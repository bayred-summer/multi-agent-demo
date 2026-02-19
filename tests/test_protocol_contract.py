"""Regression tests for JSON protocol contracts."""

from __future__ import annotations

import json
import unittest

from src.friends_bar.agents import DUFFY, LINA_BELL
from src.friends_bar.orchestrator import _agent_output_contract, _validate_agent_output


class TestProtocolContract(unittest.TestCase):
    """Lock JSON-only contract behavior."""

    def test_contract_requires_json_only(self) -> None:
        contract = _agent_output_contract(current_agent=LINA_BELL, peer_agent=DUFFY)
        self.assertIn("JSON Schema", contract)
        self.assertIn("只允许输出一个 JSON 对象", contract)

    def test_validate_agent_output_rejects_plain_text(self) -> None:
        ok, errors, parsed, payload = _validate_agent_output(
            current_agent=DUFFY,
            output="这不是 JSON",
            peer_agent=LINA_BELL,
            trace_id="trace-plain",
        )
        self.assertFalse(ok)
        self.assertIsNone(parsed)
        self.assertIsNone(payload)
        self.assertTrue(any("E_SCHEMA_INVALID_FORMAT" in item for item in errors))

    def test_validate_agent_output_accepts_valid_review_json(self) -> None:
        raw = json.dumps(
            {
                "schema_version": "friendsbar.review.v1",
                "status": "ok",
                "acceptance": "pass",
                "verification": [
                    {"command": "Get-Content model.py", "result": "ok"},
                    {"command": "python -m pytest -q", "result": "1 passed"},
                ],
                "root_cause": [],
                "issues": [],
                "gate": {"decision": "allow", "conditions": []},
                "next_question": "是否继续下一步？",
                "warnings": [],
                "errors": [],
            },
            ensure_ascii=False,
        )
        ok, errors, parsed, payload = _validate_agent_output(
            current_agent=DUFFY,
            output=raw,
            peer_agent=LINA_BELL,
            trace_id="trace-json",
        )
        self.assertTrue(ok, msg=str(errors))
        self.assertIsNotNone(parsed)
        self.assertIsNotNone(payload)


if __name__ == "__main__":
    unittest.main()
