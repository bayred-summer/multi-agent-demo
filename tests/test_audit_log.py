"""Audit logging tests for Friends Bar."""

from __future__ import annotations

import json
import tempfile
import unittest

from src.utils.audit_log import AuditLogConfig, AuditLogger, text_meta


class TestAuditLog(unittest.TestCase):
    """Covers standalone logger behavior."""

    def test_text_meta_contains_hash_and_preview(self) -> None:
        meta = text_meta("hello world", include_preview=True, max_preview_chars=5)
        self.assertEqual(meta["chars"], 11)
        self.assertEqual(meta["preview"], "hello")
        self.assertIn("sha256", meta)

    def test_logger_writes_jsonl_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            logger = AuditLogger(
                AuditLogConfig(
                    enabled=True,
                    log_dir=tmp_dir,
                    include_prompt_preview=True,
                    max_preview_chars=200,
                )
            )
            logger.log("run.started", {"user_request": "demo"})
            logger.log("turn.completed", {"turn": 1, "final_text": "ok"})
            logger.finalize(status="success", summary={"turns_completed": 1})

            self.assertIsNotNone(logger.log_file)
            self.assertIsNotNone(logger.summary_file)
            assert logger.log_file is not None
            assert logger.summary_file is not None

            self.assertTrue(logger.log_file.exists())
            self.assertTrue(logger.summary_file.exists())

            lines = [
                json.loads(line)
                for line in logger.log_file.read_text(encoding="utf-8").splitlines()
            ]
            self.assertGreaterEqual(len(lines), 3)
            self.assertEqual(lines[0]["event"], "run.started")
            self.assertEqual(lines[1]["event"], "turn.completed")
            self.assertEqual(lines[-1]["event"], "run.finalized")

            summary = json.loads(logger.summary_file.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "success")
            self.assertEqual(summary["turns_completed"], 1)
            self.assertEqual(summary["run_id"], logger.run_id)


if __name__ == "__main__":
    unittest.main()
