"""Gemini provider with dual adapter support.

Adapter A: antigravity (GUI + MCP callback, no stdout parsing)
Adapter B: gemini-cli (headless CLI, parses stdout NDJSON/JSON)
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.utils.process_runner import (
    ProcessExecutionError,
    resolve_timeout_config,
    run_stream_process,
)

GEMINI_ADAPTER_ENV = "GEMINI_ADAPTER"
GEMINI_ADAPTER_CLI = "gemini-cli"
GEMINI_ADAPTER_ANTIGRAVITY = "antigravity"


def resolve_gemini_command() -> str:
    """Resolve final Gemini CLI command."""
    custom_bin = os.environ.get("GEMINI_BIN")
    if custom_bin:
        return custom_bin
    if os.name == "nt":
        app_data = os.environ.get("APPDATA")
        if app_data:
            gemini_cmd = os.path.join(app_data, "npm", "gemini.cmd")
            if os.path.exists(gemini_cmd):
                return gemini_cmd
    return "gemini"


def _text_from_value(value: Any) -> str:
    """Extract display text from mixed JSON values."""
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, list):
        return "".join(_text_from_value(item) for item in value)
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"]
        if isinstance(value.get("content"), str):
            return value["content"]
        if isinstance(value.get("response"), str):
            return value["response"]
    return ""


def _extract_assistant_text(event: Dict[str, Any], state: Dict[str, Any]) -> str:
    """Extract assistant text from one stream-json event."""
    if not isinstance(event, dict):
        return ""

    if event.get("type") == "init" and isinstance(event.get("session_id"), str):
        state["session_id"] = event["session_id"]
        return ""

    if event.get("type") == "message" and event.get("role") == "assistant":
        content = _text_from_value(event.get("content"))
        if not content:
            return ""
        # Delta mode can emit multiple assistant chunks; keep all chunks.
        if event.get("delta") is True:
            state["saw_delta"] = True
            return content
        # If delta was already consumed, ignore later non-delta duplicate text.
        if state.get("saw_delta"):
            return ""
        return content

    return ""


def _pick_final_text(state: Dict[str, Any]) -> str:
    """Pick the most reliable final text across channels."""
    response_text = state.get("response_text", "")
    stream_text = "".join(state.get("output_parts", []))
    if isinstance(response_text, str) and response_text.strip():
        return response_text
    return stream_text


def _normalize_auth_mode(auth_mode: Optional[str]) -> str:
    """Normalize auth mode value."""
    mode = (auth_mode or "auto").strip().lower()
    if mode not in {"auto", "oauth", "api_key", "vertex"}:
        raise ValueError("auth_mode must be one of: auto, oauth, api_key, vertex")
    return mode


def _validate_auth_prerequisites(auth_mode: str) -> None:
    """Validate required environment variables for explicit auth modes."""
    has_gemini_key = bool(os.environ.get("GEMINI_API_KEY"))
    has_google_key = bool(os.environ.get("GOOGLE_API_KEY"))
    has_project = bool(
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GOOGLE_CLOUD_PROJECT_ID")
    )
    has_location = bool(os.environ.get("GOOGLE_CLOUD_LOCATION"))
    has_adc = bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))

    if auth_mode == "api_key" and not has_gemini_key:
        raise ValueError(
            "auth_mode=api_key requires GEMINI_API_KEY for headless automation"
        )
    if auth_mode == "vertex":
        if has_google_key:
            return
        if has_project and has_location and has_adc:
            return
        raise ValueError(
            "auth_mode=vertex requires GOOGLE_API_KEY, or "
            "GOOGLE_APPLICATION_CREDENTIALS + GOOGLE_CLOUD_PROJECT + GOOGLE_CLOUD_LOCATION"
        )


def _resolve_adapter(adapter: Optional[str]) -> str:
    """Resolve adapter from explicit arg > env > default."""
    raw = (adapter or os.environ.get(GEMINI_ADAPTER_ENV) or GEMINI_ADAPTER_CLI).strip().lower()
    alias_map = {
        "cli": GEMINI_ADAPTER_CLI,
        "gemini_cli": GEMINI_ADAPTER_CLI,
        "gemini-cli": GEMINI_ADAPTER_CLI,
        "antigravity": GEMINI_ADAPTER_ANTIGRAVITY,
        "antigravity-mcp": GEMINI_ADAPTER_ANTIGRAVITY,
        "mcp": GEMINI_ADAPTER_ANTIGRAVITY,
    }
    if raw not in alias_map:
        raise ValueError(
            "adapter must be one of: gemini-cli, antigravity "
            "(or aliases: cli, gemini_cli, antigravity-mcp, mcp)"
        )
    return alias_map[raw]


def _emit_event(
    event_hook: Optional[Callable[[str, Dict[str, Any]], None]],
    event: str,
    payload: Dict[str, Any],
) -> None:
    """Emit optional structured provider event."""
    if event_hook:
        event_hook(event, payload)


def _strip_optional_text(value: Optional[str]) -> Optional[str]:
    """Normalize optional text value: trim and map empty to None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_cli_env(
    *,
    no_browser: Optional[bool],
    proxy: Optional[str],
    no_proxy: Optional[str],
) -> Optional[Dict[str, str]]:
    """Build subprocess env for Gemini CLI when runtime overrides are needed."""
    resolved_proxy = _strip_optional_text(proxy)
    resolved_no_proxy = _strip_optional_text(no_proxy)

    if no_browser is None and resolved_proxy is None and resolved_no_proxy is None:
        return None

    proc_env = os.environ.copy()
    if no_browser is not None:
        proc_env["NO_BROWSER"] = "true" if no_browser else "false"

    if resolved_proxy is not None:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            proc_env[key] = resolved_proxy
        if resolved_no_proxy is None:
            fallback = proc_env.get("NO_PROXY") or proc_env.get("no_proxy")
            if not fallback:
                proc_env["NO_PROXY"] = "localhost,127.0.0.1"
                proc_env["no_proxy"] = "localhost,127.0.0.1"

    if resolved_no_proxy is not None:
        proc_env["NO_PROXY"] = resolved_no_proxy
        proc_env["no_proxy"] = resolved_no_proxy

    return proc_env


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    """Write JSON atomically to avoid half-written callback files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _invoke_antigravity_callback(
    *,
    prompt: str,
    session_id: Optional[str],
    workdir: Optional[str],
    model: Optional[str],
    event_hook: Optional[Callable[[str, Dict[str, Any]], None]],
    callback_dir: Optional[str],
    request_id: Optional[str],
    poll_interval_s: float,
    callback_timeout_s: float,
    cleanup_response: bool,
) -> Dict[str, Any]:
    """MCP callback adapter (GUI integration, no stdout parsing)."""
    started = time.monotonic()
    rid = request_id or uuid.uuid4().hex
    root = Path(callback_dir or ".gemini/mcp_bridge")
    requests_dir = root / "requests"
    responses_dir = root / "responses"
    request_path = requests_dir / f"{rid}.json"
    response_path = responses_dir / f"{rid}.json"

    request_payload: Dict[str, Any] = {
        "request_id": rid,
        "prompt": prompt,
        "session_id": session_id,
        "workdir": workdir,
        "model": model,
        "timestamp_ms": int(time.time() * 1000),
        "adapter": GEMINI_ADAPTER_ANTIGRAVITY,
    }
    _atomic_write_json(request_path, request_payload)
    _emit_event(
        event_hook,
        "adapter.request_written",
        {
            "provider": "gemini",
            "adapter": GEMINI_ADAPTER_ANTIGRAVITY,
            "request_id": rid,
            "request_path": str(request_path),
            "response_path": str(response_path),
        },
    )

    interval = max(0.05, float(poll_interval_s))
    timeout_s = max(1.0, float(callback_timeout_s))
    while True:
        if response_path.exists():
            raw = response_path.read_text(encoding="utf-8").strip()
            try:
                payload = json.loads(raw) if raw else {}
            except json.JSONDecodeError as exc:
                raise ProcessExecutionError(
                    provider="gemini",
                    reason="mcp_callback_invalid_json",
                    command_repr=f"antigravity-mcp-callback request_id={rid}",
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                    extra_message=str(exc),
                ) from exc

            callback_request_id = str(payload.get("request_id", rid))
            if callback_request_id != rid:
                raise ProcessExecutionError(
                    provider="gemini",
                    reason="mcp_callback_request_id_mismatch",
                    command_repr=f"antigravity-mcp-callback request_id={rid}",
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                    extra_message=(
                        f"response request_id={callback_request_id} does not match expected {rid}"
                    ),
                )

            if str(payload.get("status", "ok")).lower() == "error":
                raise ProcessExecutionError(
                    provider="gemini",
                    reason="mcp_callback_error",
                    command_repr=f"antigravity-mcp-callback request_id={rid}",
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                    extra_message=str(payload.get("error", "callback returned error")),
                )

            text = _text_from_value(payload.get("text"))
            if not text:
                text = _text_from_value(payload.get("response"))
            if not text:
                text = _text_from_value(payload.get("content"))
            if not text and isinstance(payload.get("result"), dict):
                text = _text_from_value(payload["result"].get("text"))
            if not text:
                raise ProcessExecutionError(
                    provider="gemini",
                    reason="mcp_callback_missing_text",
                    command_repr=f"antigravity-mcp-callback request_id={rid}",
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                    extra_message="callback payload does not contain text/response/content",
                )

            final_session_id = payload.get("session_id")
            if not isinstance(final_session_id, str) or not final_session_id.strip():
                final_session_id = session_id

            if cleanup_response:
                try:
                    response_path.unlink(missing_ok=True)
                except OSError:
                    pass

            elapsed = int((time.monotonic() - started) * 1000)
            _emit_event(
                event_hook,
                "adapter.callback_received",
                {
                    "provider": "gemini",
                    "adapter": GEMINI_ADAPTER_ANTIGRAVITY,
                    "request_id": rid,
                    "elapsed_ms": elapsed,
                },
            )
            return {
                "provider": "gemini",
                "text": text,
                "session_id": final_session_id,
                "elapsed_ms": elapsed,
            }

        elapsed_s = time.monotonic() - started
        if elapsed_s > timeout_s:
            raise ProcessExecutionError(
                provider="gemini",
                reason="mcp_callback_timeout",
                command_repr=f"antigravity-mcp-callback request_id={rid}",
                elapsed_ms=int(elapsed_s * 1000),
                extra_message=(
                    f"no callback at {response_path} within {timeout_s:.1f}s; "
                    f"request written to {request_path}"
                ),
            )
        time.sleep(interval)


def _invoke_gemini_cli(
    *,
    prompt: str,
    session_id: Optional[str],
    stream: bool,
    workdir: Optional[str],
    model: Optional[str],
    approval_mode: Optional[str],
    sandbox: Optional[bool],
    yolo: bool,
    allowed_tools: Optional[List[str]],
    output_format: Optional[str],
    raw_output: bool,
    auth_mode: Optional[str],
    no_browser: Optional[bool],
    proxy: Optional[str],
    no_proxy: Optional[str],
    print_stderr: bool,
    event_hook: Optional[Callable[[str, Dict[str, Any]], None]],
    timeout_level: str,
    idle_timeout_s: Optional[float],
    max_timeout_s: Optional[float],
    terminate_grace_s: Optional[float],
) -> Dict[str, Any]:
    """Headless gemini-cli adapter implementation."""
    gemini_command = resolve_gemini_command()
    resolved_auth_mode = _normalize_auth_mode(auth_mode)
    _validate_auth_prerequisites(resolved_auth_mode)
    fmt = (output_format or ("stream-json" if stream else "json")).strip().lower()
    if fmt not in {"text", "json", "stream-json"}:
        raise ValueError("output_format must be one of: text, json, stream-json")

    args: List[str] = ["-p", prompt, "--output-format", fmt]
    if model:
        args += ["--model", model]
    if approval_mode:
        args += ["--approval-mode", approval_mode]
    if sandbox is not None:
        args += ["--sandbox", "true" if sandbox else "false"]
    if yolo:
        args.append("--yolo")
    if session_id:
        args += ["--resume", session_id]
    if allowed_tools:
        for tool in allowed_tools:
            args += ["--allowed-tools", str(tool)]
    if raw_output:
        args += ["--raw-output", "--accept-raw-output-risk"]

    proc_env = _build_cli_env(
        no_browser=no_browser,
        proxy=proxy,
        no_proxy=no_proxy,
    )

    state: Dict[str, Any] = {
        "session_id": session_id,
        "output_parts": [],
        "response_text": "",
        "json_buffer": [],
        "printed_any": False,
        "needs_newline": False,
        "saw_delta": False,
    }

    def on_stdout_line(line: str) -> None:
        if fmt == "json":
            state["json_buffer"].append(line)
            raw = "\n".join(state["json_buffer"]).strip()
            if not raw:
                return
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                return
            if isinstance(payload, dict):
                if isinstance(payload.get("session_id"), str):
                    state["session_id"] = payload["session_id"]
                response = payload.get("response")
                if isinstance(response, (dict, list)):
                    state["response_text"] = json.dumps(
                        response, ensure_ascii=False, separators=(",", ":")
                    )
                else:
                    state["response_text"] = _text_from_value(response)
            return

        if fmt == "stream-json":
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
            return

        # text mode fallback
        if line:
            state["output_parts"].append(line + "\n")
            if stream:
                print(line)

    timeout = resolve_timeout_config(
        timeout_level=timeout_level,
        idle_timeout_s=idle_timeout_s,
        max_timeout_s=max_timeout_s,
        terminate_grace_s=terminate_grace_s,
    )

    try:
        result = run_stream_process(
            provider="gemini",
            command=gemini_command,
            args=args,
            workdir=workdir,
            env=proc_env,
            timeout=timeout,
            stream_stderr=bool(print_stderr and stream),
            stderr_prefix="[gemini stderr] ",
            on_stdout_line=on_stdout_line,
            on_process_start=lambda payload: _emit_event(
                event_hook, "subprocess.started", payload
            ),
            on_first_byte=lambda payload: _emit_event(
                event_hook, "subprocess.first_byte", payload
            ),
            inherit_stdin=True,
        )
    except ProcessExecutionError as exc:
        stderr_lower = " ".join(exc.stderr_tail).lower()
        extra_message = exc.extra_message
        if "interactive consent could not be obtained" in stderr_lower:
            extra_message = (
                "Gemini OAuth needs interactive consent. "
                "For workflow automation, prefer auth_mode=api_key (set GEMINI_API_KEY) "
                "or auth_mode=vertex."
            )
        raise ProcessExecutionError(
            provider=exc.provider,
            reason=exc.reason,
            command_repr=exc.command_repr,
            elapsed_ms=exc.elapsed_ms,
            return_code=exc.return_code,
            stderr_lines=exc.stderr_lines,
            session_id=state.get("session_id"),
            extra_message=extra_message,
        ) from exc

    if stream and state["printed_any"] and state["needs_newline"]:
        print("")

    return {
        "provider": "gemini",
        "text": _pick_final_text(state),
        "session_id": state.get("session_id"),
        "elapsed_ms": result.elapsed_ms,
    }


def invoke_gemini(
    prompt: str,
    session_id: Optional[str] = None,
    stream: bool = True,
    *,
    workdir: Optional[str] = None,
    model: Optional[str] = None,
    approval_mode: Optional[str] = None,
    sandbox: Optional[bool] = None,
    yolo: bool = False,
    allowed_tools: Optional[List[str]] = None,
    output_format: Optional[str] = None,
    raw_output: bool = False,
    auth_mode: Optional[str] = None,
    no_browser: Optional[bool] = None,
    proxy: Optional[str] = None,
    no_proxy: Optional[str] = None,
    print_stderr: bool = False,
    adapter: Optional[str] = None,
    mcp_callback_dir: Optional[str] = None,
    mcp_request_id: Optional[str] = None,
    mcp_poll_interval_s: float = 0.25,
    mcp_timeout_s: float = 300.0,
    mcp_cleanup_response: bool = True,
    event_hook: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    timeout_level: str = "standard",
    idle_timeout_s: Optional[float] = None,
    max_timeout_s: Optional[float] = None,
    terminate_grace_s: Optional[float] = None,
) -> Dict[str, Any]:
    """Invoke Gemini with pluggable adapter strategy."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")

    selected_adapter = _resolve_adapter(adapter)
    _emit_event(
        event_hook,
        "adapter.selected",
        {"provider": "gemini", "adapter": selected_adapter},
    )

    if selected_adapter == GEMINI_ADAPTER_ANTIGRAVITY:
        callback_timeout = (
            float(max_timeout_s) if max_timeout_s is not None else float(mcp_timeout_s)
        )
        return _invoke_antigravity_callback(
            prompt=prompt,
            session_id=session_id,
            workdir=workdir,
            model=model,
            event_hook=event_hook,
            callback_dir=mcp_callback_dir,
            request_id=mcp_request_id,
            poll_interval_s=float(mcp_poll_interval_s),
            callback_timeout_s=callback_timeout,
            cleanup_response=bool(mcp_cleanup_response),
        )

    return _invoke_gemini_cli(
        prompt=prompt,
        session_id=session_id,
        stream=stream,
        workdir=workdir,
        model=model,
        approval_mode=approval_mode,
        sandbox=sandbox,
        yolo=yolo,
        allowed_tools=allowed_tools,
        output_format=output_format,
        raw_output=raw_output,
        auth_mode=auth_mode,
        no_browser=no_browser,
        proxy=proxy,
        no_proxy=no_proxy,
        print_stderr=print_stderr,
        event_hook=event_hook,
        timeout_level=timeout_level,
        idle_timeout_s=idle_timeout_s,
        max_timeout_s=max_timeout_s,
        terminate_grace_s=terminate_grace_s,
    )
