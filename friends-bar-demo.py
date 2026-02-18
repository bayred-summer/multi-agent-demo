#!/usr/bin/env python
"""Friends Bar Phase0 演示脚本：运行“玲娜贝儿/达菲”双 Agent 协作。"""

from __future__ import annotations

import argparse
import sys

from src.friends_bar.orchestrator import run_two_agent_dialogue


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="Friends Bar 双 Agent 协作演示（玲娜贝儿 <-> 达菲）",
    )
    parser.add_argument("prompt", help="用户任务，例如：设计一个最小 MVP 方案")
    parser.add_argument(
        "--rounds",
        type=int,
        default=None,
        help="总轮次（每轮一个 Agent 发言），默认读取 config.toml",
    )
    parser.add_argument(
        "--start-agent",
        default=None,
        help="首轮 Agent，支持：玲娜贝儿 / 达菲 / codex / claude-minimax；默认读取 config.toml",
    )
    parser.add_argument(
        "--project-path",
        default=None,
        help="任务执行目录；为空时使用当前目录",
    )
    parser.add_argument(
        "--use-session",
        action="store_true",
        help="启用 provider session 续聊（默认关闭）",
    )
    parser.add_argument(
        "--timeout-level",
        default="standard",
        help="超时档位：quick / standard / complex",
    )
    return parser


def main() -> int:
    """程序主入口。"""
    args = build_parser().parse_args()
    try:
        run_two_agent_dialogue(
            args.prompt,
            rounds=args.rounds,
            start_agent=args.start_agent,
            project_path=args.project_path,
            use_session=args.use_session,
            stream=True,
            timeout_level=args.timeout_level,
            config_path="config.toml",
        )
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
