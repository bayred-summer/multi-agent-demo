#!/usr/bin/env python
"""统一调用接口演示脚本。"""

from __future__ import annotations

import sys

from src.invoke import invoke


def main() -> int:
    """演示如何通过统一入口调用多个 provider。"""
    try:
        # 先调用占位 provider（不启用会话恢复）。
        invoke("xxx", "hello", use_session=False, stream=True)
        # 再调用 codex provider（启用会话恢复）。
        invoke("codex", "hello", use_session=True, stream=True)
        # 最后调用 Claude MiniMax provider（启用会话恢复）。
        invoke("claude-minimax", "hello", use_session=True, stream=True)
        return 0
    except Exception as exc:
        # 把运行异常打印到 stderr，方便定位问题。
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
