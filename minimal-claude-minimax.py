#!/usr/bin/env python
"""最小化 Claude MiniMax 调用入口脚本。"""

from __future__ import annotations

import sys

from src.invoke import invoke


def main() -> int:
    """程序主入口。

    职责：
    1. 读取命令行 prompt
    2. 调用统一入口 invoke("claude-minimax", ...)
    3. 通过 session 自动续聊
    """
    prompt = " ".join(sys.argv[1:]).strip()
    if not prompt:
        print('Usage: python minimal-claude-minimax.py "your prompt"', file=sys.stderr)
        return 1

    try:
        # 默认行为由 config.toml 决定；这里仅指定 provider 与 prompt。
        invoke("claude-minimax", prompt)
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
