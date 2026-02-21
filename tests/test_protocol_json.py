"""Tests for structured JSON protocol validators."""

from __future__ import annotations

import unittest

from src.protocol.validators import validate_json_protocol_content


class TestProtocolJson(unittest.TestCase):
    """Validate JSON payload schemas for PM/delivery/review."""

    def test_plan_json_ok(self) -> None:
        payload = {
            "schema_version": "friendsbar.plan.v1",
            "status": "ok",
            "result": {
                "requirement_breakdown": ["a", "b"],
                "implementation_scope": "scope",
                "acceptance_criteria": ["c1", "c2"],
                "handoff_notes": "handoff",
            },
            "next_question": "是否继续？",
            "warnings": [],
            "errors": [],
        }
        result = validate_json_protocol_content(
            current_agent="duffy",
            peer_display="玲娜贝儿",
            payload=payload,
            trace_id="trace-plan",
        )
        self.assertTrue(result.ok, msg=str(result.errors))

    def test_delivery_json_ok(self) -> None:
        payload = {
            "schema_version": "friendsbar.delivery.v1",
            "status": "ok",
            "result": {
                "task_understanding": "goal",
                "implementation_plan": "plan",
                "execution_evidence": [{"command": "python -V", "result": "3.12"}],
                "risks_and_rollback": "none",
                "deliverables": [{"path": "train.py", "kind": "file", "summary": "entrypoint"}],
            },
            "next_question": "是否继续？",
            "warnings": [],
            "errors": [],
        }
        result = validate_json_protocol_content(
            current_agent="linabell",
            peer_display="星黛露",
            payload=payload,
            trace_id="trace-delivery",
        )
        self.assertTrue(result.ok, msg=str(result.errors))

    def test_review_json_requires_evidence(self) -> None:
        payload = {
            "schema_version": "friendsbar.review.v1",
            "status": "ok",
            "acceptance": "pass",
            "verification": [{"command": "python -V", "result": "3.12"}],
            "root_cause": [],
            "issues": [],
            "gate": {"decision": "allow", "conditions": []},
            "next_question": "是否继续？",
            "warnings": [],
            "errors": [],
        }
        result = validate_json_protocol_content(
            current_agent="stella",
            peer_display="玲娜贝儿",
            payload=payload,
            trace_id="trace-review",
        )
        self.assertFalse(result.ok)
        self.assertTrue(
            any(item["code"] == "E_REVIEW_EVIDENCE_MISSING" for item in result.errors)
        )

    def test_review_json_rejects_malformed_verification_item(self) -> None:
        payload = {
            "schema_version": "friendsbar.review.v1",
            "status": "ok",
            "acceptance": "pass",
            "verification": [
                {"oops": "python -V", "result": "3.12"},
                {"command": "python -m pytest -q", "result": "ok"},
            ],
            "root_cause": [],
            "issues": [],
            "gate": {"decision": "allow", "conditions": []},
            "next_question": "是否继续？",
            "warnings": [],
            "errors": [],
        }
        result = validate_json_protocol_content(
            current_agent="stella",
            peer_display="玲娜贝儿",
            payload=payload,
            trace_id="trace-review-malformed",
        )
        self.assertFalse(result.ok)
        self.assertTrue(
            any(
                "verification item 1 must include string command/result"
                in item["message"]
                for item in result.errors
            )
        )


if __name__ == "__main__":
    unittest.main()
