#!/usr/bin/env python
"""最小化 Codex 调用入口脚本。"""

from __future__ import annotations

import sys

from src.invoke import invoke


def main() -> int:
    """程序主入口。

    职责：
    1. 读取命令行 prompt
    2. 调用统一入口 invoke("codex", ...)
    3. 把成功/失败转换为标准退出码
    """
    # 把命令行参数拼成一句完整提问，支持带空格的输入。
    prompt = " ".join(sys.argv[1:]).strip()
    if not prompt:
        # 用户未传 prompt 时，输出用法并返回非 0。
        print('Usage: python minimal-codex.py "your prompt"', file=sys.stderr)
        return 1

    try:
        # 默认行为由 config.toml 决定；这里仅指定 provider 与 prompt。
        invoke("codex", prompt)
        return 0
    except Exception as exc:
        # 统一把异常打印到 stderr，便于在终端或 CI 中排查。
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
