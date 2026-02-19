"""会话持久化工具。"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# 会话缓存放在项目目录下，做到“项目级隔离”。
SESSION_FILE = Path.cwd() / ".sessions" / "session-store.json"
DEBUG_ENV = "FRIENDS_BAR_DEBUG"


def _debug_log(message: str) -> None:
    """Print optional debug logs when FRIENDS_BAR_DEBUG is enabled."""
    if os.environ.get(DEBUG_ENV):
        print(f"[session_store] {message}", file=sys.stderr)


def load_session_store() -> Dict[str, Any]:
    """从磁盘读取会话缓存。

    若文件不存在、JSON 损坏或类型不合法，则返回空字典。
    """
    if not SESSION_FILE.exists():
        return {}

    try:
        raw = SESSION_FILE.read_text(encoding="utf-8")
        parsed = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        # 读取异常时走空缓存，避免影响主流程。
        _debug_log(f"load failed, fallback to empty store: {exc}")
        return {}

    if isinstance(parsed, dict):
        return parsed

    _debug_log("invalid store type, fallback to empty store")
    return {}


def save_session_store(store: Dict[str, Any]) -> None:
    """把完整会话缓存写回磁盘。"""
    # 先确保父目录存在，再原子落盘（temp -> replace）。
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(store, indent=2, ensure_ascii=False)
    tmp_file = SESSION_FILE.with_name(
        f".{SESSION_FILE.name}.tmp-{os.getpid()}-{int(datetime.now(timezone.utc).timestamp() * 1_000_000)}"
    )

    try:
        tmp_file.write_text(payload, encoding="utf-8")
        os.replace(tmp_file, SESSION_FILE)
    finally:
        if tmp_file.exists():
            try:
                tmp_file.unlink()
            except OSError as exc:
                _debug_log(f"cleanup temp file failed: {exc}")


def get_session_id(provider: str) -> Optional[str]:
    """读取某个 provider 对应的 session_id。"""
    store = load_session_store()
    value = store.get(provider, {})
    if isinstance(value, dict):
        session_id = value.get("sessionId")
        if isinstance(session_id, str) and session_id.strip():
            return session_id
    return None


def set_session_id(provider: str, session_id: str) -> None:
    """更新某个 provider 的 session_id 并写盘。"""
    store = load_session_store()
    store[provider] = {
        "sessionId": session_id,
        # 使用 UTC 时间，便于跨时区排查问题。
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    save_session_store(store)
