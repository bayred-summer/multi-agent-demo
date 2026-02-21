"""Integration-like tests for orchestrator audit logging."""

from __future__ import annotations

import json
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from src.friends_bar.orchestrator import run_two_agent_dialogue


def _fake_invoke(
    cli: str,
    prompt: str,
    *,
    use_session: bool = False,
    stream: bool = False,
    workdir: str | None = None,
    provider_options: dict | None = None,
    timeout_level: str | None = None,
    run_id: str | None = None,
    seed: int | None = None,
    dry_run: bool = False,
    event_hook=None,
    config_path: str = "config.toml",
):
    """Deterministic invoke stub for PM -> Dev -> Reviewer turns."""
    if cli == "duffy":
        text = json.dumps(
            {
                "schema_version": "friendsbar.plan.v1",
                "status": "ok",
                "result": {
                    "requirement_breakdown": ["任务A", "任务B"],
                    "implementation_scope": "MVP",
                    "acceptance_criteria": ["可运行", "有测试"],
                    "handoff_notes": "优先完成核心路径",
                },
                "next_question": "玲娜贝儿是否开始实现？",
                "warnings": [],
                "errors": [],
            },
            ensure_ascii=False,
        )
        return {
            "cli": "claude-minimax",
            "text": text,
            "session_id": "session-duffy",
            "elapsed_ms": 9,
            "run_id": run_id,
            "seed": seed,
        }

    if cli == "linabell":
        text = json.dumps(
            {
                "schema_version": "friendsbar.delivery.v1",
                "status": "ok",
                "result": {
                    "task_understanding": "goal",
                    "implementation_plan": "plan",
                    "execution_evidence": [
                        {"command": "python -V", "result": "Python 3.12"}
                    ],
                    "risks_and_rollback": "none",
                    "deliverables": [
                        {"path": "train.py", "kind": "file", "summary": "entrypoint"}
                    ],
                },
                "next_question": "星黛露是否开始评审？",
                "warnings": [],
                "errors": [],
            },
            ensure_ascii=False,
        )
        return {
            "cli": "codex",
            "text": text,
            "session_id": "session-linabell",
            "elapsed_ms": 10,
            "run_id": run_id,
            "seed": seed,
        }

    text = json.dumps(
        {
            "schema_version": "friendsbar.review.v1",
            "status": "ok",
            "acceptance": "pass",
            "verification": [
                {"command": "Get-Content model.py", "result": "readable"},
                {"command": "python -m pytest -q", "result": "1 passed"},
            ],
            "root_cause": ["none"],
            "issues": [],
            "gate": {"decision": "allow", "conditions": []},
            "next_question": "达菲是否更新下一轮需求？",
            "warnings": [],
            "errors": [],
        },
        ensure_ascii=False,
    )
    return {
        "cli": "gemini",
        "text": text,
        "session_id": "session-stella",
        "elapsed_ms": 11,
        "run_id": run_id,
        "seed": seed,
    }


class TestOrchestratorAuditLogging(unittest.TestCase):
    """Verifies that user request and agent JSON replies are persisted."""

    def test_run_writes_user_request_and_turn_replies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workdir = Path(tmp_dir) / "workspace"
            workdir.mkdir(parents=True, exist_ok=True)
            (workdir / "train.py").write_text("print('ok')\n", encoding="utf-8")
            config_path = Path(tmp_dir) / "config.toml"
            logs_dir = Path(tmp_dir) / "logs"

            config_path.write_text(
                textwrap.dedent(
                    f"""
                    [friends_bar]
                    default_rounds = 3
                    start_agent = "duffy"

                    [friends_bar.logging]
                    enabled = true
                    dir = "{logs_dir.as_posix()}"
                    include_prompt_preview = true
                    max_preview_chars = 300
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            with patch("src.friends_bar.orchestrator.invoke", side_effect=_fake_invoke):
                result = run_two_agent_dialogue(
                    "请检查最小任务",
                    rounds=3,
                    start_agent="duffy",
                    project_path=str(workdir),
                    use_session=False,
                    stream=False,
                    timeout_level="quick",
                    config_path=str(config_path),
                )

            log_file = result["log"]["log_file"]
            summary_file = result["log"]["summary_file"]
            self.assertIsNotNone(log_file)
            self.assertIsNotNone(summary_file)
            self.assertTrue(Path(log_file).exists())
            self.assertTrue(Path(summary_file).exists())

            events = [
                json.loads(line)
                for line in Path(log_file).read_text(encoding="utf-8").splitlines()
            ]
            run_started = next(item for item in events if item["event"] == "run.started")
            self.assertEqual(run_started["payload"]["user_request"], "请检查最小任务")
            self.assertIn("seed", run_started)

            turn_completed = [item for item in events if item["event"] == "turn.completed"]
            self.assertEqual(len(turn_completed), 3)
            pm_payload = json.loads(turn_completed[0]["payload"]["final_text"])
            dev_payload = json.loads(turn_completed[1]["payload"]["final_text"])
            review_payload = json.loads(turn_completed[2]["payload"]["final_text"])
            self.assertEqual(pm_payload["schema_version"], "friendsbar.plan.v1")
            self.assertEqual(dev_payload["schema_version"], "friendsbar.delivery.v1")
            self.assertEqual(review_payload["schema_version"], "friendsbar.review.v1")

            summary = json.loads(Path(summary_file).read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "success")
            self.assertEqual(summary["turns_completed"], 3)
            self.assertEqual(len(summary["turns"]), 3)


if __name__ == "__main__":
    unittest.main()
