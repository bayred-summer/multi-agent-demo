"""Persistent provider session store utilities."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

SESSION_FILE = Path.cwd() / ".sessions" / "session-store.json"
DEBUG_ENV = "FRIENDS_BAR_DEBUG"


def _debug_log(message: str) -> None:
    """Print optional debug logs when FRIENDS_BAR_DEBUG is enabled."""
    if os.environ.get(DEBUG_ENV):
        print(f"[session_store] {message}", file=sys.stderr)


def load_session_store() -> Dict[str, Any]:
    """Load full session store from disk."""
    if not SESSION_FILE.exists():
        return {}

    try:
        raw = SESSION_FILE.read_text(encoding="utf-8")
        parsed = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _debug_log(f"load failed, fallback to empty store: {exc}")
        return {}

    if isinstance(parsed, dict):
        return parsed

    _debug_log("invalid store type, fallback to empty store")
    return {}


def save_session_store(store: Dict[str, Any]) -> None:
    """Atomically save full session store to disk."""
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
    """Read one provider session id."""
    store = load_session_store()
    value = store.get(provider, {})
    if isinstance(value, dict):
        session_id = value.get("sessionId")
        if isinstance(session_id, str) and session_id.strip():
            return session_id
    return None


def set_session_id(provider: str, session_id: str) -> None:
    """Update one provider session id and save."""
    store = load_session_store()
    store[provider] = {
        "sessionId": session_id,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    save_session_store(store)


def clear_session_id(provider: str) -> None:
    """Delete one provider session mapping."""
    store = load_session_store()
    if provider in store:
        del store[provider]
        save_session_store(store)
