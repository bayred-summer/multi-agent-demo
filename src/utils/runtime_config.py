"""Runtime config loader (TOML) for Friends Bar."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - py<3.11 fallback
    tomllib = None

LINA_BELL = "linabell"
DUFFY = "duffy"


DEFAULT_CONFIG: Dict[str, Any] = {
    "defaults": {
        "provider": "codex",
        "use_session": True,
        "stream": True,
        "timeout_level": "standard",
        "retry_attempts": 1,
        "retry_backoff_s": 1.0,
    },
    "providers": {
        "codex": {
            "timeout_level": "standard",
            "retry_attempts": 1,
            "exec_mode": "safe",
        },
        "claude-minimax": {
            "timeout_level": "standard",
            "retry_attempts": 1,
            "permission_mode": "default",
            "include_partial_messages": False,
            "print_stderr": False,
        },
    },
    "friends_bar": {
        "name": "Friends Bar",
        "default_rounds": 4,
        "start_agent": LINA_BELL,
        "agents": {
            LINA_BELL: {
                "provider": "codex",
                "response_mode": "execute",
                "provider_options": {"exec_mode": "bypass"},
            },
            DUFFY: {
                "provider": "claude-minimax",
                "response_mode": "text_only",
                "provider_options": {
                    "permission_mode": "default",
                    "include_partial_messages": False,
                    "print_stderr": False,
                },
            },
        },
    },
    "timeouts": {
        "quick": {
            "idle_timeout_s": 60.0,
            "max_timeout_s": 300.0,
            "terminate_grace_s": 3.0,
        },
        "standard": {
            "idle_timeout_s": 300.0,
            "max_timeout_s": 1800.0,
            "terminate_grace_s": 5.0,
        },
        "complex": {
            "idle_timeout_s": 900.0,
            "max_timeout_s": 3600.0,
            "terminate_grace_s": 8.0,
        },
    },
}


def _deep_merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge dicts (override wins)."""
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _normalize_agent_map(raw_agents: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize agent map keys to canonical agent IDs."""
    try:
        from src.friends_bar.agents import normalize_agent_name  # lazy import
    except Exception:
        normalize_agent_name = None

    normalized_agents: Dict[str, Any] = {}
    for raw_name, raw_cfg in raw_agents.items():
        if not isinstance(raw_cfg, dict):
            continue
        canonical_name = str(raw_name)
        if normalize_agent_name is not None:
            try:
                canonical_name = normalize_agent_name(str(raw_name))
            except Exception:
                canonical_name = str(raw_name)

        cfg = dict(raw_cfg)
        cfg["response_mode"] = str(cfg.get("response_mode", "text_only"))
        provider_options = cfg.get("provider_options", {})
        if not isinstance(provider_options, dict):
            cfg["provider_options"] = {}
        normalized_agents[canonical_name] = cfg
    return normalized_agents


def _normalize_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize config types and enforce minimal defaults."""
    try:
        from src.friends_bar.agents import normalize_agent_name  # lazy import
    except Exception:
        normalize_agent_name = None

    normalized = _deep_merge_dict(DEFAULT_CONFIG, config)

    defaults = normalized.get("defaults", {})
    defaults["retry_attempts"] = int(defaults.get("retry_attempts", 1))
    defaults["retry_backoff_s"] = float(defaults.get("retry_backoff_s", 1.0))

    providers = normalized.get("providers", {})
    if isinstance(providers, dict):
        codex_cfg = providers.get("codex", {})
        if isinstance(codex_cfg, dict):
            codex_cfg["exec_mode"] = str(codex_cfg.get("exec_mode", "safe"))

        claude_cfg = providers.get("claude-minimax", {})
        if isinstance(claude_cfg, dict):
            claude_cfg["permission_mode"] = str(
                claude_cfg.get("permission_mode", "default")
            )
            claude_cfg["include_partial_messages"] = bool(
                claude_cfg.get("include_partial_messages", False)
            )
            claude_cfg["print_stderr"] = bool(claude_cfg.get("print_stderr", False))

    friends_bar = normalized.get("friends_bar", {})
    if isinstance(friends_bar, dict):
        friends_bar["default_rounds"] = int(friends_bar.get("default_rounds", 4))

        start_agent = str(friends_bar.get("start_agent", LINA_BELL))
        if normalize_agent_name is None:
            friends_bar["start_agent"] = start_agent
        else:
            try:
                friends_bar["start_agent"] = normalize_agent_name(start_agent)
            except Exception:
                friends_bar["start_agent"] = LINA_BELL

        raw_agents = friends_bar.get("agents", {})
        if not isinstance(raw_agents, dict):
            raw_agents = {}
        friends_bar["agents"] = _normalize_agent_map(raw_agents)

    for profile_name, profile in normalized.get("timeouts", {}).items():
        if not isinstance(profile, dict):
            normalized["timeouts"][profile_name] = DEFAULT_CONFIG["timeouts"].get(
                profile_name, {}
            )
            continue
        profile["idle_timeout_s"] = float(profile.get("idle_timeout_s", 300))
        profile["max_timeout_s"] = float(profile.get("max_timeout_s", 1800))
        profile["terminate_grace_s"] = float(profile.get("terminate_grace_s", 5))

    return normalized


def _load_toml_dict(config_file: Path) -> Dict[str, Any]:
    """Load TOML as dict, return empty dict on any failure."""
    if tomllib is None or not config_file.exists():
        return {}

    try:
        raw = tomllib.loads(config_file.read_text(encoding="utf-8-sig"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def load_runtime_config(config_path: str = "config.toml") -> Dict[str, Any]:
    """Load runtime config with optional local override."""
    config_file = Path(config_path)
    local_file = config_file.with_name(f"{config_file.stem}.local{config_file.suffix}")

    merged = copy.deepcopy(DEFAULT_CONFIG)
    merged = _deep_merge_dict(merged, _load_toml_dict(config_file))
    merged = _deep_merge_dict(merged, _load_toml_dict(local_file))
    return _normalize_config(merged)
