"""Tests for provider-specific invoke defaults."""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from src.invoke import invoke


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


if __name__ == "__main__":
    unittest.main()
