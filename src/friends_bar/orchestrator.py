"""Friends Bar Phase0: two-agent orchestration and prompt protocol."""

from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional

from src.friends_bar.agents import (
    AGENTS,
    DUFFY,
    LINA_BELL,
    display_agent_name,
    normalize_agent_name,
)
from src.invoke import invoke
from src.utils.runtime_config import load_runtime_config

# Phase0 currently supports a fixed two-agent turn order.
AGENT_TURN_ORDER = (LINA_BELL, DUFFY)
# Keep a single provider call per turn to avoid long silent waits.
MAX_PROTOCOL_RETRY = 0


def _next_agent(current_name: str) -> str:
    """Return the next agent name by fixed turn order."""
    if current_name == AGENT_TURN_ORDER[0]:
        return AGENT_TURN_ORDER[1]
    return AGENT_TURN_ORDER[0]


def validate_minimal_protocol(output: str, peer_agent: str) -> tuple[bool, list[str]]:
    """Validate minimal protocol compliance for one agent output."""
    errors: list[str] = []
    lines = output.strip().splitlines()

    if not lines:
        errors.append("输出为空")
        return False, errors

    peer_display = display_agent_name(peer_agent)
    first_line = lines[0].strip()
    last_line = lines[-1].strip()

    expected_first = f"发送给{peer_display}：路由确认"
    if first_line != expected_first:
        errors.append(
            f"第一行必须是：{expected_first}，实际：{first_line[:50]}..."
        )

    expected_prefix = f"发送给{peer_display}："
    if not last_line.startswith(expected_prefix):
        errors.append(f"最后一行必须以「{expected_prefix}」开头")
    elif len(last_line) <= len(expected_prefix):
        errors.append("最后一行必须包含具体问题，不能为空")

    return len(errors) == 0, errors


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
        lines.append(f"第{item['turn']}轮 {agent_display}：{item['text']}")
    return "\n".join(lines)


def _extract_peer_question(
    transcript: List[Dict[str, Any]],
    current_agent: str,
) -> Optional[str]:
    """Extract the latest line explicitly addressed to current agent."""
    if not transcript:
        return None

    current_display = display_agent_name(current_agent)
    markers = (
        f"发送给{current_display}：",
        f"发送给{current_agent}：",
        f"给{current_display}：",
        f"给{current_agent}：",
    )

    for item in reversed(transcript):
        text = item.get("text") or ""
        for line in reversed(text.splitlines()):
            for marker in markers:
                if marker in line:
                    extracted = line.split(marker, 1)[1].strip()
                    if extracted:
                        return extracted
    return None


def _agent_output_contract(*, current_agent: str, peer_agent: str) -> str:
    """Return role-specific output contract for stable multi-agent handoff."""
    peer_display = display_agent_name(peer_agent)

    common_rules = (
        "元规则（来自 03-meta-rules）\n"
        "1) 先复述任务与约束，再行动；不能跳过问题定义。\n"
        "2) 只陈述有证据的结论；禁止猜测与表演式同意。\n"
        "3) 发现不合理假设要直接指出，并给出替代方案。\n"
        "4) 无法确认的事项必须标注「未验证」，不要伪造完成状态。\n"
        "5) 评审以质量门禁为先，不做「老好人」式放行。\n"
        "\n"
        "固定消息边界\n"
        f"- 第一行必须是：发送给{peer_display}：路由确认\n"
        f"- 最后一行必须是：发送给{peer_display}：<一个明确问题>\n"
    )

    if current_agent == LINA_BELL:
        return (
            f"{common_rules}\n"
            "你当前角色：开发实现 + 发布运维。\n"
            "你的输出必须按以下区块顺序，且区块名不得改动：\n"
            "[接收方]\n"
            "[任务理解]：目标 / 范围外 / 验收标准\n"
            "[实施清单]：将修改的文件、命令、部署或环境动作\n"
            "[执行证据]：命令 + 结果（失败也要写）\n"
            "[风险与回滚]：风险点 + 回滚方案\n"
            f"[给{peer_display}的问题]\n"
            "约束：\n"
            "- 声称“已完成”时，必须在[执行证据]给出命令级证据。\n"
            "- 如果本轮未执行代码/命令，要明确写“未执行”及原因。\n"
        )

    if current_agent == DUFFY:
        return (
            f"{common_rules}\n"
            "你当前角色：资深 Code Reviewer（兼 QA 测试负责人）。\n"
            "你的首要目标是找出会导致功能错误、回归、安全或稳定性问题的缺陷，并给出可执行修复建议。\n"
            "你的输出必须按以下区块顺序，且区块名不得改动：\n"
            "[接收方]\n"
            "[验收结论]：通过 / 有条件通过 / 不通过（只能三选一）\n"
            "[核验清单]：本轮检查了哪些文件、命令和场景\n"
            "[根因链]：问题触发路径与影响链路\n"
            "[问题清单]：编号 / 严重级别(P0/P1/P2) / 类型 / 文件定位 / 证据 / 影响 / 修复建议 / 回归测试\n"
            "[回归门禁]：允许合入 / 有条件合入 / 禁止合入 + 条件\n"
            f"[给{peer_display}的问题]\n"
            "约束：\n"
            "- 优先级顺序：正确性 > 回归风险 > 安全 > 性能 > 可维护性。\n"
            "- 禁止把纯样式意见当作阻塞项。\n"
            "- 如未发现阻塞问题，必须明确“未发现阻塞问题”并写出剩余风险。\n"
            "- 结论必须与证据一致，不得出现“无证据通过”。\n"
        )

    return common_rules


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
    peer_question = _extract_peer_question(transcript, current_agent)
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
            "禁止输出“我来创建/修改/查看目录”等执行承诺，"
            "必须直接给出中文评审结论与问题清单。"
            "若证据不足，请标注“证据不足”并给出需补充证据。"
        )

    turn_task_goal = user_request
    if current_agent == DUFFY and transcript:
        turn_task_goal = (
            "本轮仅做中文代码评审："
            "请以协作历史中最近一条来自玲娜贝儿的交付为评审对象，"
            "严格按输出协议给出验收结论、问题清单和回归门禁，"
            "禁止执行实现或要求额外授权。"
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
        "仅当缺口会直接阻断交付时，才允许在最后一行提出1个明确问题。\n"
        "硬性校验规则（违反会被判定失败并要求重写）：\n"
        f"1) 第一行必须完全等于：发送给{peer_display}：路由确认\n"
        f"2) 最后一行必须以：发送给{peer_display}： 开头，且包含一个明确问题\n"
        "3) 禁止以“我先看一下”“让我先了解”等元话术作为首句\n"
        f"{role_guard}\n"
        "不要问好，不要寒暄，不要自我介绍。\n\n"
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
            provider_defaults.get("permission_mode", "default")
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

    return {
        "response_mode": response_mode,
        "provider_options": provider_options,
    }


def _coerce_protocol_output(raw_text: str, peer_agent: str) -> str:
    """Wrap raw text into a protocol-compliant envelope as a final fallback."""
    peer_display = display_agent_name(peer_agent)
    cleaned = (raw_text or "").strip()

    question = ""
    if cleaned:
        # Pick the last explicit question sentence when possible.
        question_candidates = re.findall(r"([^\n。！？!?]*[？?])", cleaned)
        if question_candidates:
            question = question_candidates[-1].strip()
    if not question:
        question = "你希望我下一步优先处理哪一项？"

    body_prefix = "[protocol_adapted] 原始输出未通过协议校验，已自动封装。"
    body = f"{body_prefix}\n{cleaned}" if cleaned else body_prefix

    return (
        f"发送给{peer_display}：路由确认\n"
        f"{body}\n"
        f"发送给{peer_display}：{question}"
    )


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

    for turn in range(1, resolved_rounds + 1):
        peer_agent = _next_agent(current_agent)
        runtime_info = _resolve_agent_runtime(
            runtime_config=runtime_config,
            agent_name=current_agent,
        )

        if stream:
            current_display = display_agent_name(current_agent)
            peer_display = display_agent_name(peer_agent)
            print(f"\n[system] 第{turn}轮执行中：{current_display} -> {peer_display}")

        text = ""
        result: Dict[str, Any] = {}
        protocol_errors: List[str] = []
        extra_instruction: Optional[str] = None

        for _ in range(MAX_PROTOCOL_RETRY + 1):
            adjusted_prompt = _build_turn_prompt(
                user_request=user_request,
                current_agent=current_agent,
                peer_agent=peer_agent,
                workdir=resolved_workdir,
                response_mode=runtime_info["response_mode"],
                transcript=transcript,
                extra_instruction=extra_instruction,
            )

            result = invoke(
                current_agent,
                adjusted_prompt,
                use_session=use_session,
                stream=False,
                workdir=resolved_workdir,
                provider_options=runtime_info["provider_options"],
                timeout_level=timeout_level,
            )

            text = (result.get("text") or "").strip()
            if not text:
                text = "（空回复）"

            is_valid, protocol_errors = validate_minimal_protocol(text, peer_agent)
            if is_valid:
                break

            peer_display = display_agent_name(peer_agent)
            extra_instruction = (
                "你上一条输出没有通过协议校验："
                + " / ".join(protocol_errors)
                + "。请在不改变任务目标的前提下，"
                "严格按协议完整重写整条输出，不要解释原因。\n"
                f"重写时首行必须是：发送给{peer_display}：路由确认\n"
                f"重写时末行必须是：发送给{peer_display}：<一个明确问题>\n"
            )

        if protocol_errors:
            text = _coerce_protocol_output(text, peer_agent)

        turn_record = {
            "turn": turn,
            "agent": current_agent,
            "provider": result.get("cli"),
            "text": text,
            "session_id": result.get("session_id"),
            "elapsed_ms": result.get("elapsed_ms"),
        }
        transcript.append(turn_record)

        if stream:
            current_display = display_agent_name(current_agent)
            peer_display = display_agent_name(peer_agent)
            print(f"\n[{current_display} -> {peer_display}]")
            _safe_print(text)

        current_agent = peer_agent

    return {
        "workspace": "Friends Bar",
        "user_request": user_request,
        "rounds": resolved_rounds,
        "turns": transcript,
    }
