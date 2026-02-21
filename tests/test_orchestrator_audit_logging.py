"""Integration-like tests for orchestrator audit logging."""

from __future__ import annotations

import json
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from src.friends_bar.orchestrator import (
    _command_workdir_errors,
    _ensure_allowed_roots,
    _path_within,
    run_two_agent_dialogue,
)


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
                {"command": "cat model.py", "result": "readable"},
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

    def test_path_guard_rejects_prefix_sibling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "root"
            sibling = Path(tmp_dir) / "root_evil"
            root.mkdir(parents=True, exist_ok=True)
            sibling.mkdir(parents=True, exist_ok=True)

            self.assertTrue(_path_within(root / "nested", root))
            self.assertFalse(_path_within(sibling / "nested", root))
            with self.assertRaises(ValueError):
                _ensure_allowed_roots(str(sibling), [str(root)])

    def test_command_workdir_guard_detects_outside_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workdir = Path(tmp_dir) / "workdir"
            outside = Path(tmp_dir) / "outside"
            workdir.mkdir(parents=True, exist_ok=True)
            outside.mkdir(parents=True, exist_ok=True)

            errors = _command_workdir_errors(
                [
                    f"cd {outside} && ls -la",
                    f"cat {workdir / 'inside.txt'}",
                ],
                workdir=str(workdir),
            )
            self.assertEqual(len(errors), 1)
            self.assertIn("E_WORKDIR_COMMAND_OUTSIDE", errors[0])
            self.assertIn(str(outside), errors[0])

    def test_run_auto_resolves_project_path_from_user_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            requested_workdir = Path(tmp_dir) / "target_project"
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

            seen_workdirs: list[str] = []

            def _fake_invoke_resolved_workdir(
                cli: str,
                prompt: str,
                *,
                workdir: str | None = None,
                **kwargs,
            ):
                if workdir:
                    seen_workdirs.append(workdir)

                if cli == "duffy":
                    text = json.dumps(
                        {
                            "schema_version": "friendsbar.plan.v1",
                            "status": "ok",
                            "result": {
                                "requirement_breakdown": ["创建工程目录", "实现最小闭环"],
                                "implementation_scope": "MVP",
                                "acceptance_criteria": ["代码可运行", "验收可复现"],
                                "handoff_notes": "在统一执行目录完成开发与验收",
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
                        "session_id": None,
                        "elapsed_ms": 10,
                    }

                if cli == "linabell":
                    assert workdir is not None
                    target_file = Path(workdir) / "artifact.txt"
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    target_file.write_text("ok\n", encoding="utf-8")
                    text = json.dumps(
                        {
                            "schema_version": "friendsbar.delivery.v1",
                            "status": "ok",
                            "result": {
                                "task_understanding": "在统一目录交付最小工程",
                                "implementation_plan": "生成文件并给出验收证据",
                                "execution_evidence": [
                                    {
                                        "command": f"cd {workdir} && ls -la",
                                        "result": "artifact 落盘",
                                    }
                                ],
                                "risks_and_rollback": "无",
                                "deliverables": [
                                    {
                                        "path": "artifact.txt",
                                        "kind": "file",
                                        "summary": "最小交付文件",
                                    }
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
                        "session_id": None,
                        "elapsed_ms": 10,
                    }

                assert workdir is not None
                text = json.dumps(
                    {
                        "schema_version": "friendsbar.review.v1",
                        "status": "ok",
                        "acceptance": "pass",
                        "verification": [
                            {"command": f"cd {workdir} && ls -la", "result": "目录可访问"},
                            {"command": "python -m pytest -q", "result": "1 passed"},
                        ],
                        "root_cause": [],
                        "issues": [],
                        "gate": {"decision": "allow", "conditions": []},
                        "next_question": "达菲是否结束任务？",
                        "warnings": [],
                        "errors": [],
                    },
                    ensure_ascii=False,
                )
                return {
                    "cli": "gemini",
                    "text": text,
                    "session_id": None,
                    "elapsed_ms": 10,
                }

            user_request = f"请在{requested_workdir}目录下完成开发并验收闭环"
            with patch(
                "src.friends_bar.orchestrator.invoke",
                side_effect=_fake_invoke_resolved_workdir,
            ):
                result = run_two_agent_dialogue(
                    user_request,
                    rounds=3,
                    start_agent="duffy",
                    project_path=None,
                    use_session=False,
                    stream=False,
                    timeout_level="quick",
                    config_path=str(config_path),
                )

            self.assertTrue(requested_workdir.exists())
            self.assertTrue(requested_workdir.is_dir())
            self.assertTrue((requested_workdir / "artifact.txt").exists())
            self.assertTrue(seen_workdirs)
            self.assertTrue(all(Path(item) == requested_workdir for item in seen_workdirs))

            log_file = Path(result["log"]["log_file"])
            events = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
            run_started = next(item for item in events if item["event"] == "run.started")
            args = run_started["payload"]["args"]
            self.assertEqual(args["project_path"], str(requested_workdir))
            self.assertEqual(args["project_path_source"], "user_request")

    def test_run_requires_explicit_or_inferred_workdir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.toml"
            logs_dir = Path(tmp_dir) / "logs"
            config_path.write_text(
                textwrap.dedent(
                    f"""
                    [friends_bar]
                    default_rounds = 1
                    start_agent = "duffy"

                    [friends_bar.logging]
                    enabled = true
                    dir = "{logs_dir.as_posix()}"
                    include_prompt_preview = true
                    max_preview_chars = 200
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as ctx:
                run_two_agent_dialogue(
                    "请实现一个最小可运行示例",
                    rounds=1,
                    start_agent="duffy",
                    project_path=None,
                    use_session=False,
                    stream=False,
                    timeout_level="quick",
                    config_path=str(config_path),
                )

            self.assertIn("workdir must be explicitly specified", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
