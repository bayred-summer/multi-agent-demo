"""Protocol validators for strict JSON-schema-based agent outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from . import errors as err
from .models import (
    ALLOWED_ACCEPTANCE,
    ALLOWED_GATE_DECISION,
    ALLOWED_ROLES,
    ALLOWED_STATUS,
    DELIVERY_SCHEMA_VERSION,
    ENVELOPE_SCHEMA_VERSION,
    PLAN_SCHEMA_VERSION,
    REVIEW_SCHEMA_VERSION,
    build_delivery_content,
    build_plan_content,
    build_review_content,
)

REVIEW_AGENTS = {"stella"}
PLAN_AGENTS = {"duffy"}


@dataclass
class ProtocolValidationResult:
    """Validation result with structured diagnostics."""

    ok: bool
    errors: List[Dict[str, Any]]
    warnings: List[str]
    parsed_content: Optional[Dict[str, Any]] = None


def build_agent_output_schema(current_agent: str) -> Dict[str, Any]:
    """Return JSON Schema for one agent output payload."""
    if current_agent in REVIEW_AGENTS:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "status",
                "acceptance",
                "verification",
                "root_cause",
                "issues",
                "gate",
                "next_question",
                "warnings",
                "errors",
            ],
            "properties": {
                "schema_version": {
                    "type": "string",
                    "enum": [REVIEW_SCHEMA_VERSION],
                },
                "status": {
                    "type": "string",
                    "enum": sorted(ALLOWED_STATUS),
                },
                "acceptance": {
                    "type": "string",
                    "enum": sorted(ALLOWED_ACCEPTANCE),
                },
                "verification": {
                    "type": "array",
                    "minItems": 2,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["command", "result"],
                        "properties": {
                            "command": {"type": "string"},
                            "result": {"type": "string"},
                        },
                    },
                },
                "root_cause": {"type": "array", "items": {"type": "string"}},
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["severity", "summary"],
                        "properties": {
                            "id": {"type": "string"},
                            "severity": {
                                "type": "string",
                                "enum": ["P0", "P1", "P2"],
                            },
                            "summary": {"type": "string"},
                        },
                    },
                },
                "gate": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["decision", "conditions"],
                    "properties": {
                        "decision": {
                            "type": "string",
                            "enum": sorted(ALLOWED_GATE_DECISION),
                        },
                        "conditions": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "next_question": {
                    "type": "string",
                    "minLength": 1,
                    "pattern": ".*[？?].*",
                },
                "warnings": {"type": "array", "items": {"type": "string"}},
                "errors": {"type": "array", "items": {"type": "string"}},
            },
        }

    if current_agent in PLAN_AGENTS:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "status",
                "result",
                "next_question",
                "warnings",
                "errors",
            ],
            "properties": {
                "schema_version": {
                    "type": "string",
                    "enum": [PLAN_SCHEMA_VERSION],
                },
                "status": {
                    "type": "string",
                    "enum": sorted(ALLOWED_STATUS),
                },
                "result": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "requirement_breakdown",
                        "implementation_scope",
                        "acceptance_criteria",
                        "handoff_notes",
                    ],
                    "properties": {
                        "requirement_breakdown": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string"},
                        },
                        "implementation_scope": {"type": "string"},
                        "acceptance_criteria": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string"},
                        },
                        "handoff_notes": {"type": "string"},
                    },
                },
                "next_question": {
                    "type": "string",
                    "minLength": 1,
                    "pattern": ".*[？?].*",
                },
                "warnings": {"type": "array", "items": {"type": "string"}},
                "errors": {"type": "array", "items": {"type": "string"}},
            },
        }

    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "status",
            "result",
            "next_question",
            "warnings",
            "errors",
        ],
        "properties": {
            "schema_version": {
                "type": "string",
                "enum": [DELIVERY_SCHEMA_VERSION],
            },
            "status": {
                "type": "string",
                "enum": sorted(ALLOWED_STATUS),
            },
            "result": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "task_understanding",
                    "implementation_plan",
                    "execution_evidence",
                    "risks_and_rollback",
                ],
                "properties": {
                    "task_understanding": {"type": "string"},
                    "implementation_plan": {"type": "string"},
                    "execution_evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["command", "result"],
                            "properties": {
                                "command": {"type": "string"},
                                "result": {"type": "string"},
                            },
                        },
                    },
                    "risks_and_rollback": {"type": "string"},
                },
            },
            "next_question": {
                "type": "string",
                "minLength": 1,
                "pattern": ".*[？?].*",
            },
            "warnings": {"type": "array", "items": {"type": "string"}},
            "errors": {"type": "array", "items": {"type": "string"}},
        },
    }


def _append_error(errors: List[Dict[str, Any]], code: str, message: str) -> None:
    errors.append({"code": code, "message": message})


def _validate_envelope(envelope: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Validate core envelope shape."""
    errors: List[Dict[str, Any]] = []
    required = (
        "message_id",
        "trace_id",
        "schema_version",
        "sender",
        "recipient",
        "role",
        "timestamp",
        "content",
    )
    for key in required:
        if key not in envelope:
            _append_error(errors, err.E_SCHEMA_MISSING_FIELD, f"envelope missing field: {key}")

    if envelope.get("schema_version") != ENVELOPE_SCHEMA_VERSION:
        _append_error(errors, err.E_SCHEMA_INVALID_ENUM, "invalid envelope schema_version")

    if envelope.get("role") not in ALLOWED_ROLES:
        _append_error(errors, err.E_SCHEMA_INVALID_ENUM, "invalid envelope role")

    return errors


def _role_for_agent(current_agent: str) -> str:
    if current_agent in REVIEW_AGENTS:
        return "review"
    if current_agent in PLAN_AGENTS:
        return "observation"
    return "final"


def validate_json_protocol_content(
    *,
    current_agent: str,
    peer_display: str,
    payload: Dict[str, Any],
    trace_id: str,
) -> ProtocolValidationResult:
    """Validate structured JSON protocol payload for one agent output."""
    errors: List[Dict[str, Any]] = []
    warnings: List[str] = []

    if not isinstance(payload, dict):
        _append_error(errors, err.E_SCHEMA_INVALID_FORMAT, "payload must be a JSON object")
        return ProtocolValidationResult(ok=False, errors=errors, warnings=warnings, parsed_content=None)

    envelope: Dict[str, Any] = {
        "message_id": f"json-{abs(hash(str(payload)))}",
        "trace_id": trace_id,
        "schema_version": ENVELOPE_SCHEMA_VERSION,
        "sender": current_agent,
        "recipient": peer_display,
        "role": _role_for_agent(current_agent),
        "timestamp": "",
        "content": {},
    }
    errors.extend(_validate_envelope(envelope))

    next_question = payload.get("next_question")
    if not isinstance(next_question, str) or not next_question.strip():
        _append_error(errors, err.E_SCHEMA_MISSING_FIELD, "missing next_question")
    elif "？" not in next_question and "?" not in next_question:
        _append_error(errors, err.E_SCHEMA_INVALID_FORMAT, "next_question must contain question mark")

    if current_agent in REVIEW_AGENTS:
        required_top_keys = {
            "schema_version",
            "status",
            "acceptance",
            "verification",
            "root_cause",
            "issues",
            "gate",
            "next_question",
            "warnings",
            "errors",
        }
        unknown_top_keys = set(payload.keys()) - required_top_keys
        for key in sorted(unknown_top_keys):
            _append_error(errors, err.E_SCHEMA_INVALID_FORMAT, f"unexpected field: {key}")
        missing_top_keys = required_top_keys - set(payload.keys())
        for key in sorted(missing_top_keys):
            _append_error(errors, err.E_SCHEMA_MISSING_FIELD, f"missing field: {key}")

        if payload.get("schema_version") != REVIEW_SCHEMA_VERSION:
            _append_error(errors, err.E_SCHEMA_INVALID_ENUM, "invalid review schema_version")

        acceptance = payload.get("acceptance")
        if acceptance not in ALLOWED_ACCEPTANCE:
            _append_error(errors, err.E_SCHEMA_INVALID_ENUM, "invalid acceptance enum")

        status = payload.get("status")
        if status not in ALLOWED_STATUS:
            _append_error(errors, err.E_SCHEMA_INVALID_ENUM, "invalid status enum")

        verification = payload.get("verification")
        if not isinstance(verification, list):
            verification = []
            _append_error(errors, err.E_SCHEMA_MISSING_FIELD, "verification must be list")

        normalized_verification: List[Dict[str, str]] = []
        for idx, item in enumerate(verification, start=1):
            if not isinstance(item, dict):
                _append_error(
                    errors,
                    err.E_SCHEMA_INVALID_FORMAT,
                    f"invalid verification format at index {idx}",
                )
                continue
            unknown_keys = set(item.keys()) - {"command", "result"}
            if unknown_keys:
                _append_error(
                    errors,
                    err.E_SCHEMA_INVALID_FORMAT,
                    f"verification item {idx} has unexpected field(s): {', '.join(sorted(unknown_keys))}",
                )
            cmd = item.get("command")
            res = item.get("result")
            if isinstance(cmd, str) and isinstance(res, str):
                normalized_verification.append({"command": cmd, "result": res})
                continue
            _append_error(
                errors,
                err.E_SCHEMA_INVALID_FORMAT,
                f"verification item {idx} must include string command/result",
            )

        if len(normalized_verification) < 2:
            _append_error(
                errors,
                err.E_REVIEW_EVIDENCE_MISSING,
                "review requires at least two command/result verification entries",
            )

        issues = payload.get("issues")
        if not isinstance(issues, list):
            issues = []
            _append_error(errors, err.E_SCHEMA_MISSING_FIELD, "issues must be list")
        normalized_issues: List[Dict[str, Any]] = []
        for idx, item in enumerate(issues, start=1):
            if not isinstance(item, dict):
                continue
            severity = item.get("severity")
            summary = item.get("summary")
            if severity not in {"P0", "P1", "P2"} or not isinstance(summary, str):
                _append_error(errors, err.E_SCHEMA_INVALID_FORMAT, f"invalid issue format at index {idx}")
                continue
            normalized_issues.append(
                {
                    "id": str(item.get("id") or f"ISSUE-{idx:03d}"),
                    "severity": severity,
                    "summary": summary,
                }
            )

        gate = payload.get("gate")
        if not isinstance(gate, dict):
            gate = {}
            _append_error(errors, err.E_SCHEMA_MISSING_FIELD, "gate must be object")
        gate_decision = gate.get("decision")
        if gate_decision not in ALLOWED_GATE_DECISION:
            _append_error(errors, err.E_SCHEMA_INVALID_ENUM, "invalid gate decision enum")
        gate_conditions = gate.get("conditions")
        if not isinstance(gate_conditions, list):
            gate_conditions = []
            _append_error(errors, err.E_SCHEMA_INVALID_FORMAT, "gate.conditions must be list")

        if acceptance == "pass" and any(issue.get("severity") in {"P0", "P1"} for issue in normalized_issues):
            _append_error(
                errors,
                err.E_REVIEW_GATE_INCONSISTENT,
                "acceptance=pass is inconsistent with P0/P1 issues",
            )

        parsed = build_review_content(
            status=status if isinstance(status, str) else "failed",
            acceptance=acceptance if isinstance(acceptance, str) else "fail",
            verification=normalized_verification,
            root_cause=[str(x) for x in payload.get("root_cause", [])] if isinstance(payload.get("root_cause"), list) else [],
            issues=normalized_issues,
            gate={
                "decision": gate_decision if isinstance(gate_decision, str) else "block",
                "conditions": [str(x) for x in gate_conditions],
            },
            next_question=next_question.strip() if isinstance(next_question, str) else "",
            warnings=payload.get("warnings") if isinstance(payload.get("warnings"), list) else [],
            errors=errors,
        )
        return ProtocolValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings, parsed_content=parsed)

    if current_agent in PLAN_AGENTS:
        required_top_keys = {
            "schema_version",
            "status",
            "result",
            "next_question",
            "warnings",
            "errors",
        }
        unknown_top_keys = set(payload.keys()) - required_top_keys
        for key in sorted(unknown_top_keys):
            _append_error(errors, err.E_SCHEMA_INVALID_FORMAT, f"unexpected field: {key}")
        missing_top_keys = required_top_keys - set(payload.keys())
        for key in sorted(missing_top_keys):
            _append_error(errors, err.E_SCHEMA_MISSING_FIELD, f"missing field: {key}")

        if payload.get("schema_version") != PLAN_SCHEMA_VERSION:
            _append_error(errors, err.E_SCHEMA_INVALID_ENUM, "invalid plan schema_version")
        status = payload.get("status")
        if status not in ALLOWED_STATUS:
            _append_error(errors, err.E_SCHEMA_INVALID_ENUM, "invalid status enum")

        result = payload.get("result")
        if not isinstance(result, dict):
            result = {}
            _append_error(errors, err.E_SCHEMA_MISSING_FIELD, "result must be object")
        else:
            required_result_keys = {
                "requirement_breakdown",
                "implementation_scope",
                "acceptance_criteria",
                "handoff_notes",
            }
            unknown_result_keys = set(result.keys()) - required_result_keys
            for key in sorted(unknown_result_keys):
                _append_error(errors, err.E_SCHEMA_INVALID_FORMAT, f"unexpected result field: {key}")
            missing_result_keys = required_result_keys - set(result.keys())
            for key in sorted(missing_result_keys):
                _append_error(errors, err.E_SCHEMA_MISSING_FIELD, f"missing result field: {key}")

        raw_breakdown = result.get("requirement_breakdown")
        requirement_breakdown = [str(x) for x in raw_breakdown] if isinstance(raw_breakdown, list) else []
        if not requirement_breakdown:
            _append_error(errors, err.E_SCHEMA_INVALID_FORMAT, "result.requirement_breakdown must be non-empty list")

        raw_criteria = result.get("acceptance_criteria")
        acceptance_criteria = [str(x) for x in raw_criteria] if isinstance(raw_criteria, list) else []
        if not acceptance_criteria:
            _append_error(errors, err.E_SCHEMA_INVALID_FORMAT, "result.acceptance_criteria must be non-empty list")

        parsed_plan = build_plan_content(
            requirement_breakdown=requirement_breakdown,
            implementation_scope=str(result.get("implementation_scope", "")),
            acceptance_criteria=acceptance_criteria,
            handoff_notes=str(result.get("handoff_notes", "")),
            next_question=next_question.strip() if isinstance(next_question, str) else "",
        )
        parsed_plan["status"] = status if isinstance(status, str) else parsed_plan["status"]
        parsed_plan["warnings"] = payload.get("warnings") if isinstance(payload.get("warnings"), list) else []
        parsed_plan["errors"] = payload.get("errors") if isinstance(payload.get("errors"), list) else []

        return ProtocolValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings, parsed_content=parsed_plan)

    required_top_keys = {
        "schema_version",
        "status",
        "result",
        "next_question",
        "warnings",
        "errors",
    }
    unknown_top_keys = set(payload.keys()) - required_top_keys
    for key in sorted(unknown_top_keys):
        _append_error(errors, err.E_SCHEMA_INVALID_FORMAT, f"unexpected field: {key}")
    missing_top_keys = required_top_keys - set(payload.keys())
    for key in sorted(missing_top_keys):
        _append_error(errors, err.E_SCHEMA_MISSING_FIELD, f"missing field: {key}")

    if payload.get("schema_version") != DELIVERY_SCHEMA_VERSION:
        _append_error(errors, err.E_SCHEMA_INVALID_ENUM, "invalid delivery schema_version")
    status = payload.get("status")
    if status not in ALLOWED_STATUS:
        _append_error(errors, err.E_SCHEMA_INVALID_ENUM, "invalid status enum")

    result = payload.get("result")
    if not isinstance(result, dict):
        result = {}
        _append_error(errors, err.E_SCHEMA_MISSING_FIELD, "result must be object")
    else:
        required_result_keys = {
            "task_understanding",
            "implementation_plan",
            "execution_evidence",
            "risks_and_rollback",
        }
        unknown_result_keys = set(result.keys()) - required_result_keys
        for key in sorted(unknown_result_keys):
            _append_error(errors, err.E_SCHEMA_INVALID_FORMAT, f"unexpected result field: {key}")
        missing_result_keys = required_result_keys - set(result.keys())
        for key in sorted(missing_result_keys):
            _append_error(errors, err.E_SCHEMA_MISSING_FIELD, f"missing result field: {key}")

    execution_evidence = result.get("execution_evidence")
    normalized_evidence: List[Dict[str, str]] = []
    if isinstance(execution_evidence, list):
        for idx, item in enumerate(execution_evidence, start=1):
            if not isinstance(item, dict):
                _append_error(
                    errors,
                    err.E_SCHEMA_INVALID_FORMAT,
                    f"invalid execution_evidence format at index {idx}",
                )
                continue
            unknown_keys = set(item.keys()) - {"command", "result"}
            if unknown_keys:
                _append_error(
                    errors,
                    err.E_SCHEMA_INVALID_FORMAT,
                    f"execution_evidence item {idx} has unexpected field(s): {', '.join(sorted(unknown_keys))}",
                )
            cmd = item.get("command")
            res = item.get("result")
            if isinstance(cmd, str) and isinstance(res, str):
                normalized_evidence.append({"command": cmd, "result": res})
                continue
            _append_error(
                errors,
                err.E_SCHEMA_INVALID_FORMAT,
                f"execution_evidence item {idx} must include string command/result",
            )
    else:
        _append_error(errors, err.E_SCHEMA_INVALID_FORMAT, "result.execution_evidence must be list")

    parsed_delivery = build_delivery_content(
        task_understanding=str(result.get("task_understanding", "")),
        implementation_plan=str(result.get("implementation_plan", "")),
        execution_evidence=normalized_evidence,
        risks_and_rollback=str(result.get("risks_and_rollback", "")),
        next_question=next_question.strip() if isinstance(next_question, str) else "",
    )
    parsed_delivery["status"] = status if isinstance(status, str) else parsed_delivery["status"]
    parsed_delivery["warnings"] = payload.get("warnings") if isinstance(payload.get("warnings"), list) else []
    parsed_delivery["errors"] = payload.get("errors") if isinstance(payload.get("errors"), list) else []

    return ProtocolValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings, parsed_content=parsed_delivery)
