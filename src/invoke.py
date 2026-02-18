"""统一调用入口。

对外暴露 `invoke(cli, prompt)`，屏蔽不同 provider 的实现差异。
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

from src.providers.claude_minimax import invoke_claude_minimax
from src.providers.codex import invoke_codex
from src.providers.xxx import invoke_xxx
from src.utils.process_runner import ProcessExecutionError
from src.utils.runtime_config import load_runtime_config
from src.utils.session_store import get_session_id, set_session_id

ProviderFn = Callable[..., Dict[str, Any]]

# 只保留“规范名称”，避免会话 key 分叉。
PROVIDERS: Dict[str, ProviderFn] = {
    "codex": invoke_codex,
    "claude-minimax": invoke_claude_minimax,
    "xxx": invoke_xxx,
}

# 对外兼容别名输入，但内部统一映射到规范名称。
CLI_ALIASES = {
    "claude_minimax": "claude-minimax",
}

SUPPORTED_CLIS = tuple(sorted(set(PROVIDERS.keys()) | set(CLI_ALIASES.keys())))


def _normalize_cli(cli: str) -> str:
    """把外部输入的 cli 名称标准化为内部规范 key。"""
    raw = (cli or "").strip().lower()
    return CLI_ALIASES.get(raw, raw)


def _is_retryable_process_error(error: ProcessExecutionError) -> bool:
    """判断异常是否适合自动重试。"""
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
    timeout_level: Optional[str] = None,
    idle_timeout_s: Optional[float] = None,
    max_timeout_s: Optional[float] = None,
    terminate_grace_s: Optional[float] = None,
    retry_attempts: Optional[int] = None,
    retry_backoff_s: Optional[float] = None,
    config_path: str = "config.toml",
) -> Dict[str, Any]:
    """统一执行 provider 调用。

    参数：
    - timeout_level: quick / standard / complex
    - idle_timeout_s / max_timeout_s / terminate_grace_s: 显式覆盖超时配置
    - retry_attempts: 失败后最多重试次数（不含首次）
    """
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

    last_session_id = (
        get_session_id(provider_name) if resolved_use_session else None
    )

    attempt = 0
    while True:
        try:
            result = provider(
                prompt=prompt,
                session_id=last_session_id,
                stream=resolved_stream,
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
