"""Regression tests for Friends Bar output protocol contracts."""

from __future__ import annotations

import unittest

from src.friends_bar.agents import DUFFY, LINA_BELL
from src.friends_bar.orchestrator import _agent_output_contract, validate_minimal_protocol


class TestProtocolContract(unittest.TestCase):
    """Lock protocol block names and fixed message boundaries."""

    def test_linabell_contract_blocks(self) -> None:
        contract = _agent_output_contract(current_agent=LINA_BELL, peer_agent=DUFFY)
        expected_blocks = [
            "[接收方]",
            "[任务理解]",
            "[实施清单]",
            "[执行证据]",
            "[风险与回滚]",
            "[给达菲的问题]",
        ]
        for block in expected_blocks:
            self.assertIn(block, contract)

    def test_duffy_contract_blocks(self) -> None:
        contract = _agent_output_contract(current_agent=DUFFY, peer_agent=LINA_BELL)
        expected_blocks = [
            "[接收方]",
            "[验收结论]",
            "[核验清单]",
            "[根因链]",
            "[问题清单]",
            "[回归门禁]",
            "[给玲娜贝儿的问题]",
        ]
        for block in expected_blocks:
            self.assertIn(block, contract)

    def test_validate_minimal_protocol_accepts_valid_message_boundaries(self) -> None:
        output = "\n".join(
            [
                "发送给达菲：路由确认",
                "[接收方]",
                "发送给达菲：请确认回归门禁是否完整？",
            ]
        )
        ok, errors = validate_minimal_protocol(output=output, peer_agent=DUFFY)
        self.assertTrue(ok)
        self.assertEqual(errors, [])

    def test_validate_minimal_protocol_rejects_invalid_boundaries(self) -> None:
        output = "\n".join(
            [
                "发送给达菲：不是路由确认",
                "[接收方]",
                "发送给玲娜贝儿：问题？",
            ]
        )
        ok, errors = validate_minimal_protocol(output=output, peer_agent=DUFFY)
        self.assertFalse(ok)
        self.assertGreaterEqual(len(errors), 2)


if __name__ == "__main__":
    unittest.main()
