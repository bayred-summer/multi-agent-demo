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
    use_session: bool = True,
    stream: bool = True,
    timeout_level: str = "standard",
    idle_timeout_s: Optional[float] = None,
    max_timeout_s: Optional[float] = None,
    terminate_grace_s: Optional[float] = None,
    retry_attempts: int = 1,
    retry_backoff_s: float = 1.0,
) -> Dict[str, Any]:
    """统一执行 provider 调用。

    参数：
    - timeout_level: quick / standard / complex
    - idle_timeout_s / max_timeout_s / terminate_grace_s: 显式覆盖超时配置
    - retry_attempts: 失败后最多重试次数（不含首次）
    """
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    if retry_attempts < 0:
        raise ValueError("retry_attempts must be >= 0")

    provider_name = _normalize_cli(cli)
    provider = PROVIDERS.get(provider_name)
    if provider is None:
        supported = ", ".join(SUPPORTED_CLIS)
        raise ValueError(f"Unsupported cli: {cli}. Supported: {supported}")

    last_session_id = get_session_id(provider_name) if use_session else None

    attempt = 0
    while True:
        try:
            result = provider(
                prompt=prompt,
                session_id=last_session_id,
                stream=stream,
                timeout_level=timeout_level,
                idle_timeout_s=idle_timeout_s,
                max_timeout_s=max_timeout_s,
                terminate_grace_s=terminate_grace_s,
            )
            break
        except ProcessExecutionError as error:
            if attempt >= retry_attempts or not _is_retryable_process_error(error):
                raise
            wait_s = retry_backoff_s * (2**attempt)
            if stream:
                print(
                    f"[retry] provider={provider_name}, attempt={attempt + 1}/{retry_attempts}, "
                    f"reason={error.reason}, wait={wait_s:.1f}s",
                )
            time.sleep(wait_s)
            attempt += 1

    new_session_id = result.get("session_id")
    if use_session and isinstance(new_session_id, str) and new_session_id.strip():
        set_session_id(provider_name, new_session_id)

    return {
        "cli": provider_name,
        "prompt": prompt,
        "text": result.get("text", ""),
        "session_id": new_session_id if isinstance(new_session_id, str) else None,
        "elapsed_ms": result.get("elapsed_ms"),
    }

