"""Core protocol models (envelope + role schemas)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

ENVELOPE_SCHEMA_VERSION = "friendsbar.envelope.v1"
TASK_SCHEMA_VERSION = "friendsbar.task.v1"
DELIVERY_SCHEMA_VERSION = "friendsbar.delivery.v1"
REVIEW_SCHEMA_VERSION = "friendsbar.review.v1"

ALLOWED_ROLES = {"task", "review", "final", "error", "observation"}
ALLOWED_STATUS = {"ok", "partial", "failed"}
ALLOWED_ACCEPTANCE = {"pass", "conditional", "fail"}
ALLOWED_GATE_DECISION = {"allow", "conditional", "block"}


def utc_now_iso() -> str:
    """Return UTC timestamp in ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


def build_task_envelope(
    *,
    trace_id: str,
    sender: str,
    recipient: str,
    intent: str,
    user_request: str,
    workdir: str,
    timeout_level: Optional[str],
    expected_schema_version: str,
) -> Dict[str, Any]:
    """Create one task envelope for orchestrator -> agent."""
    return {
        "message_id": uuid.uuid4().hex,
        "trace_id": trace_id,
        "schema_version": ENVELOPE_SCHEMA_VERSION,
        "sender": sender,
        "recipient": recipient,
        "role": "task",
        "timestamp": utc_now_iso(),
        "content": {
            "schema_version": TASK_SCHEMA_VERSION,
            "intent": intent,
            "inputs": {
                "user_request": user_request,
                "workdir": workdir,
            },
            "constraints": {
                "timeout_level": timeout_level,
            },
            "expected_outputs": {
                "schema_version": expected_schema_version,
            },
        },
        "attachments": [],
        "meta": {},
    }


def build_delivery_content(
    *,
    task_understanding: str,
    implementation_plan: str,
    execution_evidence: List[Dict[str, str]],
    risks_and_rollback: str,
    next_question: str,
) -> Dict[str, Any]:
    """Create normalized delivery content."""
    return {
        "schema_version": DELIVERY_SCHEMA_VERSION,
        "status": "ok" if execution_evidence else "partial",
        "result": {
            "task_understanding": task_understanding,
            "implementation_plan": implementation_plan,
            "execution_evidence": execution_evidence,
            "risks_and_rollback": risks_and_rollback,
        },
        "warnings": [],
        "errors": [],
        "next_question": next_question,
    }


def build_review_content(
    *,
    status: str,
    acceptance: str,
    verification: List[Dict[str, str]],
    root_cause: List[str],
    issues: List[Dict[str, Any]],
    gate: Dict[str, Any],
    next_question: str,
    warnings: Optional[List[str]] = None,
    errors: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Create normalized review content."""
    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "status": status,
        "acceptance": acceptance,
        "verification": verification,
        "root_cause": root_cause,
        "issues": issues,
        "gate": gate,
        "next_question": next_question,
        "warnings": warnings or [],
        "errors": errors or [],
    }
