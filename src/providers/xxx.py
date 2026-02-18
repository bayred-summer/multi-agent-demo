"""预留 provider（占位实现）。"""

from __future__ import annotations

from typing import Any, Dict, Optional


def invoke_xxx(
    prompt: str,
    session_id: Optional[str] = None,
    stream: bool = True,
    *,
    timeout_level: str = "standard",
    idle_timeout_s: Optional[float] = None,
    max_timeout_s: Optional[float] = None,
    terminate_grace_s: Optional[float] = None,
) -> Dict[str, Any]:
    """调用占位 provider。

    说明：
    - 当前不连接真实模型
    - 仅回显输入，便于先跑通统一接口
    """
    # 预留参数：后续真实接入时可用于会话恢复。
    _ = session_id
    _ = timeout_level
    _ = idle_timeout_s
    _ = max_timeout_s
    _ = terminate_grace_s

    text = f"[xxx placeholder] prompt received: {prompt}"
    if stream:
        # 模拟流式输出：这里直接一次性打印文本。
        print(text)

    return {
        "provider": "xxx",
        "text": text,
        "session_id": None,
    }
