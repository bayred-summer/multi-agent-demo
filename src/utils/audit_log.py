"""Audit logging utilities for Friends Bar orchestration."""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _utc_now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: Any, fallback: int) -> int:
    """Best-effort int conversion."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def text_meta(text: str, *, include_preview: bool, max_preview_chars: int) -> Dict[str, Any]:
    """Build debugging metadata for text payloads."""
    value = text or ""
    meta: Dict[str, Any] = {
        "chars": len(value),
        "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
    }
    if include_preview:
        meta["preview"] = value[:_safe_int(max_preview_chars, 1200)]
    return meta


@dataclass
class AuditLogConfig:
    """Runtime configuration for audit logging."""

    enabled: bool = True
    log_dir: str = ".friends-bar/logs"
    include_prompt_preview: bool = True
    max_preview_chars: int = 1200

    @classmethod
    def from_runtime_config(
        cls,
        friends_bar_config: Dict[str, Any],
    ) -> "AuditLogConfig":
        """Load logger config from `[friends_bar.logging]`."""
        raw = friends_bar_config.get("logging", {})
        if not isinstance(raw, dict):
            raw = {}
        return cls(
            enabled=bool(raw.get("enabled", True)),
            log_dir=str(raw.get("dir", ".friends-bar/logs")),
            include_prompt_preview=bool(raw.get("include_prompt_preview", True)),
            max_preview_chars=_safe_int(raw.get("max_preview_chars", 1200), 1200),
        )


class AuditLogger:
    """Append-only JSONL logger for one Friends Bar run."""

    def __init__(self, config: AuditLogConfig, *, seed: Optional[int] = None) -> None:
        self._enabled = bool(config.enabled)
        self._include_prompt_preview = bool(config.include_prompt_preview)
        self._max_preview_chars = _safe_int(config.max_preview_chars, 1200)
        self.run_id = uuid.uuid4().hex
        if seed is None:
            self.seed = secrets.randbits(32)
        else:
            try:
                self.seed = int(seed)
            except (TypeError, ValueError):
                self.seed = secrets.randbits(32)
        self._created_at = _utc_now_iso()
        self.log_file: Optional[Path] = None
        self.summary_file: Optional[Path] = None

        if not self._enabled:
            return

        base_dir = Path(config.log_dir)
        if not base_dir.is_absolute():
            base_dir = Path.cwd() / base_dir
        base_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        file_stem = f"{timestamp}_{self.run_id}"
        self.log_file = base_dir / f"{file_stem}.jsonl"
        self.summary_file = base_dir / f"{file_stem}.summary.json"

    @property
    def enabled(self) -> bool:
        """Whether logger is enabled."""
        return self._enabled

    @property
    def include_prompt_preview(self) -> bool:
        """Whether prompt preview should be stored."""
        return self._include_prompt_preview

    @property
    def max_preview_chars(self) -> int:
        """Max chars for text preview."""
        return self._max_preview_chars

    def _write_jsonl(self, record: Dict[str, Any]) -> None:
        if not self._enabled or self.log_file is None:
            return
        try:
            with self.log_file.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            # Logging failures must not break main workflow.
            return

    def log(self, event: str, payload: Dict[str, Any]) -> None:
        """Write one structured event."""
        if not self._enabled:
            return
        record = {
            "ts": _utc_now_iso(),
            "run_id": self.run_id,
            "seed": self.seed,
            "event": event,
            "payload": payload,
        }
        self._write_jsonl(record)

    def finalize(self, *, status: str, summary: Dict[str, Any]) -> None:
        """Write run summary and final JSON event."""
        if not self._enabled:
            return

        payload = {
            "status": status,
            "started_at": self._created_at,
            "ended_at": _utc_now_iso(),
            "seed": self.seed,
            **summary,
        }
        self.log("run.finalized", payload)

        if self.summary_file is None:
            return
        try:
            self.summary_file.write_text(
                json.dumps(
                    {
                        "run_id": self.run_id,
                        "seed": self.seed,
                        **payload,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            return
