"""会话持久化工具。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# 会话缓存放在项目目录下，做到“项目级隔离”。
SESSION_FILE = Path.cwd() / ".sessions" / "session-store.json"


def load_session_store() -> Dict[str, Any]:
    """从磁盘读取会话缓存。

    若文件不存在、JSON 损坏或类型不合法，则返回空字典。
    """
    try:
        raw = SESSION_FILE.read_text(encoding="utf-8")
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
        return {}
    except Exception:
        # 读取异常时走空缓存，避免影响主流程。
        return {}


def save_session_store(store: Dict[str, Any]) -> None:
    """把完整会话缓存写回磁盘。"""
    # 先确保父目录存在，再落盘。
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(
        json.dumps(store, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


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
