#!/usr/bin/env python
"""统一调用接口演示脚本。"""

from __future__ import annotations

import sys

from src.invoke import invoke


def main() -> int:
    """演示如何通过统一入口调用多个 provider。"""
    try:
        # 直接用 Friends Bar 的中文命名触发调用：
        # - 玲娜贝儿 => codex
        # - 达菲 => claude-minimax
        invoke("玲娜贝儿", "请用一句话介绍你在 Friends Bar 的职责", use_session=False)
        invoke("达菲", "请用一句话介绍你在 Friends Bar 的职责", use_session=False)
        return 0
    except Exception as exc:
        # 把运行异常打印到 stderr，方便定位问题。
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
