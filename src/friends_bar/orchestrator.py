"""Friends Bar Phase0: multi-agent orchestration and prompt protocol."""

from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path
import sys
import time
import traceback
from typing import Any, Dict, List, Optional

from src.friends_bar.agents import (
    AGENTS,
    DUFFY,
    LINA_BELL,
    STELLA,
    display_agent_name,
    normalize_agent_name,
)
from src.invoke import invoke
from src.protocol.models import (
    DELIVERY_SCHEMA_VERSION,
    PLAN_SCHEMA_VERSION,
    REVIEW_SCHEMA_VERSION,
    build_task_envelope,
)
from src.protocol.validators import (
    build_agent_output_schema,
    validate_json_protocol_content,
)
from src.utils.audit_log import AuditLogConfig, AuditLogger, text_meta
from src.utils.runtime_config import load_runtime_config

# Phase0: fixed three-agent order (PM -> Dev -> Reviewer).
AGENT_TURN_ORDER = (DUFFY, LINA_BELL, STELLA)
# Keep retries small but non-zero for strict schema re-generation.
MAX_PROTOCOL_RETRY = 3
_UNIX_PATH_ALLOWED_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-/"
)


def _next_agent(current_name: str) -> str:
    """Return the next agent name by fixed turn order."""
    if current_name not in AGENT_TURN_ORDER:
        return AGENT_TURN_ORDER[0]
    idx = AGENT_TURN_ORDER.index(current_name)
    return AGENT_TURN_ORDER[(idx + 1) % len(AGENT_TURN_ORDER)]


def _expected_schema_for_agent(agent_name: str) -> str:
    """Return expected schema version for the target agent."""
    if agent_name == DUFFY:
        return PLAN_SCHEMA_VERSION
    if agent_name == STELLA:
        return REVIEW_SCHEMA_VERSION
    return DELIVERY_SCHEMA_VERSION


def _path_within(child: Path, parent: Path) -> bool:
    """Return True if child is within parent (resolved, case-safe)."""
    try:
        child_resolved = child.resolve()
        parent_resolved = parent.resolve()
    except OSError:
        return False
    child_parts = tuple(os.path.normcase(part) for part in child_resolved.parts)
    parent_parts = tuple(os.path.normcase(part) for part in parent_resolved.parts)
    if len(parent_parts) > len(child_parts):
        return False
    return child_parts[: len(parent_parts)] == parent_parts


def _ensure_allowed_roots(project_path: str, allowed_roots: List[str]) -> None:
    """Ensure project_path stays within configured allowed roots."""
    if not allowed_roots:
        return
    project = Path(project_path)
    for root in allowed_roots:
        if not root:
            continue
        if _path_within(project, Path(root)):
            return
    raise ValueError(f"project_path is outside allowed_roots: {project_path}")


def _collect_commands(protocol_content: Dict[str, Any], agent_name: str) -> List[str]:
    """Collect command strings from structured protocol output."""
    commands: List[str] = []
    if agent_name == STELLA:
        verification = protocol_content.get("verification", [])
        if isinstance(verification, list):
            for item in verification:
                if isinstance(item, dict) and isinstance(item.get("command"), str):
                    commands.append(item["command"])
        return commands

    result = protocol_content.get("result", {})
    if isinstance(result, dict):
        evidence = result.get("execution_evidence", [])
        if isinstance(evidence, list):
            for item in evidence:
                if isinstance(item, dict) and isinstance(item.get("command"), str):
                    commands.append(item["command"])
    return commands


def _command_policy_errors(
    commands: List[str],
    *,
    allowlist: List[str],
    denylist: List[str],
) -> List[str]:
    """Validate command strings against allow/deny lists."""
    errors: List[str] = []
    allow_patterns = [re.compile(pat) for pat in allowlist if pat]
    deny_patterns = [re.compile(pat) for pat in denylist if pat]

    for cmd in commands:
        if any(pat.search(cmd) for pat in deny_patterns):
            errors.append(f"E_SAFETY_COMMAND_DENIED: {cmd}")
            continue
        if allow_patterns and not any(pat.search(cmd) for pat in allow_patterns):
            errors.append(f"E_SAFETY_COMMAND_NOT_ALLOWED: {cmd}")
    return errors


def _extract_requested_workdir(user_request: str) -> Optional[str]:
    """Best-effort extract absolute workdir path from user request text."""
    text = (user_request or "").strip()
    if not text:
        return None

    candidates: List[str] = []
    idx = 0
    while idx < len(text):
        if text[idx] != "/":
            idx += 1
            continue
        prev = text[idx - 1] if idx > 0 else ""
        # Skip URL separators like "https://..."
        if prev in {":", "/"}:
            idx += 1
            continue

        end = idx
        while end < len(text) and text[end] in _UNIX_PATH_ALLOWED_CHARS:
            end += 1
        candidate = text[idx:end].rstrip("/")
        if candidate and len(candidate) > 1:
            candidates.append(candidate)
        idx = max(end, idx + 1)

    # Prefer deeper/longer paths first.
    for candidate in sorted(set(candidates), key=len, reverse=True):
        path = Path(candidate)
        if path.exists() and path.is_dir():
            return str(path)
        parent = path.parent
        if parent != path and parent.exists() and parent.is_dir():
            return str(path)
    return None


def _resolve_workdir(*, project_path: Optional[str], user_request: str) -> tuple[str, str]:
    """Resolve unified workdir and explain the source."""
    if project_path is not None:
        return str(Path(project_path)), "project_path_arg"

    inferred = _extract_requested_workdir(user_request)
    if inferred:
        return str(Path(inferred)), "user_request"

    return str(Path.cwd()), "cwd_default"


def _extract_absolute_paths_from_command(command: str) -> List[str]:
    """Extract absolute filesystem paths embedded in a shell-like command string."""
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()

    extracted: List[str] = []
    for token in tokens:
        raw = str(token or "").strip()
        if not raw:
            continue

        candidates = [raw]
        # Handle flag/value forms like "--file=/abs/path".
        if raw.startswith("-") and "=" in raw:
            candidates.append(raw.split("=", 1)[1].strip())

        for value in candidates:
            normalized = value.strip().strip("'\"`")
            normalized = normalized.lstrip("(").rstrip(";,|&)")
            if not normalized or "://" in normalized:
                continue
            if normalized.startswith("/"):
                extracted.append(normalized)
    return extracted


def _command_workdir_errors(commands: List[str], *, workdir: str) -> List[str]:
    """Reject evidence/verification commands that reference absolute paths outside workdir."""
    errors: List[str] = []
    workdir_path = Path(workdir)

    for cmd in commands:
        outside_paths: List[str] = []
        for raw_path in _extract_absolute_paths_from_command(cmd):
            try:
                resolved = Path(raw_path).resolve()
            except OSError:
                continue
            if not _path_within(resolved, workdir_path):
                outside_paths.append(raw_path)
        if outside_paths:
            errors.append(
                "E_WORKDIR_COMMAND_OUTSIDE: "
                + ", ".join(sorted(set(outside_paths)))
                + f" | cmd={cmd}"
            )
    return errors


def _verify_delivery_deliverables(
    delivery_content: Dict[str, Any],
    *,
    workdir: str,
) -> List[str]:
    """Verify delivery deliverables exist within workdir."""
    errors: List[str] = []
    result = delivery_content.get("result", {}) if isinstance(delivery_content.get("result"), dict) else {}
    deliverables = result.get("deliverables", [])
    if not isinstance(deliverables, list):
        return ["E_DELIVERY_INVALID_DELIVERABLES: deliverables must be list"]
    workdir_path = Path(workdir)

    for idx, item in enumerate(deliverables, start=1):
        if not isinstance(item, dict):
            errors.append(f"E_DELIVERY_INVALID_DELIVERABLES: item {idx} must be object")
            continue
        path_value = item.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            errors.append(f"E_DELIVERY_INVALID_DELIVERABLES: item {idx} missing path")
            continue
        raw_path = Path(path_value)
        resolved_path = raw_path if raw_path.is_absolute() else (workdir_path / raw_path)
        try:
            resolved_path = resolved_path.resolve()
        except OSError:
            errors.append(f"E_DELIVERY_INVALID_DELIVERABLES: item {idx} invalid path {path_value}")
            continue
        if not _path_within(resolved_path, workdir_path):
            errors.append(f"E_DELIVERY_OUTSIDE_WORKDIR: {path_value}")
            continue
        kind = str(item.get("kind", "")).strip().lower()
        if not resolved_path.exists():
            errors.append(f"E_DELIVERY_MISSING_DELIVERABLE: {path_value}")
            continue
        if kind == "dir" and not resolved_path.is_dir():
            errors.append(f"E_DELIVERY_EXPECT_DIR: {path_value}")
            continue
        if kind in {"file", ""} and not resolved_path.is_file():
            errors.append(f"E_DELIVERY_EXPECT_FILE: {path_value}")
            continue
    return errors


def _dump_prompt(
    *,
    prompt: str,
    dump_target: Optional[str],
    run_id: str,
    turn: int,
    agent: str,
) -> Optional[str]:
    """Dump prompt to stdout or file; return path if written."""
    if not dump_target:
        return None
    if dump_target in {"-", "stdout"}:
        print("\n[dump] prompt\n")
        print(prompt)
        return None

    target_path = Path(dump_target)
    if target_path.exists() and target_path.is_dir():
        file_path = target_path / f"prompt_{run_id}_turn{turn}_{agent}.txt"
    else:
        file_path = target_path
        if file_path.suffix == "":
            file_path = file_path / f"prompt_{run_id}_turn{turn}_{agent}.txt"

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(prompt, encoding="utf-8")
    return str(file_path)


def _validate_agent_output(
    *,
    current_agent: str,
    output: str,
    peer_agent: str,
    trace_id: str = "",
) -> tuple[bool, list[str], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Validate strict JSON protocol output and return normalized content."""
    raw = (output or "").strip()
    if not raw:
        return False, ["E_SCHEMA_INVALID_FORMAT: empty output"], None, None

    def _extract_first_json_object(text: str) -> Optional[Dict[str, Any]]:
        decoder = json.JSONDecoder()
        for idx, ch in enumerate(text):
            if ch != "{":
                continue
            try:
                obj, _ = decoder.raw_decode(text[idx:])
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                return obj
        return None

    def _clean_markdown_line(line: str) -> str:
        cleaned = line.strip()
        if not cleaned:
            return ""
        cleaned = re.sub(r"^\s*[-*]\s*", "", cleaned)
        cleaned = re.sub(r"^\s*\d+[.)]\s*", "", cleaned)
        cleaned = cleaned.strip()
        return cleaned

    def _adapt_review_plain_text(text: str, peer: str) -> Optional[Dict[str, Any]]:
        section_pattern = re.compile(
            r"^\s*(?:#{1,6}\s*)?\[(验收结论|核验清单|根因链|问题清单|回归门禁)\]\s*$"
        )
        sections: Dict[str, List[str]] = {
            "验收结论": [],
            "核验清单": [],
            "根因链": [],
            "问题清单": [],
            "回归门禁": [],
        }
        current_section: Optional[str] = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            matched = section_pattern.match(line)
            if matched:
                current_section = matched.group(1)
                continue
            if current_section:
                sections[current_section].append(line)

        if not any(sections.values()):
            return None

        acceptance_text = " ".join(sections["验收结论"]).lower()
        if any(token in acceptance_text for token in ("不通过", "fail", "block")):
            acceptance = "fail"
            status = "failed"
            gate_decision = "block"
        elif any(token in acceptance_text for token in ("有条件", "建议改进", "conditional")):
            acceptance = "conditional"
            status = "partial"
            gate_decision = "conditional"
        else:
            acceptance = "pass"
            status = "ok"
            gate_decision = "allow"

        verification_lines = [
            _clean_markdown_line(line) for line in sections["核验清单"] if _clean_markdown_line(line)
        ]
        verification: List[Dict[str, str]] = []
        for idx, line in enumerate(verification_lines[:2], start=1):
            verification.append(
                {
                    "command": f"static_review_evidence_{idx}",
                    "result": line,
                }
            )
        while len(verification) < 2:
            verification.append(
                {
                    "command": f"static_review_evidence_{len(verification) + 1}",
                    "result": "insufficient explicit evidence in plain-text output",
                }
            )

        root_cause = [
            _clean_markdown_line(line)
            for line in sections["根因链"]
            if _clean_markdown_line(line)
        ][:6]

        issue_lines = [
            _clean_markdown_line(line)
            for line in sections["问题清单"]
            if _clean_markdown_line(line)
        ]
        issues: List[Dict[str, Any]] = []
        for idx, line in enumerate(issue_lines[:8], start=1):
            severity = "P2"
            severity_match = re.search(r"\b(P0|P1|P2)\b", line, flags=re.IGNORECASE)
            if severity_match:
                severity = severity_match.group(1).upper()
            if line.startswith("|"):
                parts = [item.strip() for item in line.strip("|").split("|")]
                if len(parts) >= 3:
                    line = parts[2] or line
            issues.append(
                {
                    "id": f"ISSUE-{idx:03d}",
                    "severity": severity,
                    "summary": line,
                }
            )

        gate_conditions = [
            _clean_markdown_line(line)
            for line in sections["回归门禁"]
            if _clean_markdown_line(line)
        ][:8]

        peer_display = display_agent_name(peer)
        next_question = f"{peer_display}，是否需要我把以上评审项整理为可执行修复清单？"

        return {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "status": status,
            "acceptance": acceptance,
            "verification": verification,
            "root_cause": root_cause,
            "issues": issues,
            "gate": {
                "decision": gate_decision,
                "conditions": gate_conditions,
            },
            "next_question": next_question,
            "warnings": [
                "auto_adapted_from_plain_text_review",
            ],
            "errors": [],
        }

    payload: Optional[Dict[str, Any]]
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        payload = _extract_first_json_object(raw)
        if payload is None and current_agent == STELLA:
            payload = _adapt_review_plain_text(raw, peer_agent)
        if payload is None:
            return (
                False,
                [f"E_SCHEMA_INVALID_FORMAT: output is not valid JSON ({exc.msg})"],
                None,
                None,
            )

    if not isinstance(payload, dict):
        return (
            False,
            ["E_SCHEMA_INVALID_FORMAT: output must be one JSON object"],
            None,
            None,
        )

    peer_display = display_agent_name(peer_agent)
    parsed = validate_json_protocol_content(
        current_agent=current_agent,
        peer_display=peer_display,
        payload=payload,
        trace_id=trace_id,
    )
    if not parsed.ok:
        errors = [f"{item.get('code')}: {item.get('message')}" for item in parsed.errors]
        return False, errors, parsed.parsed_content, payload
    return True, [], parsed.parsed_content, payload


def _safe_print(text: str) -> None:
    """Print text safely when stdout cannot encode the text."""
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        safe_text = text.encode(encoding, errors="replace").decode(
            encoding, errors="replace"
        )
        print(safe_text)


def _truncate_text(text: str, max_chars: int) -> str:
    """Truncate text safely for prompt history summaries."""
    if max_chars <= 0:
        return ""
    raw = (text or "").strip()
    if len(raw) <= max_chars:
        return raw
    return raw[: max_chars - 3] + "..."


def _extract_latest_content(
    transcript: List[Dict[str, Any]],
    schema_version: str,
) -> tuple[Optional[Dict[str, Any]], Optional[int]]:
    """Return the latest protocol content for the given schema version."""
    for item in reversed(transcript):
        content = item.get("protocol_content")
        if isinstance(content, dict) and content.get("schema_version") == schema_version:
            return content, item.get("turn")
    return None, None


def _summarize_delivery(
    content: Dict[str, Any],
    *,
    turn: Optional[int],
    field_max_chars: int,
    evidence_limit: int,
) -> Dict[str, Any]:
    """Summarize delivery payload for history injection."""
    result = content.get("result", {}) if isinstance(content.get("result"), dict) else {}
    evidence = result.get("execution_evidence", [])
    deliverables = result.get("deliverables", [])
    summarized_evidence: List[str] = []
    if isinstance(evidence, list):
        for item in evidence[: max(0, evidence_limit)]:
            if not isinstance(item, dict):
                continue
            cmd = _truncate_text(str(item.get("command", "")), field_max_chars)
            res = _truncate_text(str(item.get("result", "")), field_max_chars)
            if cmd or res:
                summarized_evidence.append(f"{cmd} => {res}".strip())
    summarized_deliverables: List[str] = []
    if isinstance(deliverables, list):
        for item in deliverables[: max(0, evidence_limit)]:
            if not isinstance(item, dict):
                continue
            path_value = _truncate_text(str(item.get("path", "")), field_max_chars)
            kind_value = _truncate_text(str(item.get("kind", "")), field_max_chars)
            summary_value = _truncate_text(str(item.get("summary", "")), field_max_chars)
            if path_value:
                suffix = f" ({kind_value})" if kind_value else ""
                note = f": {summary_value}" if summary_value else ""
                summarized_deliverables.append(f"{path_value}{suffix}{note}".strip())
    return {
        "turn": turn,
        "status": content.get("status"),
        "task_understanding": _truncate_text(
            str(result.get("task_understanding", "")), field_max_chars
        ),
        "implementation_plan": _truncate_text(
            str(result.get("implementation_plan", "")), field_max_chars
        ),
        "execution_evidence": summarized_evidence,
        "deliverables": summarized_deliverables,
        "risks_and_rollback": _truncate_text(
            str(result.get("risks_and_rollback", "")), field_max_chars
        ),
        "next_question": _truncate_text(
            str(content.get("next_question", "")), field_max_chars
        ),
    }


def _summarize_plan(
    content: Dict[str, Any],
    *,
    turn: Optional[int],
    field_max_chars: int,
    list_limit: int,
) -> Dict[str, Any]:
    """Summarize PM planning payload for history injection."""
    result = content.get("result", {}) if isinstance(content.get("result"), dict) else {}

    def _clip_list(values: Any) -> List[str]:
        if not isinstance(values, list):
            return []
        return [
            _truncate_text(str(item), field_max_chars)
            for item in values[: max(0, list_limit)]
        ]

    return {
        "turn": turn,
        "status": content.get("status"),
        "requirement_breakdown": _clip_list(result.get("requirement_breakdown", [])),
        "implementation_scope": _truncate_text(
            str(result.get("implementation_scope", "")), field_max_chars
        ),
        "acceptance_criteria": _clip_list(result.get("acceptance_criteria", [])),
        "handoff_notes": _truncate_text(
            str(result.get("handoff_notes", "")), field_max_chars
        ),
        "next_question": _truncate_text(
            str(content.get("next_question", "")), field_max_chars
        ),
    }


def _summarize_review(
    content: Dict[str, Any],
    *,
    turn: Optional[int],
    field_max_chars: int,
    issue_limit: int,
    root_cause_limit: int,
) -> Dict[str, Any]:
    """Summarize review payload for history injection."""
    issues = content.get("issues", [])
    summarized_issues: List[Dict[str, str]] = []
    if isinstance(issues, list):
        for item in issues[: max(0, issue_limit)]:
            if not isinstance(item, dict):
                continue
            summary = _truncate_text(str(item.get("summary", "")), field_max_chars)
            severity = str(item.get("severity", ""))
            if summary:
                summarized_issues.append({"severity": severity, "summary": summary})
    root_cause = content.get("root_cause", [])
    summarized_root: List[str] = []
    if isinstance(root_cause, list):
        for item in root_cause[: max(0, root_cause_limit)]:
            summarized_root.append(_truncate_text(str(item), field_max_chars))
    gate = content.get("gate", {}) if isinstance(content.get("gate"), dict) else {}
    gate_conditions = gate.get("conditions", [])
    if not isinstance(gate_conditions, list):
        gate_conditions = []
    gate_summary = {
        "decision": gate.get("decision"),
        "conditions": [
            _truncate_text(str(item), field_max_chars)
            for item in gate_conditions
        ][: max(0, issue_limit)],
    }
    return {
        "turn": turn,
        "status": content.get("status"),
        "acceptance": content.get("acceptance"),
        "gate": gate_summary,
        "issues": summarized_issues,
        "root_cause": summarized_root,
        "next_question": _truncate_text(
            str(content.get("next_question", "")), field_max_chars
        ),
    }


def _extract_key_changes(
    plan: Optional[Dict[str, Any]],
    delivery: Optional[Dict[str, Any]],
    review: Optional[Dict[str, Any]],
    *,
    field_max_chars: int,
    evidence_limit: int,
    issue_limit: int,
) -> List[str]:
    """Extract key change hints from PM/Dev/Review outputs."""
    key_changes: List[str] = []
    if plan:
        result = plan.get("result", {}) if isinstance(plan.get("result"), dict) else {}
        acceptance = result.get("acceptance_criteria", [])
        if isinstance(acceptance, list):
            for item in acceptance[: max(0, issue_limit)]:
                line = _truncate_text(str(item), field_max_chars)
                if line:
                    key_changes.append(f"acceptance: {line}")
    if delivery:
        result = delivery.get("result", {}) if isinstance(delivery.get("result"), dict) else {}
        evidence = result.get("execution_evidence", [])
        deliverables = result.get("deliverables", [])
        if isinstance(evidence, list):
            for item in evidence[: max(0, evidence_limit)]:
                if not isinstance(item, dict):
                    continue
                cmd = _truncate_text(str(item.get("command", "")), field_max_chars)
                res = _truncate_text(str(item.get("result", "")), field_max_chars)
                if cmd or res:
                    key_changes.append(f"evidence: {cmd} => {res}".strip())
        if isinstance(deliverables, list):
            for item in deliverables[: max(0, evidence_limit)]:
                if not isinstance(item, dict):
                    continue
                path_value = _truncate_text(str(item.get("path", "")), field_max_chars)
                if path_value:
                    key_changes.append(f"deliverable: {path_value}")
    if review:
        issues = review.get("issues", [])
        if isinstance(issues, list):
            for item in issues[: max(0, issue_limit)]:
                if not isinstance(item, dict):
                    continue
                severity = str(item.get("severity", ""))
                summary = _truncate_text(str(item.get("summary", "")), field_max_chars)
                if summary:
                    key_changes.append(f"issue[{severity}]: {summary}")
    return key_changes


def _format_history(
    transcript: List[Dict[str, Any]],
    history_cfg: Dict[str, Any],
) -> str:
    """Format trimmed transcript with latest PM + delivery + review summaries."""
    if not transcript:
        return "(no history)"

    max_chars = int(history_cfg.get("max_chars", 3000))
    field_max_chars = int(history_cfg.get("field_max_chars", 400))
    evidence_limit = int(history_cfg.get("evidence_limit", 3))
    issue_limit = int(history_cfg.get("issue_limit", 5))
    root_cause_limit = int(history_cfg.get("root_cause_limit", 3))
    include_key_changes = bool(history_cfg.get("include_key_changes", True))

    delivery_content, delivery_turn = _extract_latest_content(
        transcript, DELIVERY_SCHEMA_VERSION
    )
    plan_content, plan_turn = _extract_latest_content(
        transcript, PLAN_SCHEMA_VERSION
    )
    review_content, review_turn = _extract_latest_content(
        transcript, REVIEW_SCHEMA_VERSION
    )

    lines: List[str] = []
    if plan_content:
        summary = _summarize_plan(
            plan_content,
            turn=plan_turn,
            field_max_chars=field_max_chars,
            list_limit=max(issue_limit, evidence_limit),
        )
        lines.append(
            "LATEST_PLAN="
            + json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
        )
    if delivery_content:
        summary = _summarize_delivery(
            delivery_content,
            turn=delivery_turn,
            field_max_chars=field_max_chars,
            evidence_limit=evidence_limit,
        )
        lines.append(
            "LATEST_DELIVERY="
            + json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
        )
    if review_content:
        summary = _summarize_review(
            review_content,
            turn=review_turn,
            field_max_chars=field_max_chars,
            issue_limit=issue_limit,
            root_cause_limit=root_cause_limit,
        )
        lines.append(
            "LATEST_REVIEW="
            + json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
        )
    if include_key_changes:
        key_changes = _extract_key_changes(
            plan_content,
            delivery_content,
            review_content,
            field_max_chars=field_max_chars,
            evidence_limit=evidence_limit,
            issue_limit=issue_limit,
        )
        if key_changes:
            lines.append(
                "KEY_CHANGES="
                + json.dumps(key_changes, ensure_ascii=False, separators=(",", ":"))
            )

    if not lines:
        return "(no relevant history)"

    history_text = "\n".join(lines)
    if max_chars > 0 and len(history_text) > max_chars:
        history_text = history_text[: max_chars - 3] + "..."
    return history_text


def _extract_peer_question(
    transcript: List[Dict[str, Any]],
) -> Optional[str]:
    """Extract latest question from structured JSON content."""
    if not transcript:
        return None

    for item in reversed(transcript):
        content = item.get("protocol_content")
        if isinstance(content, dict):
            next_question = content.get("next_question")
            if isinstance(next_question, str) and next_question.strip():
                return next_question.strip()
    return None


def _agent_output_contract(*, current_agent: str, peer_agent: str) -> str:
    """Return strict JSON output contract for stable multi-agent handoff."""
    peer_display = display_agent_name(peer_agent)
    schema = build_agent_output_schema(current_agent)
    schema_text = json.dumps(schema, ensure_ascii=False, indent=2)

    return (
        "输出必须严格遵循 JSON Schema。\n"
        "只允许输出一个 JSON 对象；禁止输出 Markdown、代码块、前后解释文本。\n"
        f"`next_question` 必须面向接收方 {peer_display}，并包含问号。\n"
        "若证据不足，请在 JSON 中用 status/warnings/errors 明确表达，禁止自然语言补丁。\n"
        f"JSON Schema:\n{schema_text}"
    )


def _build_turn_prompt(
    *,
    user_request: str,
    current_agent: str,
    peer_agent: str,
    workdir: str,
    response_mode: str,
    transcript: List[Dict[str, Any]],
    history_cfg: Dict[str, Any],
    extra_instruction: Optional[str] = None,
    prompt_dir: Optional[str] = None,
    read_only: bool = False,
) -> str:
    """Build one turn prompt for current agent."""
    mission = AGENTS[current_agent].mission
    current_display = display_agent_name(current_agent)
    peer_display = display_agent_name(peer_agent)
    history_text = _format_history(transcript, history_cfg)
    peer_question = _extract_peer_question(transcript)
    peer_question_text = f"对方刚才的问题：{peer_question}\n\n" if peer_question else ""

    extra_text = f"\n{extra_instruction}\n" if extra_instruction else ""
    output_contract = _agent_output_contract(
        current_agent=current_agent, peer_agent=peer_agent
    )

    mode = (response_mode or "text_only").strip().lower()
    workdir_lock = (
        f"工作目录一致性约束：所有命令、读写、交付与验收必须在执行目录 {workdir} 内闭环完成；"
        "禁止在其它目录创建镜像副本或同步副本。"
    )
    if mode == "execute":
        mode_instruction = (
            "当前为执行模式：你可以调用工具并在执行目录直接创建/修改文件，"
            "不要请求授权，不要停留在计划层。"
            f"{workdir_lock}"
        )
    else:
        mode_instruction = (
            "当前为对话模式：只输出 JSON，不调用工具，不执行命令，不读写文件。"
            f"{workdir_lock}"
        )

    role_guard = ""
    if current_agent == STELLA:
        mode_instruction = (
            "当前为动态评审模式：你可以调用只读工具收集证据，"
            "并允许执行 shell 验证命令（如 python -m pytest、python -m unittest、ls、grep）；"
            "禁止修改/删除业务文件。"
            f"{workdir_lock}"
        )
        role_guard = (
            "角色硬约束：你是评审官，不是实现者。"
            "请基于动态核验证据完成评审，verification 至少包含2条证据（command/result 格式，"
            "建议至少包含1条 shell 验证命令）。"
        )
    elif current_agent == DUFFY:
        role_guard = (
            "角色硬约束：你是产品经理，不是实现者也不是评审者。"
            "必须输出需求拆解和验收目标，并把任务交接给玲娜贝儿。"
        )

    turn_task_goal = user_request
    if current_agent == STELLA and transcript:
        turn_task_goal = (
            "本轮只做中文代码评审。"
            "请基于最近一条来自玲娜贝儿的交付进行核验，"
            "按协议给出验收结论、问题清单和回归门禁。"
        )
    elif current_agent == DUFFY:
        turn_task_goal = (
            "本轮只做产品需求拆解。"
            "请把用户需求拆解为可执行任务，明确范围边界、优先级和验收目标，"
            "并交接给玲娜贝儿执行。"
        )

    safety_note = ""
    if read_only:
        safety_note = "安全约束：只允许只读操作，禁止写入/删除/修改文件。\n"

    base_dir = Path(prompt_dir or "prompts")
    system_path = base_dir / "system.md"
    if current_agent == DUFFY:
        agent_template = base_dir / "duffy_plan.md"
    elif current_agent == STELLA:
        agent_template = base_dir / "stella_review.md"
    else:
        agent_template = base_dir / "linabell_delivery.md"

    def _read_template(path: Path) -> str:
        if not path.exists():
            return ""
        text = path.read_text(encoding="utf-8", errors="replace")
        return text.lstrip("\ufeff")

    def _render_template(template: str, context: Dict[str, str]) -> str:
        rendered = template
        for key, value in context.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", value)
        return rendered

    context = {
        "task_goal": turn_task_goal,
        "user_request": user_request,
        "workdir": workdir,
        "mode_instruction": mode_instruction,
        "history": history_text,
        "peer_question_text": peer_question_text,
        "agent_display": current_display,
        "agent_id": current_agent,
        "mission": mission,
        "role_guard": role_guard,
        "safety_note": safety_note,
        "output_contract": output_contract,
        "peer_display": peer_display,
        "extra_instruction": extra_text,
    }

    system_template = _read_template(system_path)
    agent_template_text = _read_template(agent_template)
    combined = "\n\n".join(
        part for part in (system_template, agent_template_text) if part.strip()
    )
    if combined:
        return _render_template(combined, context)

    # Fallback: previous inline prompt if templates are missing.
    return (
        f"任务目标：{turn_task_goal}\n"
        f"原始用户需求：{user_request}\n\n"
        f"执行目录：{workdir}\n"
        f"{mode_instruction}\n\n"
        f"当前协作历史：\n{history_text}\n\n"
        f"{peer_question_text}"
        f"你是「{current_display}」（ID: {current_agent}），职责：{mission}\n"
        "请直接围绕任务作答，禁止解释系统/角色/脚本/运行方式。\n"
        "禁止输出“无法访问目录”“请授权”“请先提供文件列表”等元请求。\n"
        "信息不足时先基于当前任务做最小可执行假设并继续推进，"
        "仅当缺口会直接阻断交付时，才允许在 JSON 的 next_question 提出1个明确问题。\n"
        "硬性校验规则（违反会被判定失败并要求重写）：\n"
        "1) 输出必须是可被 json.loads 直接解析的单个 JSON 对象\n"
        "2) 输出必须满足给定 JSON Schema\n"
        "3) next_question 必须包含问号\n"
        "4) 第一字符必须是 {，最后字符必须是 }\n"
        "5) 禁止输出任何 JSON 之外字符（包括“我将先...”“```json”）\n"
        f"{role_guard}\n"
        f"{safety_note}"
        "不要问好，不要寒暄，不要自我介绍，不要输出 JSON 之外的任何文本。\n\n"
        f"输出协议：\n{output_contract}\n"
        f"当前轮次接收方：{peer_display}\n"
        f"{extra_text}"
    )


def _resolve_agent_runtime(
    *,
    runtime_config: Dict[str, Any],
    agent_name: str,
    safety_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge provider defaults with per-agent overrides."""
    provider_name = AGENTS[agent_name].provider
    providers_cfg = runtime_config.get("providers", {})
    provider_defaults = (
        providers_cfg.get(provider_name, {}) if isinstance(providers_cfg, dict) else {}
    )

    provider_options: Dict[str, Any] = {}
    if provider_name == "codex":
        provider_options["exec_mode"] = str(provider_defaults.get("exec_mode", "safe"))
    elif provider_name == "claude-minimax":
        provider_options["permission_mode"] = str(
            provider_defaults.get("permission_mode", "acceptEdits")
        )
        provider_options["include_partial_messages"] = bool(
            provider_defaults.get("include_partial_messages", False)
        )
        provider_options["print_stderr"] = bool(
            provider_defaults.get("print_stderr", False)
        )
        if "tools" in provider_defaults:
            provider_options["tools"] = provider_defaults.get("tools")

    friends_bar = runtime_config.get("friends_bar", {})
    agents_cfg = friends_bar.get("agents", {}) if isinstance(friends_bar, dict) else {}

    agent_cfg: Dict[str, Any] = {}
    if isinstance(agents_cfg, dict):
        candidate_cfg = agents_cfg.get(agent_name)
        if isinstance(candidate_cfg, dict):
            agent_cfg = candidate_cfg
        else:
            display_name = display_agent_name(agent_name)
            display_cfg = agents_cfg.get(display_name)
            if isinstance(display_cfg, dict):
                agent_cfg = display_cfg

    response_mode = "text_only"
    if isinstance(agent_cfg, dict):
        response_mode = str(agent_cfg.get("response_mode", "text_only"))
        agent_provider_opts = agent_cfg.get("provider_options", {})
        if isinstance(agent_provider_opts, dict):
            provider_options.update(agent_provider_opts)

    if (
        agent_name == STELLA
        and provider_name == "claude-minimax"
        and response_mode.strip().lower() == "execute"
    ):
        normalized_permission_mode = str(
            provider_options.get("permission_mode", "")
        ).strip()
        if normalized_permission_mode in {
            "",
            "default",
            "acceptEdits",
            "delegate",
            "dontAsk",
            "plan",
        }:
            provider_options["permission_mode"] = "bypassPermissions"

    if safety_cfg.get("read_only"):
        if provider_name == "codex":
            provider_options["exec_mode"] = "safe"
            provider_options["sandbox_mode"] = safety_cfg.get(
                "codex_sandbox_read_only", "read-only"
            )
        elif provider_name == "claude-minimax":
            provider_options["tools"] = safety_cfg.get(
                "claude_tools_read_only", "Read"
            )
            if "disallowed_tools" not in provider_options:
                provider_options["disallowed_tools"] = ["Bash", "Edit"]
    else:
        if provider_name == "codex" and "sandbox_mode" not in provider_options:
            provider_options["sandbox_mode"] = safety_cfg.get(
                "codex_sandbox_default", "workspace-write"
            )

    return {
        "response_mode": response_mode,
        "provider_options": provider_options,
    }


def run_two_agent_dialogue(
    user_request: str,
    *,
    rounds: Optional[int] = None,
    start_agent: Optional[str] = None,
    project_path: Optional[str] = None,
    use_session: Optional[bool] = None,
    stream: bool = True,
    stream_debug: bool = False,
    timeout_level: Optional[str] = "standard",
    config_path: str = "config.toml",
    seed: Optional[int] = None,
    dry_run: bool = False,
    dump_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """Run Friends Bar multi-agent dialogue loop."""
    if not isinstance(user_request, str) or not user_request.strip():
        raise ValueError("user_request must be a non-empty string")

    runtime_config = load_runtime_config(config_path=config_path)
    friends_bar_config = runtime_config.get("friends_bar", {})
    if not isinstance(friends_bar_config, dict):
        friends_bar_config = {}
    prompt_dir = friends_bar_config.get("prompt_dir", "prompts")
    safety_cfg = friends_bar_config.get("safety", {})
    if not isinstance(safety_cfg, dict):
        safety_cfg = {}
    history_cfg = friends_bar_config.get("history", {})
    if not isinstance(history_cfg, dict):
        history_cfg = {}

    audit_logger = AuditLogger(
        AuditLogConfig.from_runtime_config(friends_bar_config),
        seed=seed,
    )
    run_started = time.monotonic()

    resolved_rounds = (
        int(friends_bar_config.get("default_rounds", 4))
        if rounds is None
        else int(rounds)
    )
    if resolved_rounds < 1:
        raise ValueError("rounds must be >= 1")

    resolved_start_agent = (
        str(friends_bar_config.get("start_agent", DUFFY))
        if start_agent is None
        else start_agent
    )

    resolved_workdir, workdir_source = _resolve_workdir(
        project_path=project_path, user_request=user_request
    )
    if workdir_source == "cwd_default":
        raise ValueError(
            "workdir must be explicitly specified via --project-path "
            "or as an absolute path in user_request"
        )
    _ensure_allowed_roots(resolved_workdir, safety_cfg.get("allowed_roots", []))
    resolved_workdir_path = Path(resolved_workdir)
    if resolved_workdir_path.exists():
        if not resolved_workdir_path.is_dir():
            raise ValueError(f"project_path is not a directory: {resolved_workdir}")
    else:
        resolved_workdir_path.mkdir(parents=True, exist_ok=True)
    resolved_workdir = str(resolved_workdir_path)

    current_agent = normalize_agent_name(resolved_start_agent)
    transcript: List[Dict[str, Any]] = []
    run_error: Optional[Dict[str, Any]] = None
    dry_run_payload: Optional[Dict[str, Any]] = None
    dry_run_triggered = False

    audit_logger.log(
        "run.started",
        {
            "workspace": "Friends Bar",
            "config_path": config_path,
            "user_request": user_request,
            "user_request_meta": text_meta(
                user_request,
                include_preview=audit_logger.include_prompt_preview,
                max_preview_chars=audit_logger.max_preview_chars,
            ),
            "args": {
                "rounds": resolved_rounds,
                "start_agent": current_agent,
                "project_path": resolved_workdir,
                "project_path_source": workdir_source,
                "use_session": (
                    "config_default" if use_session is None else bool(use_session)
                ),
                "timeout_level": timeout_level,
                "stream": bool(stream),
            },
        },
    )
    audit_logger.log(
        "protocol.task.envelope",
        build_task_envelope(
            trace_id=audit_logger.run_id,
            sender="orchestrator",
            recipient=current_agent,
            intent="friends_bar_round_robin_task",
            user_request=user_request,
            workdir=resolved_workdir,
            timeout_level=timeout_level,
            expected_schema_version=_expected_schema_for_agent(current_agent),
        ),
    )

    try:
        for turn in range(1, resolved_rounds + 1):
            turn_started = time.monotonic()
            peer_agent = _next_agent(current_agent)
            runtime_info = _resolve_agent_runtime(
                runtime_config=runtime_config,
                agent_name=current_agent,
                safety_cfg=safety_cfg,
            )

            audit_logger.log(
                "round.started",
                {
                    "turn": turn,
                    "agent": current_agent,
                    "peer_agent": peer_agent,
                },
            )
            audit_logger.log(
                "round.start",
                {
                    "turn": turn,
                    "agent": current_agent,
                    "peer_agent": peer_agent,
                },
            )
            audit_logger.log(
                "turn.started",
                {
                    "turn": turn,
                    "agent": current_agent,
                    "peer_agent": peer_agent,
                    "response_mode": runtime_info.get("response_mode"),
                    "provider_options": runtime_info.get("provider_options", {}),
                },
            )

            if stream:
                current_display = display_agent_name(current_agent)
                peer_display = display_agent_name(peer_agent)
                print(f"\n[system] 第{turn}轮执行中：{current_display} -> {peer_display}")

            text = ""
            raw_text = ""
            result: Dict[str, Any] = {}
            protocol_errors: List[str] = []
            extra_instruction: Optional[str] = None
            attempt_count = 0
            structured_content: Optional[Dict[str, Any]] = None
            raw_payload: Optional[Dict[str, Any]] = None

            for attempt_idx in range(MAX_PROTOCOL_RETRY + 1):
                attempt_count = attempt_idx + 1
                attempt_started = time.monotonic()
                # Reviewer usually needs extra pre-flight time for CLI/tools.
                effective_timeout_level = timeout_level
                if current_agent == STELLA and timeout_level == "quick":
                    effective_timeout_level = "standard"

                adjusted_prompt = _build_turn_prompt(
                    user_request=user_request,
                    current_agent=current_agent,
                    peer_agent=peer_agent,
                    workdir=resolved_workdir,
                    response_mode=runtime_info["response_mode"],
                    transcript=transcript,
                    history_cfg=history_cfg,
                    extra_instruction=extra_instruction,
                    prompt_dir=str(prompt_dir) if prompt_dir else None,
                    read_only=bool(safety_cfg.get("read_only", False)),
                )
                prompt_bytes = len(adjusted_prompt.encode("utf-8"))
                audit_logger.log(
                    "prompt.stats",
                    {
                        "turn": turn,
                        "attempt": attempt_count,
                        "agent": current_agent,
                        "chars": len(adjusted_prompt),
                        "bytes": prompt_bytes,
                    },
                )
                audit_logger.log(
                    "prompt.bytes",
                    {
                        "turn": turn,
                        "attempt": attempt_count,
                        "agent": current_agent,
                        "bytes": prompt_bytes,
                    },
                )
                dump_path = _dump_prompt(
                    prompt=adjusted_prompt,
                    dump_target=dump_prompt,
                    run_id=audit_logger.run_id,
                    turn=turn,
                    agent=current_agent,
                )
                if dump_path or dump_prompt:
                    audit_logger.log(
                        "prompt.dump",
                        {
                            "turn": turn,
                            "agent": current_agent,
                            "path": dump_path,
                            "prompt_meta": text_meta(
                                adjusted_prompt,
                                include_preview=audit_logger.include_prompt_preview,
                                max_preview_chars=audit_logger.max_preview_chars,
                            ),
                        },
                    )
                if dry_run:
                    audit_logger.log(
                        "run.dry_run",
                        {
                            "turn": turn,
                            "agent": current_agent,
                            "schema": build_agent_output_schema(current_agent),
                        },
                    )
                    dry_run_payload = {
                        "workspace": "Friends Bar",
                        "user_request": user_request,
                        "rounds": resolved_rounds,
                        "dry_run": True,
                        "prompt": adjusted_prompt,
                        "schema": build_agent_output_schema(current_agent),
                        "run_id": audit_logger.run_id,
                        "seed": audit_logger.seed,
                    }
                    dry_run_triggered = True
                    break
                audit_logger.log(
                    "turn.attempt.started",
                    {
                        "turn": turn,
                        "attempt": attempt_count,
                        "agent": current_agent,
                        "peer_agent": peer_agent,
                        "timeout_level": effective_timeout_level,
                        "prompt_meta": text_meta(
                            adjusted_prompt,
                            include_preview=audit_logger.include_prompt_preview,
                            max_preview_chars=audit_logger.max_preview_chars,
                        ),
                    },
                )

                provider_options = dict(runtime_info["provider_options"])
                agent_schema = build_agent_output_schema(current_agent)
                if AGENTS[current_agent].provider == "claude-minimax":
                    provider_options["json_schema"] = agent_schema
                if AGENTS[current_agent].provider == "codex":
                    provider_options["output_schema"] = agent_schema
                if AGENTS[current_agent].provider == "gemini":
                    provider_options["json_schema"] = agent_schema

                try:
                    def event_hook(event: str, payload: Dict[str, Any]) -> None:
                        audit_logger.log(
                            event,
                            {
                                "turn": turn,
                                "attempt": attempt_count,
                                "agent": current_agent,
                                **payload,
                            },
                        )
                        if not stream or not stream_debug or current_agent != STELLA:
                            return
                        if event == "provider.raw_stdout_line":
                            line = str(payload.get("line", "")).strip()
                            if line:
                                _safe_print(f"[星黛露 raw] {line}")
                            return
                        if event == "provider.tool_use":
                            tool_name = str(payload.get("tool_name", "")).strip() or "unknown"
                            parameters = payload.get("parameters")
                            if isinstance(parameters, dict) and parameters.get("file_path"):
                                _safe_print(
                                    f"[星黛露] 调用工具 `{tool_name}` 读取文件: {parameters.get('file_path')}"
                                )
                            else:
                                _safe_print(f"[星黛露] 调用工具 `{tool_name}`")
                            return
                        if event == "provider.tool_result":
                            status = str(payload.get("status", "")).strip() or "unknown"
                            tool_id = str(payload.get("tool_id", "")).strip()
                            if status.lower() == "error":
                                error_msg = payload.get("error")
                                _safe_print(
                                    f"[星黛露] 工具结果失败 ({tool_id}): {error_msg}"
                                )
                            else:
                                _safe_print(f"[星黛露] 工具结果成功 ({tool_id})")

                    result = invoke(
                        current_agent,
                        adjusted_prompt,
                        use_session=use_session,
                        stream=False,
                        workdir=resolved_workdir,
                        provider_options=provider_options,
                        timeout_level=effective_timeout_level,
                        run_id=audit_logger.run_id,
                        seed=audit_logger.seed,
                        event_hook=event_hook,
                    )
                except Exception as exc:
                    audit_logger.log(
                        "turn.attempt.failed",
                        {
                            "turn": turn,
                            "attempt": attempt_count,
                            "agent": current_agent,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                    )
                    raise

                raw_text = (result.get("text") or "").strip()
                text = raw_text if raw_text else "(empty reply)"

                validation_started = time.monotonic()
                is_valid, protocol_errors, parsed_content, parsed_payload = _validate_agent_output(
                    current_agent=current_agent,
                    output=text,
                    peer_agent=peer_agent,
                    trace_id=audit_logger.run_id,
                )
                parse_ok = not any(
                    error.startswith("E_SCHEMA_INVALID_FORMAT") for error in protocol_errors
                )
                schema_ok = parse_ok and not any(
                    error.startswith("E_SCHEMA_") for error in protocol_errors
                )
                audit_logger.log(
                    "protocol.validated",
                    {
                        "turn": turn,
                        "attempt": attempt_count,
                        "agent": current_agent,
                        "is_valid": is_valid,
                        "parse_ok": parse_ok,
                        "schema_ok": schema_ok,
                        "errors": protocol_errors,
                        "validation_ms": int((time.monotonic() - validation_started) * 1000),
                        "attempt_elapsed_ms": int((time.monotonic() - attempt_started) * 1000),
                    },
                )
                structured_content = parsed_content
                raw_payload = parsed_payload
                if is_valid and isinstance(parsed_content, dict):
                    commands = _collect_commands(parsed_content, current_agent)
                    safety_errors = _command_policy_errors(
                        commands,
                        allowlist=safety_cfg.get("command_allowlist", []),
                        denylist=safety_cfg.get("command_denylist", []),
                    )
                    if safety_errors:
                        is_valid = False
                        protocol_errors = protocol_errors + safety_errors
                    if is_valid and current_agent in {LINA_BELL, STELLA}:
                        workdir_errors = _command_workdir_errors(
                            commands,
                            workdir=resolved_workdir,
                        )
                        if workdir_errors:
                            is_valid = False
                            protocol_errors = protocol_errors + workdir_errors
                            audit_logger.log(
                                "workdir.verify",
                                {
                                    "turn": turn,
                                    "attempt": attempt_count,
                                    "agent": current_agent,
                                    "workdir": resolved_workdir,
                                    "commands": commands,
                                    "errors": workdir_errors,
                                },
                            )
                    if (
                        is_valid
                        and current_agent == LINA_BELL
                        and runtime_info.get("response_mode") == "execute"
                        and not safety_cfg.get("read_only", False)
                    ):
                        delivery_errors = _verify_delivery_deliverables(
                            parsed_content,
                            workdir=resolved_workdir,
                        )
                        if delivery_errors:
                            is_valid = False
                            protocol_errors = protocol_errors + delivery_errors
                            audit_logger.log(
                                "delivery.verify",
                                {
                                    "turn": turn,
                                    "attempt": attempt_count,
                                    "agent": current_agent,
                                    "workdir": resolved_workdir,
                                    "deliverables": (
                                        parsed_content.get("result", {}).get("deliverables", [])
                                        if isinstance(parsed_content.get("result"), dict)
                                        else []
                                    ),
                                    "errors": delivery_errors,
                                },
                            )
                audit_logger.log(
                    "turn.attempt.completed",
                    {
                        "turn": turn,
                        "attempt": attempt_count,
                        "agent": current_agent,
                        "provider": result.get("cli"),
                        "session_id": result.get("session_id"),
                        "elapsed_ms": result.get("elapsed_ms"),
                        "raw_text": raw_text,
                        "raw_text_meta": text_meta(
                            raw_text,
                            include_preview=audit_logger.include_prompt_preview,
                            max_preview_chars=audit_logger.max_preview_chars,
                        ),
                        "is_valid": is_valid,
                        "protocol_errors": protocol_errors,
                        "protocol_content": parsed_content,
                        "protocol_raw_payload": parsed_payload,
                    },
                )
                if is_valid:
                    if isinstance(parsed_payload, dict):
                        text = json.dumps(parsed_payload, ensure_ascii=False, indent=2)
                    break

                schema = build_agent_output_schema(current_agent)
                repair_path = Path(prompt_dir or "prompts") / "repair_json.md"
                repair_template = ""
                if repair_path.exists():
                    repair_template = repair_path.read_text(encoding="utf-8")
                previous_output_hint = _truncate_text(raw_text, 2000) if raw_text else ""
                if repair_template:
                    extra_instruction = (
                        repair_template.replace("{{validation_errors}}", " / ".join(protocol_errors))
                        .replace("{{previous_output}}", previous_output_hint)
                        .replace("{{schema}}", json.dumps(schema, ensure_ascii=False, indent=2))
                    )
                else:
                    extra_instruction = (
                        "你上一条输出没有通过 JSON Schema 校验："
                        + " / ".join(protocol_errors)
                        + "。请在不改变任务目标的前提下输出一个合法 JSON 对象。\n"
                        + "禁止输出任何 JSON 之外文本；首字符必须是 {，末字符必须是 }。\n"
                        + (previous_output_hint + "\n" if previous_output_hint else "")
                        + "请严格匹配以下 schema：\n"
                        + json.dumps(schema, ensure_ascii=False, indent=2)
                    )

            if dry_run_triggered:
                break

            if protocol_errors:
                raise RuntimeError(
                    f"JSON protocol validation failed after {attempt_count} attempts: "
                    + " / ".join(protocol_errors)
                )

            turn_record = {
                "turn": turn,
                "agent": current_agent,
                "provider": result.get("cli"),
                "text": text,
                "session_id": result.get("session_id"),
                "elapsed_ms": result.get("elapsed_ms"),
                "attempts": attempt_count,
                "protocol_coerced": False,
                "protocol_content": structured_content,
                "protocol_raw_payload": raw_payload,
            }
            transcript.append(turn_record)
            audit_logger.log(
                "turn.completed",
                {
                    "turn": turn,
                    "agent": current_agent,
                    "peer_agent": peer_agent,
                    "provider": result.get("cli"),
                    "session_id": result.get("session_id"),
                    "elapsed_ms": result.get("elapsed_ms"),
                    "attempts": attempt_count,
                    "protocol_coerced": False,
                    "final_text": text,
                    "final_text_meta": text_meta(
                        text,
                        include_preview=audit_logger.include_prompt_preview,
                        max_preview_chars=audit_logger.max_preview_chars,
                    ),
                    "turn_duration_ms": int((time.monotonic() - turn_started) * 1000),
                },
            )

            if stream:
                current_display = display_agent_name(current_agent)
                peer_display = display_agent_name(peer_agent)
                print(f"\n[{current_display} -> {peer_display}]")
                _safe_print(text)

            current_agent = peer_agent
            if dry_run_triggered:
                break
    except Exception as exc:
        run_error = {
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "turns_completed": len(transcript),
        }
        audit_logger.log("run.failed", run_error)
        raise
    finally:
        summary: Dict[str, Any] = {
            "workspace": "Friends Bar",
            "rounds": resolved_rounds,
            "turns_completed": len(transcript),
            "elapsed_ms": int((time.monotonic() - run_started) * 1000),
            "project_path": resolved_workdir,
            "turns": transcript,
        }
        if dry_run_payload is not None:
            summary["dry_run"] = True
        if run_error is not None:
            summary["error"] = run_error
        audit_logger.finalize(
            status="failed" if run_error is not None else "success",
            summary=summary,
        )

    if dry_run_payload is not None:
        dry_run_payload["log"] = {
            "run_id": audit_logger.run_id,
            "log_file": str(audit_logger.log_file) if audit_logger.log_file else None,
            "summary_file": (
                str(audit_logger.summary_file) if audit_logger.summary_file else None
            ),
        }
        return dry_run_payload

    result_payload = {
        "workspace": "Friends Bar",
        "user_request": user_request,
        "rounds": resolved_rounds,
        "turns": transcript,
        "run_id": audit_logger.run_id,
        "seed": audit_logger.seed,
        "log": {
            "run_id": audit_logger.run_id,
            "log_file": str(audit_logger.log_file) if audit_logger.log_file else None,
            "summary_file": (
                str(audit_logger.summary_file) if audit_logger.summary_file else None
            ),
        },
    }
    if stream and result_payload["log"]["log_file"]:
        _safe_print(f"\n[system] Log file: {result_payload['log']['log_file']}")
    return result_payload
