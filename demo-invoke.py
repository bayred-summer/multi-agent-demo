#!/usr/bin/env python
"""统一调用接口演示脚本。"""

from __future__ import annotations

import sys

from src.invoke import invoke


def main() -> int:
    """演示如何通过统一入口调用多个 provider。"""
    try:
        # 先调用占位 provider（示例中显式关闭会话，覆盖配置文件）。
        invoke("xxx", "hello", use_session=False)
        # 再调用 codex provider（使用 config.toml 默认参数）。
        invoke("codex", "hello")
        # 最后调用 Claude MiniMax provider（使用 config.toml 默认参数）。
        invoke("claude-minimax", "hello")
        return 0
    except Exception as exc:
        # 把运行异常打印到 stderr，方便定位问题。
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
