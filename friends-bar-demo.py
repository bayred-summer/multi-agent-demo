#!/usr/bin/env python
"""Friends Bar Phase0 demo script: run multi-agent collaboration."""

from __future__ import annotations

import argparse
import sys

from src.friends_bar.orchestrator import run_two_agent_dialogue


def build_parser() -> argparse.ArgumentParser:
    """Build command-line parser."""
    parser = argparse.ArgumentParser(
        description="Friends Bar multi-agent demo (duffy -> linabell -> stella)",
    )
    parser.add_argument("prompt", help="User task, e.g. design a minimal MVP")
    parser.add_argument(
        "--rounds",
        type=int,
        default=None,
        help="Total turns (one agent per turn), default from config.toml",
    )
    parser.add_argument(
        "--start-agent",
        default=None,
        help=(
            "First turn agent. Supported: linabell / duffy / stella / codex / "
            "claude-minimax / gemini / 玲娜贝儿 / 达菲 / 星黛露. Default from config.toml"
        ),
    )
    parser.add_argument(
        "--project-path",
        default=None,
        help="Task working directory; defaults to current directory",
    )
    session_group = parser.add_mutually_exclusive_group()
    session_group.add_argument(
        "--use-session",
        dest="use_session",
        action="store_true",
        help="Force-enable provider session resume",
    )
    session_group.add_argument(
        "--no-session",
        dest="use_session",
        action="store_false",
        help="Force-disable provider session resume",
    )
    parser.set_defaults(use_session=None)
    parser.add_argument(
        "--timeout-level",
        default="standard",
        help="Timeout profile: quick / standard / complex",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only build prompt/schema without invoking providers",
    )
    parser.add_argument(
        "--dump-prompt",
        nargs="?",
        const="-",
        default=None,
        help="Dump the prompt to stdout or to a file path (use '-' for stdout)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional deterministic seed for the run",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose agent stream logs (raw provider lines and tool events)",
    )
    return parser


def main() -> int:
    """Program entry point."""
    args = build_parser().parse_args()
    try:
        run_two_agent_dialogue(
            args.prompt,
            rounds=args.rounds,
            start_agent=args.start_agent,
            project_path=args.project_path,
            use_session=args.use_session,
            stream=True,
            stream_debug=args.debug,
            timeout_level=args.timeout_level,
            config_path="config.toml",
            seed=args.seed,
            dry_run=args.dry_run,
            dump_prompt=args.dump_prompt if (args.dump_prompt or args.dry_run) else None,
        )
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


