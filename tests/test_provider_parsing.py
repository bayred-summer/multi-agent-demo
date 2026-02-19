"""Provider JSON parsing tolerance tests."""

from __future__ import annotations

import unittest

from src.providers.claude_minimax import (
    _collapse_repeated_json_objects,
    _pick_final_text,
)
from src.providers.codex import _extract_assistant_text


class TestProviderParsing(unittest.TestCase):
    """Ensures parsing stays robust against mixed/partial event styles."""

    def test_codex_delta_then_full_message_is_not_duplicated(self) -> None:
        state = {"saw_delta": False, "thread_id": None}
        delta = _extract_assistant_text(
            {"type": "agent_message_delta", "delta": "Hello"},
            state,
        )
        full = _extract_assistant_text(
            {"type": "agent_message", "message": "Hello"},
            state,
        )
        self.assertEqual(delta, "Hello")
        self.assertEqual(full, "")

    def test_codex_ignores_malformed_event(self) -> None:
        state = {"saw_delta": False, "thread_id": None}
        text = _extract_assistant_text({"type": "unknown", "x": 1}, state)
        self.assertEqual(text, "")

    def test_claude_collapses_duplicated_json_objects(self) -> None:
        duplicated = '{"a":1}{"a":1}'
        collapsed = _collapse_repeated_json_objects(duplicated)
        self.assertEqual(collapsed, '{"a":1}')

    def test_claude_keeps_non_duplicate_mixed_json_stream(self) -> None:
        mixed = '{"a":1}{"a":2}'
        collapsed = _collapse_repeated_json_objects(mixed)
        self.assertEqual(collapsed, mixed)

    def test_claude_pick_final_text_prefers_json_object(self) -> None:
        state = {
            "result_text": "",
            "assistant_text": "非结构化说明文本",
            "delta_parts": ['{"schema_version":"friendsbar.delivery.v1","status":"ok"}'],
        }
        text = _pick_final_text(state)
        self.assertEqual(text, '{"schema_version":"friendsbar.delivery.v1","status":"ok"}')


if __name__ == "__main__":
    unittest.main()
