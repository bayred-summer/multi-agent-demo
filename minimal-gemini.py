#!/usr/bin/env python
"""Minimal Gemini invoke script."""

from __future__ import annotations

import sys

from src.invoke import invoke


def main() -> int:
    """Run one Gemini prompt through unified invoke."""
    prompt = " ".join(sys.argv[1:]).strip()
    if not prompt:
        print('Usage: python minimal-gemini.py "your prompt"', file=sys.stderr)
        return 1

    try:
        # Session behavior follows config.toml (default: enabled).
        invoke("gemini", prompt)
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
