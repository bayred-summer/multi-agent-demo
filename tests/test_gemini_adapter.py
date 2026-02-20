"""Gemini adapter behavior tests."""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.providers.gemini import invoke_gemini
from src.utils.process_runner import ProcessExecutionError


class TestGeminiAdapter(unittest.TestCase):
    """Covers antigravity callback adapter behavior."""

    def test_antigravity_callback_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            rid = "req-test-001"
            root = Path(tmp_dir)

            def _writer() -> None:
                time.sleep(0.1)
                response_path = root / "responses" / f"{rid}.json"
                response_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path = response_path.with_suffix(".json.tmp")
                tmp_path.write_text(
                    json.dumps(
                        {
                            "request_id": rid,
                            "status": "ok",
                            "text": "hello-from-mcp",
                            "session_id": "mcp-session-1",
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                tmp_path.replace(response_path)

            t = threading.Thread(target=_writer, daemon=True)
            t.start()
            result = invoke_gemini(
                "ping",
                stream=False,
                adapter="antigravity",
                mcp_callback_dir=str(root),
                mcp_request_id=rid,
                mcp_poll_interval_s=0.05,
                mcp_timeout_s=3.0,
            )
            t.join(timeout=1.0)

            self.assertEqual(result["text"], "hello-from-mcp")
            self.assertEqual(result["session_id"], "mcp-session-1")
            request_file = root / "requests" / f"{rid}.json"
            self.assertTrue(request_file.exists())

    def test_antigravity_callback_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(ProcessExecutionError) as ctx:
                invoke_gemini(
                    "ping",
                    stream=False,
                    adapter="antigravity",
                    mcp_callback_dir=tmp_dir,
                    mcp_request_id="req-timeout-001",
                    mcp_poll_interval_s=0.05,
                    mcp_timeout_s=0.2,
                )
            self.assertEqual(ctx.exception.reason, "mcp_callback_timeout")

    def test_cli_proxy_env_is_injected(self) -> None:
        captured: dict[str, object] = {}

        def _fake_run_stream_process(**kwargs):
            captured["env"] = kwargs.get("env")
            on_stdout_line = kwargs["on_stdout_line"]
            on_stdout_line(
                json.dumps(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": "proxy-ok",
                        "delta": True,
                    },
                    ensure_ascii=False,
                )
            )
            return SimpleNamespace(elapsed_ms=12)

        with patch("src.providers.gemini.resolve_gemini_command", return_value="gemini"), patch(
            "src.providers.gemini.run_stream_process",
            side_effect=_fake_run_stream_process,
        ):
            result = invoke_gemini(
                "ping",
                stream=False,
                adapter="gemini-cli",
                output_format="stream-json",
                proxy="http://127.0.0.1:7890",
                no_proxy="localhost,127.0.0.1",
            )

        env = captured.get("env")
        self.assertIsInstance(env, dict)
        assert isinstance(env, dict)
        self.assertEqual(env.get("HTTP_PROXY"), "http://127.0.0.1:7890")
        self.assertEqual(env.get("HTTPS_PROXY"), "http://127.0.0.1:7890")
        self.assertEqual(env.get("NO_PROXY"), "localhost,127.0.0.1")
        self.assertEqual(result["text"], "proxy-ok")

    def test_cli_proxy_sets_default_no_proxy_when_missing(self) -> None:
        captured: dict[str, object] = {}

        def _fake_run_stream_process(**kwargs):
            captured["env"] = kwargs.get("env")
            on_stdout_line = kwargs["on_stdout_line"]
            on_stdout_line(
                json.dumps(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": "ok",
                        "delta": True,
                    }
                )
            )
            return SimpleNamespace(elapsed_ms=8)

        with patch("src.providers.gemini.resolve_gemini_command", return_value="gemini"), patch(
            "src.providers.gemini.run_stream_process",
            side_effect=_fake_run_stream_process,
        ):
            invoke_gemini(
                "ping",
                stream=False,
                adapter="gemini-cli",
                output_format="stream-json",
                proxy="http://127.0.0.1:7890",
            )

        env = captured.get("env")
        self.assertIsInstance(env, dict)
        assert isinstance(env, dict)
        self.assertEqual(env.get("NO_PROXY"), "localhost,127.0.0.1")
        self.assertEqual(env.get("no_proxy"), "localhost,127.0.0.1")


if __name__ == "__main__":
    unittest.main()
