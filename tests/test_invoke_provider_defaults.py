"""Tests for provider-specific invoke defaults."""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from src.invoke import invoke
from src.utils.process_runner import ProcessExecutionError


class TestInvokeProviderDefaults(unittest.TestCase):
    """Ensure provider-level config can override global defaults."""

    def test_gemini_uses_session_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.toml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    [defaults]
                    use_session = true
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            captured: dict[str, object] = {}

            def fake_provider(**kwargs):
                captured["session_id"] = kwargs.get("session_id")
                return {"text": "ok", "session_id": None, "elapsed_ms": 1}

            with patch("src.invoke.PROVIDERS", {"gemini": fake_provider}), patch(
                "src.invoke.get_session_id", return_value="existing-session"
            ) as mock_get_session:
                result = invoke("gemini", "ping", config_path=str(config_path))

            self.assertEqual(result["text"], "ok")
            self.assertEqual(captured.get("session_id"), "existing-session")
            mock_get_session.assert_called_once_with("gemini")

    def test_gemini_provider_can_override_use_session_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.toml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    [defaults]
                    use_session = true

                    [providers.gemini]
                    use_session = false
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            captured: dict[str, object] = {}

            def fake_provider(**kwargs):
                captured["session_id"] = kwargs.get("session_id")
                return {"text": "ok", "session_id": None, "elapsed_ms": 1}

            with patch("src.invoke.PROVIDERS", {"gemini": fake_provider}), patch(
                "src.invoke.get_session_id"
            ) as mock_get_session:
                result = invoke("gemini", "ping", config_path=str(config_path))

            self.assertEqual(result["text"], "ok")
            self.assertIsNone(captured.get("session_id"))
            mock_get_session.assert_not_called()

    def test_provider_options_use_config_defaults_and_explicit_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.toml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    [providers.gemini]
                    adapter = "antigravity"
                    auth_mode = "api_key"
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            captured: dict[str, object] = {}

            def fake_provider(**kwargs):
                captured.update(kwargs)
                return {"text": "ok", "session_id": None, "elapsed_ms": 1}

            with patch("src.invoke.PROVIDERS", {"gemini": fake_provider}):
                invoke(
                    "gemini",
                    "ping",
                    config_path=str(config_path),
                    provider_options={"adapter": "gemini-cli"},
                )

            self.assertEqual(captured.get("adapter"), "gemini-cli")
            self.assertEqual(captured.get("auth_mode"), "api_key")

    def test_provider_options_include_gemini_proxy_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.toml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    [providers.gemini]
                    proxy = "http://127.0.0.1:7890"
                    no_proxy = "localhost,127.0.0.1"
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            captured: dict[str, object] = {}

            def fake_provider(**kwargs):
                captured.update(kwargs)
                return {"text": "ok", "session_id": None, "elapsed_ms": 1}

            with patch("src.invoke.PROVIDERS", {"gemini": fake_provider}):
                invoke("gemini", "ping", config_path=str(config_path))

            self.assertEqual(captured.get("proxy"), "http://127.0.0.1:7890")
            self.assertEqual(captured.get("no_proxy"), "localhost,127.0.0.1")

    def test_provider_options_include_gemini_include_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.toml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    [providers.gemini]
                    include_directories = ["E:\\\\PythonProjects\\\\test_project1"]
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            captured: dict[str, object] = {}

            def fake_provider(**kwargs):
                captured.update(kwargs)
                return {"text": "ok", "session_id": None, "elapsed_ms": 1}

            with patch("src.invoke.PROVIDERS", {"gemini": fake_provider}):
                invoke("gemini", "ping", config_path=str(config_path))

            self.assertEqual(
                captured.get("include_directories"),
                ["E:\\PythonProjects\\test_project1"],
            )

    def test_claude_stale_session_auto_clears_and_retries_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.toml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    [providers.claude-minimax]
                    use_session = true
                    retry_attempts = 0
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            call_sessions: list[object] = []

            def fake_provider(**kwargs):
                call_sessions.append(kwargs.get("session_id"))
                if len(call_sessions) == 1:
                    raise ProcessExecutionError(
                        provider="claude-minimax",
                        reason="nonzero_exit",
                        command_repr="claude -r stale-id -p ping",
                        elapsed_ms=10,
                        return_code=1,
                        stderr_lines=["No conversation found with session ID: stale-id"],
                    )
                return {"text": "ok", "session_id": "fresh-id", "elapsed_ms": 1}

            with patch(
                "src.invoke.PROVIDERS", {"claude-minimax": fake_provider}
            ), patch(
                "src.invoke.get_session_id", return_value="stale-id"
            ) as mock_get_session, patch(
                "src.invoke.clear_session_id"
            ) as mock_clear_session, patch(
                "src.invoke.set_session_id"
            ) as mock_set_session:
                result = invoke(
                    "claude-minimax",
                    "ping",
                    config_path=str(config_path),
                    stream=False,
                )

            self.assertEqual(result["text"], "ok")
            self.assertEqual(call_sessions, ["stale-id", None])
            mock_get_session.assert_called_once_with("claude-minimax")
            mock_clear_session.assert_called_once_with("claude-minimax")
            mock_set_session.assert_called_once_with("claude-minimax", "fresh-id")

    def test_gemini_ssl_network_error_is_retryable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.toml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    [defaults]
                    retry_backoff_s = 0.0

                    [providers.gemini]
                    retry_attempts = 1
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            call_count = {"n": 0}

            def fake_provider(**kwargs):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    raise ProcessExecutionError(
                        provider="gemini",
                        reason="nonzero_exit",
                        command_repr="gemini -p ping",
                        elapsed_ms=10,
                        return_code=1,
                        stderr_lines=["ERR_SSL_SSL/TLS_ALERT_BAD_RECORD_MAC"],
                    )
                return {"text": "ok", "session_id": None, "elapsed_ms": 1}

            with patch("src.invoke.PROVIDERS", {"gemini": fake_provider}):
                result = invoke(
                    "gemini",
                    "ping",
                    config_path=str(config_path),
                    stream=False,
                )

            self.assertEqual(result["text"], "ok")
            self.assertEqual(call_count["n"], 2)


if __name__ == "__main__":
    unittest.main()
