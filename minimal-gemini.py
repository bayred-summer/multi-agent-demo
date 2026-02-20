#!/usr/bin/env python
"""Minimal Gemini invoke script."""

from __future__ import annotations

import argparse
import sys

from src.invoke import invoke


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build CLI parser for minimal Gemini smoke calls."""
    parser = argparse.ArgumentParser(
        description="Minimal Gemini invoke entry (supports include-directories)."
    )
    parser.add_argument("prompt", nargs="+", help="Prompt text")
    parser.add_argument(
        "--workdir",
        default=None,
        help="Execution working directory for provider subprocess",
    )
    parser.add_argument(
        "--include-directories",
        dest="include_directories",
        action="append",
        default=[],
        help="Additional Gemini workspace directories (repeatable)",
    )
    return parser


def main() -> int:
    """Run one Gemini prompt through unified invoke."""
    parser = _build_arg_parser()
    args = parser.parse_args()
    prompt = " ".join(args.prompt).strip()

    try:
        provider_options = {}
        if args.include_directories:
            provider_options["include_directories"] = args.include_directories
        invoke(
            "gemini",
            prompt,
            workdir=args.workdir,
            provider_options=provider_options or None,
        )
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
