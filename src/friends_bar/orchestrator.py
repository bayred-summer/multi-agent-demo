"""Friends Bar Phase0: two-agent orchestration and prompt protocol."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time
import traceback
from typing import Any, Dict, List, Optional

from src.friends_bar.agents import (
    AGENTS,
    DUFFY,
    LINA_BELL,
    display_agent_name,
    normalize_agent_name,
)
from src.invoke import invoke
from src.protocol.models import build_task_envelope
from src.protocol.validators import (
    build_agent_output_schema,
    validate_json_protocol_content,
)
from src.utils.audit_log import AuditLogConfig, AuditLogger, text_meta
from src.utils.runtime_config import load_runtime_config

# Phase0 currently supports a fixed two-agent turn order.
AGENT_TURN_ORDER = (LINA_BELL, DUFFY)
# Keep retries small but non-zero for strict schema re-generation.
MAX_PROTOCOL_RETRY = 3


def _next_agent(current_name: str) -> str:
    """Return the next agent name by fixed turn order."""
    if current_name == AGENT_TURN_ORDER[0]:
        return AGENT_TURN_ORDER[1]
    return AGENT_TURN_ORDER[0]


def _validate_agent_output(
    *,
    current_agent: str,
    output: str,
    peer_agent: str,
    trace_id: str = "",
) -> tuple[bool, list[str], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Validate strict JSON protocol output and return normalized content."""
    raw = (output or "").strip()
    if not raw:
        return False, ["E_SCHEMA_INVALID_FORMAT: empty output"], None, None

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return (
            False,
            [f"E_SCHEMA_INVALID_FORMAT: output is not valid JSON ({exc.msg})"],
            None,
            None,
        )

    if not isinstance(payload, dict):
        return (
            False,
            ["E_SCHEMA_INVALID_FORMAT: output must be one JSON object"],
            None,
            None,
        )

    peer_display = display_agent_name(peer_agent)
    parsed = validate_json_protocol_content(
        current_agent=current_agent,
        peer_display=peer_display,
        payload=payload,
        trace_id=trace_id,
    )
    if not parsed.ok:
        errors = [f"{item.get('code')}: {item.get('message')}" for item in parsed.errors]
        return False, errors, parsed.parsed_content, payload
    return True, [], parsed.parsed_content, payload


def _safe_print(text: str) -> None:
    """Print text safely under non-UTF-8 Windows consoles."""
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        safe_text = text.encode(encoding, errors="replace").decode(
            encoding, errors="replace"
        )
        print(safe_text)


def _format_history(transcript: List[Dict[str, Any]]) -> str:
    """Format transcript into readable history text."""
    if not transcript:
        return "（暂无历史对话）"

    lines: List[str] = []
    for item in transcript:
        agent_display = display_agent_name(item["agent"])
        content = item.get("protocol_content")
        if isinstance(content, dict):
            history_brief = {
                "schema_version": content.get("schema_version"),
                "status": content.get("status"),
                "acceptance": content.get("acceptance"),
                "next_question": content.get("next_question"),
            }
            lines.append(
                f"第{item['turn']}轮 {agent_display}："
                + json.dumps(history_brief, ensure_ascii=False)
            )
        else:
            raw_text = str(item.get("text") or "")
            lines.append(f"第{item['turn']}轮 {agent_display}：{raw_text[:300]}")
    return "\n".join(lines)


def _extract_peer_question(
    transcript: List[Dict[str, Any]],
) -> Optional[str]:
    """Extract latest question from structured JSON content."""
    if not transcript:
        return None

    for item in reversed(transcript):
        content = item.get("protocol_content")
        if isinstance(content, dict):
            next_question = content.get("next_question")
            if isinstance(next_question, str) and next_question.strip():
                return next_question.strip()
    return None


def _agent_output_contract(*, current_agent: str, peer_agent: str) -> str:
    """Return strict JSON output contract for stable multi-agent handoff."""
    peer_display = display_agent_name(peer_agent)
    schema = build_agent_output_schema(current_agent)
    schema_text = json.dumps(schema, ensure_ascii=False, indent=2)

    return (
        "输出必须严格遵循 JSON schema。\n"
        "只允许输出一个 JSON 对象；禁止输出 Markdown、代码块、前后解释文本。\n"
        f"`next_question` 必须面向接收方 {peer_display}，并包含问号。\n"
        "若证据不足，请在 JSON 中用 status/warnings/errors 明确表达，禁止自然语言补丁。\n"
        f"JSON Schema:\n{schema_text}"
    )


def _build_turn_prompt(
    *,
    user_request: str,
    current_agent: str,
    peer_agent: str,
    workdir: str,
    response_mode: str,
    transcript: List[Dict[str, Any]],
    extra_instruction: Optional[str] = None,
) -> str:
    """Build one turn prompt for current agent."""
    mission = AGENTS[current_agent].mission
    current_display = display_agent_name(current_agent)
    peer_display = display_agent_name(peer_agent)
    history_text = _format_history(transcript)
    peer_question = _extract_peer_question(transcript)
    peer_question_text = f"对方刚才的问题：{peer_question}\n\n" if peer_question else ""

    extra_text = f"\n{extra_instruction}\n" if extra_instruction else ""
    output_contract = _agent_output_contract(
        current_agent=current_agent, peer_agent=peer_agent
    )

    mode = (response_mode or "text_only").strip().lower()
    if mode == "execute":
        mode_instruction = (
            "当前为执行模式：你可以调用工具并在执行目录直接创建/修改文件，"
            "不要请求授权，不要停留在计划层。"
        )
    else:
        mode_instruction = (
            "当前为对话模式：只能输出文本，禁止工具调用、命令执行、文件读写与权限请求。"
        )

    role_guard = ""
    if current_agent == DUFFY:
        role_guard = (
            "角色硬约束：你是评审官，不是实现者。"
            "必须先执行读取/测试命令再评审。"
            "JSON 中 verification 至少包含2条命令证据。"
        )

    turn_task_goal = user_request
    if current_agent == DUFFY and transcript:
        turn_task_goal = (
            "本轮仅做中文代码评审："
            "请以协作历史中最近一条来自玲娜贝儿的交付为评审对象，"
            "严格按输出协议给出验收结论、问题清单和回归门禁，"
            "先读取实际文件并运行最小核验命令后再下结论，"
            "禁止基于口头描述做评审，禁止执行实现或要求额外授权。"
        )

    return (
        f"任务目标：{turn_task_goal}\n"
        f"原始用户需求：{user_request}\n\n"
        f"执行目录：{workdir}\n"
        f"{mode_instruction}\n\n"
        f"当前协作历史：\n{history_text}\n\n"
        f"{peer_question_text}"
        f"你是「{current_display}」（ID: {current_agent}），职责：{mission}\n"
        "请直接围绕任务作答，禁止解释系统/角色/脚本/运行方式。\n"
        "禁止输出“无法访问目录”“请授权”“请先提供文件列表”等元请求。\n"
        "信息不足时先基于当前任务做最小可执行假设并继续推进，"
        "仅当缺口会直接阻断交付时，才允许在 JSON 的 next_question 提出1个明确问题。\n"
        "硬性校验规则（违反会被判定失败并要求重写）：\n"
        "1) 输出必须是可被 json.loads 直接解析的单个 JSON 对象\n"
        "2) 输出必须满足给定 JSON Schema\n"
        "3) next_question 必须包含问号\n"
        "4) 第一字符必须是 {，最后字符必须是 }\n"
        "5) 禁止输出任何 JSON 之外字符（包括“我将先...”“```json”）\n"
        f"{role_guard}\n"
        "不要问好，不要寒暄，不要自我介绍，不要输出 JSON 之外的任何文本。\n\n"
        f"输出协议：\n{output_contract}\n"
        f"当前轮次接收方：{peer_display}\n"
        f"{extra_text}"
    )


def _resolve_agent_runtime(
    *,
    runtime_config: Dict[str, Any],
    agent_name: str,
) -> Dict[str, Any]:
    """Merge provider defaults with per-agent overrides."""
    provider_name = AGENTS[agent_name].provider
    providers_cfg = runtime_config.get("providers", {})
    provider_defaults = (
        providers_cfg.get(provider_name, {}) if isinstance(providers_cfg, dict) else {}
    )

    provider_options: Dict[str, Any] = {}
    if provider_name == "codex":
        provider_options["exec_mode"] = str(provider_defaults.get("exec_mode", "safe"))
    elif provider_name == "claude-minimax":
        provider_options["permission_mode"] = str(
            provider_defaults.get("permission_mode", "acceptEdits")
        )
        provider_options["include_partial_messages"] = bool(
            provider_defaults.get("include_partial_messages", False)
        )
        provider_options["print_stderr"] = bool(
            provider_defaults.get("print_stderr", False)
        )

    friends_bar = runtime_config.get("friends_bar", {})
    agents_cfg = friends_bar.get("agents", {}) if isinstance(friends_bar, dict) else {}

    agent_cfg: Dict[str, Any] = {}
    if isinstance(agents_cfg, dict):
        candidate_cfg = agents_cfg.get(agent_name)
        if isinstance(candidate_cfg, dict):
            agent_cfg = candidate_cfg
        else:
            display_name = display_agent_name(agent_name)
            display_cfg = agents_cfg.get(display_name)
            if isinstance(display_cfg, dict):
                agent_cfg = display_cfg

    response_mode = "text_only"
    if isinstance(agent_cfg, dict):
        response_mode = str(agent_cfg.get("response_mode", "text_only"))
        agent_provider_opts = agent_cfg.get("provider_options", {})
        if isinstance(agent_provider_opts, dict):
            provider_options.update(agent_provider_opts)

    if (
        agent_name == DUFFY
        and provider_name == "claude-minimax"
        and response_mode.strip().lower() == "execute"
    ):
        normalized_permission_mode = str(
            provider_options.get("permission_mode", "")
        ).strip()
        if normalized_permission_mode in {
            "",
            "default",
            "acceptEdits",
            "delegate",
            "dontAsk",
            "plan",
        }:
            provider_options["permission_mode"] = "bypassPermissions"

    return {
        "response_mode": response_mode,
        "provider_options": provider_options,
    }


def run_two_agent_dialogue(
    user_request: str,
    *,
    rounds: Optional[int] = None,
    start_agent: Optional[str] = None,
    project_path: Optional[str] = None,
    use_session: bool = False,
    stream: bool = True,
    timeout_level: Optional[str] = "standard",
    config_path: str = "config.toml",
) -> Dict[str, Any]:
    """Run Friends Bar two-agent dialogue loop."""
    if not isinstance(user_request, str) or not user_request.strip():
        raise ValueError("user_request must be a non-empty string")

    runtime_config = load_runtime_config(config_path=config_path)
    friends_bar_config = runtime_config.get("friends_bar", {})
    if not isinstance(friends_bar_config, dict):
        friends_bar_config = {}
    audit_logger = AuditLogger(AuditLogConfig.from_runtime_config(friends_bar_config))
    run_started = time.monotonic()

    resolved_rounds = (
        int(friends_bar_config.get("default_rounds", 4))
        if rounds is None
        else int(rounds)
    )
    if resolved_rounds < 1:
        raise ValueError("rounds must be >= 1")

    resolved_start_agent = (
        str(friends_bar_config.get("start_agent", LINA_BELL))
        if start_agent is None
        else start_agent
    )

    resolved_workdir = str(Path.cwd()) if project_path is None else str(Path(project_path))
    if not Path(resolved_workdir).exists():
        raise ValueError(f"project_path does not exist: {resolved_workdir}")
    if not Path(resolved_workdir).is_dir():
        raise ValueError(f"project_path is not a directory: {resolved_workdir}")

    current_agent = normalize_agent_name(resolved_start_agent)
    transcript: List[Dict[str, Any]] = []
    run_error: Optional[Dict[str, Any]] = None

    audit_logger.log(
        "run.started",
        {
            "workspace": "Friends Bar",
            "config_path": config_path,
            "user_request": user_request,
            "user_request_meta": text_meta(
                user_request,
                include_preview=audit_logger.include_prompt_preview,
                max_preview_chars=audit_logger.max_preview_chars,
            ),
            "args": {
                "rounds": resolved_rounds,
                "start_agent": current_agent,
                "project_path": resolved_workdir,
                "use_session": bool(use_session),
                "timeout_level": timeout_level,
                "stream": bool(stream),
            },
        },
    )
    audit_logger.log(
        "protocol.task.envelope",
        build_task_envelope(
            trace_id=audit_logger.run_id,
            sender="orchestrator",
            recipient=current_agent,
            intent="friends_bar_round_robin_task",
            user_request=user_request,
            workdir=resolved_workdir,
            timeout_level=timeout_level,
            expected_schema_version="friendsbar.review.v1",
        ),
    )

    try:
        for turn in range(1, resolved_rounds + 1):
            turn_started = time.monotonic()
            peer_agent = _next_agent(current_agent)
            runtime_info = _resolve_agent_runtime(
                runtime_config=runtime_config,
                agent_name=current_agent,
            )

            audit_logger.log(
                "turn.started",
                {
                    "turn": turn,
                    "agent": current_agent,
                    "peer_agent": peer_agent,
                    "response_mode": runtime_info.get("response_mode"),
                    "provider_options": runtime_info.get("provider_options", {}),
                },
            )

            if stream:
                current_display = display_agent_name(current_agent)
                peer_display = display_agent_name(peer_agent)
                print(f"\n[system] 第{turn}轮执行中：{current_display} -> {peer_display}")

            text = ""
            raw_text = ""
            result: Dict[str, Any] = {}
            protocol_errors: List[str] = []
            extra_instruction: Optional[str] = None
            attempt_count = 0
            structured_content: Optional[Dict[str, Any]] = None
            raw_payload: Optional[Dict[str, Any]] = None

            for attempt_idx in range(MAX_PROTOCOL_RETRY + 1):
                attempt_count = attempt_idx + 1
                # Duffy review often needs extra pre-flight time for CLI tools.
                effective_timeout_level = timeout_level
                if current_agent == DUFFY and timeout_level == "quick":
                    effective_timeout_level = "standard"

                adjusted_prompt = _build_turn_prompt(
                    user_request=user_request,
                    current_agent=current_agent,
                    peer_agent=peer_agent,
                    workdir=resolved_workdir,
                    response_mode=runtime_info["response_mode"],
                    transcript=transcript,
                    extra_instruction=extra_instruction,
                )
                audit_logger.log(
                    "turn.attempt.started",
                    {
                        "turn": turn,
                        "attempt": attempt_count,
                        "agent": current_agent,
                        "peer_agent": peer_agent,
                        "timeout_level": effective_timeout_level,
                        "prompt_meta": text_meta(
                            adjusted_prompt,
                            include_preview=audit_logger.include_prompt_preview,
                            max_preview_chars=audit_logger.max_preview_chars,
                        ),
                    },
                )

                provider_options = dict(runtime_info["provider_options"])
                agent_schema = build_agent_output_schema(current_agent)
                if AGENTS[current_agent].provider == "claude-minimax":
                    provider_options["json_schema"] = agent_schema
                if AGENTS[current_agent].provider == "codex":
                    provider_options["output_schema"] = agent_schema

                try:
                    result = invoke(
                        current_agent,
                        adjusted_prompt,
                        use_session=use_session,
                        stream=False,
                        workdir=resolved_workdir,
                        provider_options=provider_options,
                        timeout_level=effective_timeout_level,
                    )
                except Exception as exc:
                    audit_logger.log(
                        "turn.attempt.failed",
                        {
                            "turn": turn,
                            "attempt": attempt_count,
                            "agent": current_agent,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                    )
                    raise

                raw_text = (result.get("text") or "").strip()
                text = raw_text if raw_text else "（空回复）"

                is_valid, protocol_errors, parsed_content, parsed_payload = _validate_agent_output(
                    current_agent=current_agent,
                    output=text,
                    peer_agent=peer_agent,
                    trace_id=audit_logger.run_id,
                )
                structured_content = parsed_content
                raw_payload = parsed_payload
                audit_logger.log(
                    "turn.attempt.completed",
                    {
                        "turn": turn,
                        "attempt": attempt_count,
                        "agent": current_agent,
                        "provider": result.get("cli"),
                        "session_id": result.get("session_id"),
                        "elapsed_ms": result.get("elapsed_ms"),
                        "raw_text": raw_text,
                        "raw_text_meta": text_meta(
                            raw_text,
                            include_preview=audit_logger.include_prompt_preview,
                            max_preview_chars=audit_logger.max_preview_chars,
                        ),
                        "is_valid": is_valid,
                        "protocol_errors": protocol_errors,
                        "protocol_content": parsed_content,
                        "protocol_raw_payload": parsed_payload,
                    },
                )
                if is_valid:
                    if isinstance(parsed_payload, dict):
                        text = json.dumps(parsed_payload, ensure_ascii=False, indent=2)
                    break

                schema = build_agent_output_schema(current_agent)
                extra_instruction = (
                    "你上一条输出没有通过 JSON Schema 校验："
                    + " / ".join(protocol_errors)
                    + "。请在不改变任务目标的前提下输出一个合法 JSON 对象。\n"
                    "禁止输出任何 JSON 之外文本；首字符必须是 {，末字符必须是 }。\n"
                    "请严格匹配以下 schema：\n"
                    + json.dumps(schema, ensure_ascii=False, indent=2)
                )

            if protocol_errors:
                raise RuntimeError(
                    f"JSON protocol validation failed after {attempt_count} attempts: "
                    + " / ".join(protocol_errors)
                )

            turn_record = {
                "turn": turn,
                "agent": current_agent,
                "provider": result.get("cli"),
                "text": text,
                "session_id": result.get("session_id"),
                "elapsed_ms": result.get("elapsed_ms"),
                "attempts": attempt_count,
                "protocol_coerced": False,
                "protocol_content": structured_content,
                "protocol_raw_payload": raw_payload,
            }
            transcript.append(turn_record)
            audit_logger.log(
                "turn.completed",
                {
                    "turn": turn,
                    "agent": current_agent,
                    "peer_agent": peer_agent,
                    "provider": result.get("cli"),
                    "session_id": result.get("session_id"),
                    "elapsed_ms": result.get("elapsed_ms"),
                    "attempts": attempt_count,
                    "protocol_coerced": False,
                    "final_text": text,
                    "final_text_meta": text_meta(
                        text,
                        include_preview=audit_logger.include_prompt_preview,
                        max_preview_chars=audit_logger.max_preview_chars,
                    ),
                    "turn_duration_ms": int((time.monotonic() - turn_started) * 1000),
                },
            )

            if stream:
                current_display = display_agent_name(current_agent)
                peer_display = display_agent_name(peer_agent)
                print(f"\n[{current_display} -> {peer_display}]")
                _safe_print(text)

            current_agent = peer_agent
    except Exception as exc:
        run_error = {
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "turns_completed": len(transcript),
        }
        audit_logger.log("run.failed", run_error)
        raise
    finally:
        summary: Dict[str, Any] = {
            "workspace": "Friends Bar",
            "rounds": resolved_rounds,
            "turns_completed": len(transcript),
            "elapsed_ms": int((time.monotonic() - run_started) * 1000),
            "project_path": resolved_workdir,
            "turns": transcript,
        }
        if run_error is not None:
            summary["error"] = run_error
        audit_logger.finalize(
            status="failed" if run_error is not None else "success",
            summary=summary,
        )

    result_payload = {
        "workspace": "Friends Bar",
        "user_request": user_request,
        "rounds": resolved_rounds,
        "turns": transcript,
        "log": {
            "run_id": audit_logger.run_id,
            "log_file": str(audit_logger.log_file) if audit_logger.log_file else None,
            "summary_file": (
                str(audit_logger.summary_file) if audit_logger.summary_file else None
            ),
        },
    }
    if stream and result_payload["log"]["log_file"]:
        print(f"\n[system] 本次日志文件: {result_payload['log']['log_file']}")
    return result_payload
