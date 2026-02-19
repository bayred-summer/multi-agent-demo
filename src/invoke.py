"""Unified invoke entry for CLI providers."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

from src.providers.claude_minimax import invoke_claude_minimax
from src.providers.codex import invoke_codex
from src.utils.process_runner import ProcessExecutionError
from src.utils.runtime_config import load_runtime_config
from src.utils.session_store import get_session_id, set_session_id

ProviderFn = Callable[..., Dict[str, Any]]

# Implemented providers.
PROVIDERS: Dict[str, ProviderFn] = {
    "codex": invoke_codex,
    "claude-minimax": invoke_claude_minimax,
}

# External aliases -> provider keys.
CLI_ALIASES = {
    "claude_minimax": "claude-minimax",
    "linabell": "codex",
    "duffy": "claude-minimax",
    "玲娜贝儿": "codex",
    "达菲": "claude-minimax",
    # Backward-compatible mojibake aliases.
    "짎쳹괔랿": "codex",
    "댄뷅": "claude-minimax",
}

SUPPORTED_CLIS = tuple(sorted(set(PROVIDERS.keys()) | set(CLI_ALIASES.keys())))


def _normalize_cli(cli: str) -> str:
    """Normalize external CLI alias to provider key."""
    raw = (cli or "").strip()
    if raw in CLI_ALIASES:
        return CLI_ALIASES[raw]
    lower_raw = raw.lower()
    return CLI_ALIASES.get(lower_raw, lower_raw)


def _is_retryable_process_error(error: ProcessExecutionError) -> bool:
    """Return True if process error is likely transient."""
    if error.reason in {"idle_timeout", "max_timeout"}:
        return True
    if error.reason != "nonzero_exit":
        return False

    stderr_text = " ".join(error.stderr_tail).lower()
    retry_keywords = (
        "timeout",
        "temporarily",
        "try again",
        "429",
        "503",
        "504",
        "connection",
        "network",
        "rate limit",
    )
    return any(keyword in stderr_text for keyword in retry_keywords)


def invoke(
    cli: str,
    prompt: str,
    *,
    use_session: Optional[bool] = None,
    stream: Optional[bool] = None,
    workdir: Optional[str] = None,
    provider_options: Optional[Dict[str, Any]] = None,
    timeout_level: Optional[str] = None,
    idle_timeout_s: Optional[float] = None,
    max_timeout_s: Optional[float] = None,
    terminate_grace_s: Optional[float] = None,
    retry_attempts: Optional[int] = None,
    retry_backoff_s: Optional[float] = None,
    config_path: str = "config.toml",
) -> Dict[str, Any]:
    """Invoke one provider through a unified interface."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")

    provider_name = _normalize_cli(cli)
    provider = PROVIDERS.get(provider_name)
    if provider is None:
        supported = ", ".join(SUPPORTED_CLIS)
        raise ValueError(f"Unsupported cli: {cli}. Supported: {supported}")

    runtime_config = load_runtime_config(config_path=config_path)
    defaults = runtime_config.get("defaults", {})
    provider_config = runtime_config.get("providers", {}).get(provider_name, {})
    timeout_profiles = runtime_config.get("timeouts", {})

    resolved_use_session = (
        bool(defaults.get("use_session", True)) if use_session is None else use_session
    )
    resolved_stream = bool(defaults.get("stream", True)) if stream is None else stream

    resolved_timeout_level = timeout_level or provider_config.get(
        "timeout_level", defaults.get("timeout_level", "standard")
    )
    timeout_profile = timeout_profiles.get(
        resolved_timeout_level, timeout_profiles.get("standard", {})
    )

    resolved_idle_timeout_s = (
        idle_timeout_s
        if idle_timeout_s is not None
        else timeout_profile.get("idle_timeout_s")
    )
    resolved_max_timeout_s = (
        max_timeout_s if max_timeout_s is not None else timeout_profile.get("max_timeout_s")
    )
    resolved_terminate_grace_s = (
        terminate_grace_s
        if terminate_grace_s is not None
        else timeout_profile.get("terminate_grace_s")
    )

    resolved_retry_attempts = (
        retry_attempts
        if retry_attempts is not None
        else provider_config.get("retry_attempts", defaults.get("retry_attempts", 1))
    )
    resolved_retry_backoff_s = (
        retry_backoff_s
        if retry_backoff_s is not None
        else defaults.get("retry_backoff_s", 1.0)
    )

    if int(resolved_retry_attempts) < 0:
        raise ValueError("retry_attempts must be >= 0")

    last_session_id = get_session_id(provider_name) if resolved_use_session else None

    attempt = 0
    while True:
        try:
            result = provider(
                prompt=prompt,
                session_id=last_session_id,
                stream=resolved_stream,
                workdir=workdir,
                **(provider_options or {}),
                timeout_level=resolved_timeout_level,
                idle_timeout_s=resolved_idle_timeout_s,
                max_timeout_s=resolved_max_timeout_s,
                terminate_grace_s=resolved_terminate_grace_s,
            )
            attempt_count = attempt
            break
        except ProcessExecutionError as error:
            if attempt >= int(resolved_retry_attempts) or not _is_retryable_process_error(error):
                raise
            wait_s = float(resolved_retry_backoff_s) * (2**attempt)
            if resolved_stream:
                print(
                    f"[retry] provider={provider_name}, attempt={attempt + 1}/{resolved_retry_attempts}, "
                    f"reason={error.reason}, wait={wait_s:.1f}s",
                )
            time.sleep(wait_s)
            attempt += 1

    new_session_id = result.get("session_id")
    if resolved_use_session and isinstance(new_session_id, str) and new_session_id.strip():
        set_session_id(provider_name, new_session_id)

    return {
        "cli": provider_name,
        "prompt": prompt,
        "text": result.get("text", ""),
        "session_id": new_session_id if isinstance(new_session_id, str) else None,
        "elapsed_ms": result.get("elapsed_ms"),
        "timeout_level": resolved_timeout_level,
        "retry_count": attempt_count,
    }
