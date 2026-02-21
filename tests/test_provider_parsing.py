"""Provider JSON parsing tolerance tests."""

from __future__ import annotations

import unittest

from src.providers.claude_minimax import (
    _collapse_repeated_json_objects,
    _extract_structured_output,
    _pick_final_text,
    resolve_claude_command,
)
from src.providers.codex import _extract_assistant_text, resolve_codex_command
from src.providers.gemini import (
    _extract_assistant_text as _extract_gemini_text,
    _normalize_auth_mode,
    _pick_final_text as _pick_gemini_final_text,
    _resolve_adapter,
    _validate_auth_prerequisites,
    resolve_gemini_command,
)


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

    def test_claude_extracts_structured_output(self) -> None:
        payload = {
            "structured_output": {
                "schema_version": "friendsbar.review.v1",
                "status": "ok",
            }
        }
        text = _extract_structured_output(payload)
        self.assertEqual(
            text, '{"schema_version":"friendsbar.review.v1","status":"ok"}'
        )

    def test_gemini_delta_then_full_message_is_not_duplicated(self) -> None:
        state = {"saw_delta": False, "session_id": None}
        delta = _extract_gemini_text(
            {"type": "message", "role": "assistant", "content": "Hello", "delta": True},
            state,
        )
        full = _extract_gemini_text(
            {"type": "message", "role": "assistant", "content": "Hello", "delta": False},
            state,
        )
        self.assertEqual(delta, "Hello")
        self.assertEqual(full, "")

    def test_gemini_pick_final_prefers_json_response_text(self) -> None:
        state = {
            "response_text": '{"status":"ok"}',
            "output_parts": ["fallback"],
        }
        text = _pick_gemini_final_text(state)
        self.assertEqual(text, '{"status":"ok"}')

    def test_gemini_normalize_auth_mode(self) -> None:
        self.assertEqual(_normalize_auth_mode("api_key"), "api_key")
        with self.assertRaises(ValueError):
            _normalize_auth_mode("unknown")

    def test_gemini_validate_auth_mode_api_key_requires_env(self) -> None:
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                _validate_auth_prerequisites("api_key")

    def test_gemini_adapter_normalization(self) -> None:
        self.assertEqual(_resolve_adapter("cli"), "gemini-cli")
        self.assertEqual(_resolve_adapter("antigravity-mcp"), "antigravity")
        with self.assertRaises(ValueError):
            _resolve_adapter("invalid-adapter")

    def test_codex_command_resolution(self) -> None:
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"CODEX_BIN": "/tmp/custom-codex"}, clear=True):
            self.assertEqual(resolve_codex_command(), "/tmp/custom-codex")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_codex_command(), "codex")

    def test_claude_command_resolution(self) -> None:
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"CLAUDE_BIN": "/tmp/custom-claude"}, clear=True):
            self.assertEqual(resolve_claude_command(), ("/tmp/custom-claude", []))
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_claude_command(), ("claude", []))

    def test_gemini_command_resolution(self) -> None:
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"GEMINI_BIN": "/tmp/custom-gemini"}, clear=True):
            self.assertEqual(resolve_gemini_command(), "/tmp/custom-gemini")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_gemini_command(), "gemini")


if __name__ == "__main__":
    unittest.main()
