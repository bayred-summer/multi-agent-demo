"""运行时配置加载器（TOML）。"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - py<3.11 fallback
    tomllib = None


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
        },
    },
    "friends_bar": {
        "name": "Friends Bar",
        "default_rounds": 4,
        "start_agent": "玲娜贝儿",
        "agents": {
            "玲娜贝儿": {
                "provider": "codex",
                "response_mode": "execute",
                "provider_options": {"exec_mode": "bypass"},
            },
            "达菲": {
                "provider": "claude-minimax",
                "response_mode": "text_only",
                "provider_options": {"permission_mode": "plan"},
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
    """递归合并字典（override 覆盖 base）。"""
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _normalize_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """对配置做轻量规范化，防止类型异常。"""
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

    friends_bar = normalized.get("friends_bar", {})
    if isinstance(friends_bar, dict):
        friends_bar["default_rounds"] = int(friends_bar.get("default_rounds", 4))
        agents = friends_bar.get("agents", {})
        if isinstance(agents, dict):
            for _, agent in agents.items():
                if not isinstance(agent, dict):
                    continue
                agent["response_mode"] = str(agent.get("response_mode", "text_only"))
                provider_options = agent.get("provider_options", {})
                if not isinstance(provider_options, dict):
                    agent["provider_options"] = {}

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
    """读取 TOML 文件并返回 dict。"""
    if tomllib is None or not config_file.exists():
        return {}

    try:
        raw = tomllib.loads(config_file.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def load_runtime_config(config_path: str = "config.toml") -> Dict[str, Any]:
    """加载配置文件（支持 local 覆盖），失败时回退默认配置。"""
    config_file = Path(config_path)
    local_file = config_file.with_name(f"{config_file.stem}.local{config_file.suffix}")

    merged = copy.deepcopy(DEFAULT_CONFIG)
    merged = _deep_merge_dict(merged, _load_toml_dict(config_file))
    merged = _deep_merge_dict(merged, _load_toml_dict(local_file))
    return _normalize_config(merged)
