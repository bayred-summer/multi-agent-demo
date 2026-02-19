"""Codex provider 实现。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.process_runner import (
    ProcessExecutionError,
    resolve_timeout_config,
    run_stream_process,
)


def _list_directories(path: Path) -> List[str]:
    """安全获取目录下一级子目录名称。"""
    try:
        return [item.name for item in path.iterdir() if item.is_dir()]
    except Exception:
        return []


def _find_vscode_bundled_codex() -> Optional[str]:
    """Windows 下尝试定位 VS Code 扩展内置 codex.exe。"""
    if os.name != "nt":
        return None

    user_profile = os.environ.get("USERPROFILE")
    if not user_profile:
        return None

    extensions_dir = Path(user_profile) / ".vscode" / "extensions"
    extension_dirs = sorted(
        (
            name
            for name in _list_directories(extensions_dir)
            if name.startswith("openai.chatgpt-")
        ),
        reverse=True,
    )

    for extension_dir in extension_dirs:
        exe_path = (
            extensions_dir
            / extension_dir
            / "bin"
            / "windows-x86_64"
            / "codex.exe"
        )
        if exe_path.exists():
            return str(exe_path)

    return None


def resolve_codex_command() -> str:
    """解析最终要执行的 codex 命令路径。"""
    if os.environ.get("CODEX_BIN"):
        return os.environ["CODEX_BIN"]

    bundled = _find_vscode_bundled_codex()
    if bundled:
        return bundled

    return "codex"


def _text_from_parts(value: Any) -> str:
    """从多种消息结构中抽取纯文本。"""
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, list):
        return "".join(_text_from_parts(item) for item in value)
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"]
        if isinstance(value.get("output_text"), str):
            return value["output_text"]
        if isinstance(value.get("content"), list):
            return _text_from_parts(value["content"])
        if value.get("delta") is not None:
            return _text_from_parts(value["delta"])
        if value.get("message") is not None:
            return _text_from_parts(value["message"])
    return ""


def _extract_assistant_text(event: Dict[str, Any], state: Dict[str, Any]) -> str:
    """从单条 Codex JSON 事件中抽取助手输出文本。"""
    if not isinstance(event, dict):
        return ""

    if event.get("type") == "thread.started" and isinstance(event.get("thread_id"), str):
        state["thread_id"] = event["thread_id"]

    if event.get("type") == "item.completed" and isinstance(event.get("item"), dict):
        item = event["item"]
        if item.get("type") in {"agent_message", "assistant"}:
            if state["saw_delta"]:
                return ""
            return _text_from_parts(item.get("text") or item.get("message") or item.get("content"))

    if event.get("type") == "agent_message_delta":
        state["saw_delta"] = True
        return _text_from_parts(event.get("delta"))

    if event.get("type") == "agent_message":
        if state["saw_delta"]:
            return ""
        return _text_from_parts(event.get("message"))

    if event.get("type") == "assistant":
        if state["saw_delta"]:
            return ""
        return _text_from_parts(event.get("message") or event.get("content"))

    if event.get("role") == "assistant":
        if state["saw_delta"]:
            return ""
        return _text_from_parts(event.get("content") or event.get("message") or event.get("delta"))

    return ""


def invoke_codex(
    prompt: str,
    session_id: Optional[str] = None,
    stream: bool = True,
    *,
    workdir: Optional[str] = None,
    exec_mode: str = "safe",
    output_schema: Optional[Any] = None,
    timeout_level: str = "standard",
    idle_timeout_s: Optional[float] = None,
    max_timeout_s: Optional[float] = None,
    terminate_grace_s: Optional[float] = None,
) -> Dict[str, Any]:
    """调用 Codex CLI 并解析流式输出。"""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")

    codex_command = resolve_codex_command()
    base_flags = ["--json", "--skip-git-repo-check"]
    exec_prefix = ["exec"]
    normalized_exec_mode = (exec_mode or "safe").strip().lower()
    if normalized_exec_mode == "full_auto":
        exec_prefix.append("--full-auto")
    elif normalized_exec_mode == "bypass":
        exec_prefix.append("--dangerously-bypass-approvals-and-sandbox")
    elif normalized_exec_mode != "safe":
        raise ValueError("exec_mode must be one of: safe, full_auto, bypass")

    args = (
        [*exec_prefix, "resume", *base_flags, session_id, prompt]
        if session_id
        else [*exec_prefix, *base_flags, prompt]
    )

    schema_temp_file: Optional[str] = None
    if output_schema is not None:
        schema_path = ""
        if isinstance(output_schema, str):
            candidate = Path(output_schema)
            if candidate.exists():
                schema_path = str(candidate)
            else:
                schema_path = output_schema
        else:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", encoding="utf-8", delete=False
            ) as fp:
                json.dump(output_schema, fp, ensure_ascii=False, indent=2)
                schema_temp_file = fp.name
                schema_path = schema_temp_file
        args += ["--output-schema", schema_path]

    state: Dict[str, Any] = {
        "saw_delta": False,
        "thread_id": session_id,
        "printed_any": False,
        "needs_newline": False,
        "output_parts": [],
    }

    def on_stdout_line(line: str) -> None:
        trimmed = line.strip()
        if not trimmed:
            return
        try:
            event = json.loads(trimmed)
        except json.JSONDecodeError:
            return

        text = _extract_assistant_text(event, state)
        if not text:
            return

        state["output_parts"].append(text)
        if stream:
            print(text, end="", flush=True)
            state["printed_any"] = True
            state["needs_newline"] = not text.endswith("\n")

    timeout = resolve_timeout_config(
        timeout_level=timeout_level,
        idle_timeout_s=idle_timeout_s,
        max_timeout_s=max_timeout_s,
        terminate_grace_s=terminate_grace_s,
    )

    try:
        try:
            result = run_stream_process(
                provider="codex",
                command=codex_command,
                args=args,
                workdir=workdir,
                timeout=timeout,
                stream_stderr=stream,
                stderr_prefix="[codex stderr] ",
                on_stdout_line=on_stdout_line,
            )
        except ProcessExecutionError as exc:
            raise ProcessExecutionError(
                provider=exc.provider,
                reason=exc.reason,
                command_repr=exc.command_repr,
                elapsed_ms=exc.elapsed_ms,
                return_code=exc.return_code,
                stderr_lines=exc.stderr_lines,
                session_id=state.get("thread_id"),
                extra_message=exc.extra_message,
            ) from exc
    finally:
        if schema_temp_file:
            try:
                Path(schema_temp_file).unlink(missing_ok=True)
            except Exception:
                pass

    if stream and state["printed_any"] and state["needs_newline"]:
        print("")

    return {
        "provider": "codex",
        "text": "".join(state["output_parts"]),
        "session_id": state.get("thread_id"),
        "elapsed_ms": result.elapsed_ms,
    }
