"""Friends Bar 的 Agent 定义与名称映射。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class AgentProfile:
    """单个 Agent 的基础配置。"""

    name: str
    provider: str
    mission: str


AGENTS: Dict[str, AgentProfile] = {
    "玲娜贝儿": AgentProfile(
        name="玲娜贝儿",
        provider="codex",
        mission="偏重工程落地与风险校验，给出可执行方案。",
    ),
    "达菲": AgentProfile(
        name="达菲",
        provider="claude-minimax",
        mission="偏重问题澄清与结构化思考，补充上下文与权衡。",
    ),
}

# 兼容用户可能输入的英文/技术别名。
AGENT_NAME_ALIASES = {
    "codex": "玲娜贝儿",
    "claude-minimax": "达菲",
    "claude_minimax": "达菲",
    "玲娜贝儿": "玲娜贝儿",
    "达菲": "达菲",
}


def normalize_agent_name(name: str) -> str:
    """把任意输入映射到 Friends Bar 规范 Agent 名称。"""
    raw = (name or "").strip()
    if raw in AGENT_NAME_ALIASES:
        return AGENT_NAME_ALIASES[raw]
    lower_raw = raw.lower()
    normalized = AGENT_NAME_ALIASES.get(lower_raw)
    if normalized is None:
        supported = ", ".join(sorted(AGENTS))
        raise ValueError(f"Unsupported agent name: {name}. Supported: {supported}")
    return normalized
