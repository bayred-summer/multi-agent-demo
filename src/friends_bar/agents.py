"""Friends Bar agent profiles and name normalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

# Canonical internal IDs (ASCII only).
LINA_BELL = "linabell"
DUFFY = "duffy"
STELLA = "stella"

# Display names.
LINA_BELL_ZH = "玲娜贝儿"
DUFFY_ZH = "达菲"
STELLA_ZH = "星黛露"

# Backward-compatible mojibake aliases seen in old config files.
LINA_BELL_MOJIBAKE = "歆庫彻甏旊灴"
DUFFY_MOJIBAKE = "雽勲穮"
STELLA_MOJIBAKE = "鏄熼化闇?"


@dataclass(frozen=True)
class AgentProfile:
    """Static profile for one agent."""

    name: str
    display_name: str
    provider: str
    mission: str


AGENTS: Dict[str, AgentProfile] = {
    LINA_BELL: AgentProfile(
        name=LINA_BELL,
        display_name=LINA_BELL_ZH,
        provider="codex",
        mission=(
            "兼职开发实现 + 发布运维："
            "代码落地、脚本、部署、环境问题处理。"
        ),
    ),
    DUFFY: AgentProfile(
        name=DUFFY,
        display_name=DUFFY_ZH,
        provider="claude-minimax",
        mission=(
            "产品经理："
            "负责需求拆解、范围边界定义、优先级与验收目标设定，"
            "将可执行任务清晰交接给玲娜贝儿。"
        ),
    ),
    STELLA: AgentProfile(
        name=STELLA,
        display_name=STELLA_ZH,
        provider="gemini",
        mission=(
            "资深 Code Reviewer（兼 QA 测试负责人）："
            "以缺陷发现和质量门禁为核心，输出可复现证据、风险评估、回归策略与最终合入结论。"
        ),
    ),
}

# Aliases users may input.
AGENT_NAME_ALIASES = {
    # Provider names
    "codex": LINA_BELL,
    "claude-minimax": DUFFY,
    "claude_minimax": DUFFY,
    "gemini": STELLA,
    "gemini-cli": STELLA,
    # Canonical IDs
    LINA_BELL: LINA_BELL,
    DUFFY: DUFFY,
    STELLA: STELLA,
    # Chinese display names
    LINA_BELL_ZH: LINA_BELL,
    DUFFY_ZH: DUFFY,
    STELLA_ZH: STELLA,
    # Legacy mojibake aliases
    LINA_BELL_MOJIBAKE: LINA_BELL,
    DUFFY_MOJIBAKE: DUFFY,
    STELLA_MOJIBAKE: STELLA,
}


def normalize_agent_name(name: str) -> str:
    """Map any user input to canonical Friends Bar agent ID."""
    raw = (name or "").strip()
    if raw in AGENT_NAME_ALIASES:
        return AGENT_NAME_ALIASES[raw]

    lower_raw = raw.lower()
    normalized = AGENT_NAME_ALIASES.get(lower_raw)
    if normalized is None:
        supported = ", ".join(sorted(AGENTS))
        raise ValueError(f"Unsupported agent name: {name}. Supported: {supported}")
    return normalized


def display_agent_name(name: str) -> str:
    """Return Chinese display name for a canonical/alias agent name."""
    canonical = normalize_agent_name(name)
    return AGENTS[canonical].display_name
