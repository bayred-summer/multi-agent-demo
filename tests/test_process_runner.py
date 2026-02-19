"""Non-functional regression tests for process runner stability."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from src.utils.process_runner import (
    ProcessExecutionError,
    TimeoutConfig,
    _build_command_repr,
    run_stream_process,
)


class _FakeStream:
    """Simple stream that reaches EOF immediately."""

    def read(self, _size: int) -> str:
        return ""


class _IdleProcess:
    """Fake process that stays alive until terminate/kill is called."""

    def __init__(self) -> None:
        self.stdout = _FakeStream()
        self.stderr = _FakeStream()
        self._return_code = None
        self.terminate_calls = 0
        self.kill_calls = 0

    def poll(self):
        return self._return_code

    def terminate(self) -> None:
        self.terminate_calls += 1
        self._return_code = 143

    def kill(self) -> None:
        self.kill_calls += 1
        self._return_code = -9

    def wait(self, timeout=None):  # noqa: ANN001 - subprocess compatible signature
        if self._return_code is None:
            self._return_code = 0
        return self._return_code


class TestProcessRunner(unittest.TestCase):
    """Covers timeout/termination behavior without external CLI dependency."""

    def test_command_repr_is_truncated(self) -> None:
        long_arg = "x" * 1000
        rendered = _build_command_repr("cmd", [long_arg], None, max_chars=40)
        self.assertIn("...<truncated", rendered)
        self.assertLessEqual(len(rendered), 80)

    def test_idle_timeout_terminates_process(self) -> None:
        fake_process = _IdleProcess()

        with patch("subprocess.Popen", return_value=fake_process):
            with self.assertRaises(ProcessExecutionError) as ctx:
                run_stream_process(
                    provider="test",
                    command="dummy",
                    args=[],
                    workdir=None,
                    timeout=TimeoutConfig(
                        idle_timeout_s=0.01,
                        max_timeout_s=1.0,
                        terminate_grace_s=0.0,
                    ),
                    stream_stderr=False,
                    stderr_prefix="",
                    on_stdout_line=lambda _line: None,
                )

        self.assertEqual(ctx.exception.reason, "idle_timeout")
        self.assertGreaterEqual(fake_process.terminate_calls, 1)


if __name__ == "__main__":
    unittest.main()
