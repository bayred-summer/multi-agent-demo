"""Claude MiniMax provider 实现。"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from src.utils.process_runner import (
    ProcessExecutionError,
    resolve_timeout_config,
    run_stream_process,
)


def resolve_claude_command() -> str:
    """解析最终要执行的 claude 命令路径。"""
    custom_bin = os.environ.get("CLAUDE_BIN")
    if custom_bin:
        return custom_bin

    if os.name == "nt":
        app_data = os.environ.get("APPDATA")
        if app_data:
            claude_cmd = os.path.join(app_data, "npm", "claude.cmd")
            if os.path.exists(claude_cmd):
                return claude_cmd

    return "claude"


def _extract_text_from_assistant_message(message: Any) -> str:
    """从 assistant.message 结构中提取文本内容。"""
    if not isinstance(message, dict):
        return ""

    content = message.get("content")
    if not isinstance(content, list):
        return ""

    text_parts: List[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            text_parts.append(block["text"])
    return "".join(text_parts)


def _extract_claude_text(event: Dict[str, Any], state: Dict[str, Any]) -> str:
    """从单条 Claude stream-json 事件中提取可输出文本。"""
    if not isinstance(event, dict):
        return ""

    if isinstance(event.get("session_id"), str):
        state["session_id"] = event["session_id"]

    event_type = event.get("type")

    if event_type == "stream_event" and isinstance(event.get("event"), dict):
        stream_event = event["event"]
        if stream_event.get("type") == "content_block_delta":
            delta = stream_event.get("delta")
            if isinstance(delta, dict) and delta.get("type") == "text_delta":
                text = delta.get("text")
                if isinstance(text, str) and text:
                    state["saw_text_delta"] = True
                    return text
        return ""

    if event_type == "assistant":
        if state["saw_text_delta"] or state["printed_fallback"]:
            return ""
        text = _extract_text_from_assistant_message(event.get("message"))
        if text:
            state["printed_fallback"] = True
            return text
        return ""

    if event_type == "result" and event.get("subtype") == "success":
        if state["saw_text_delta"] or state["printed_fallback"]:
            return ""
        result_text = event.get("result")
        if isinstance(result_text, str) and result_text:
            state["printed_fallback"] = True
            return result_text
        return ""

    return ""


def invoke_claude_minimax(
    prompt: str,
    session_id: Optional[str] = None,
    stream: bool = True,
    *,
    workdir: Optional[str] = None,
    timeout_level: str = "standard",
    idle_timeout_s: Optional[float] = None,
    max_timeout_s: Optional[float] = None,
    terminate_grace_s: Optional[float] = None,
) -> Dict[str, Any]:
    """调用 Claude CLI（MiniMax 配置）并解析流式输出。"""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")

    claude_command = resolve_claude_command()
    args = [
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
    ]
    if session_id:
        args += ["-r", session_id]
    args.append(prompt)

    state: Dict[str, Any] = {
        "session_id": session_id,
        "saw_text_delta": False,
        "printed_fallback": False,
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

        text = _extract_claude_text(event, state)
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
        result = run_stream_process(
            provider="claude-minimax",
            command=claude_command,
            args=args,
            workdir=workdir,
            timeout=timeout,
            stream_stderr=stream,
            stderr_prefix="[claude stderr] ",
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
            session_id=state.get("session_id"),
            extra_message=exc.extra_message,
        ) from exc

    if stream and state["printed_any"] and state["needs_newline"]:
        print("")

    return {
        "provider": "claude-minimax",
        "text": "".join(state["output_parts"]),
        "session_id": state.get("session_id"),
        "elapsed_ms": result.elapsed_ms,
    }
