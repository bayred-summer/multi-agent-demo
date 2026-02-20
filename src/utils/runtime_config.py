"""Runtime config loader (TOML) for Friends Bar."""

from __future__ import annotations

import copy
import os
import sys
from pathlib import Path
from typing import Any, Dict

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - py<3.11 fallback
    tomllib = None

LINA_BELL = "linabell"
DUFFY = "duffy"
STELLA = "stella"
DEBUG_ENV = "FRIENDS_BAR_DEBUG"

_CONFIG_CACHE: Dict[str, Dict[str, Any]] = {}


def _debug_log(message: str) -> None:
    """Print optional debug logs when FRIENDS_BAR_DEBUG is enabled."""
    if os.environ.get(DEBUG_ENV):
        print(f"[runtime_config] {message}", file=sys.stderr)


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
            "use_session": True,
            "exec_mode": "safe",
        },
        "claude-minimax": {
            "timeout_level": "standard",
            "retry_attempts": 1,
            "use_session": True,
            "permission_mode": "bypassPermissions",
            "include_partial_messages": False,
            "print_stderr": False,
        },
        "gemini": {
            "timeout_level": "standard",
            "retry_attempts": 1,
            "use_session": True,
            "adapter": "gemini-cli",
            "auth_mode": "auto",
            "approval_mode": "default",
            "output_format": "stream-json",
            "yolo": False,
            "no_browser": False,
            "proxy": "",
            "no_proxy": "",
            "proxy_args": False,
            "include_directories": [],
            "print_stderr": False,
            "mcp_callback_dir": ".gemini/mcp_bridge",
            "mcp_poll_interval_s": 0.25,
            "mcp_timeout_s": 300.0,
            "mcp_cleanup_response": True,
        },
    },
    "friends_bar": {
        "name": "Friends Bar",
        "default_rounds": 4,
        "start_agent": DUFFY,
        "logging": {
            "enabled": True,
            "dir": ".friends-bar/logs",
            "include_prompt_preview": True,
            "max_preview_chars": 1200,
        },
        "history": {
            "max_chars": 3000,
            "field_max_chars": 400,
            "evidence_limit": 3,
            "issue_limit": 5,
            "root_cause_limit": 3,
            "include_key_changes": True,
        },
        "safety": {
            "read_only": False,
            "allowed_roots": [],
            "command_allowlist": [],
            "command_denylist": [],
            "codex_sandbox_read_only": "read-only",
            "codex_sandbox_default": "workspace-write",
            "claude_tools_read_only": "Read",
        },
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
                    "permission_mode": "bypassPermissions",
                    "include_partial_messages": True,
                    "print_stderr": False,
                },
            },
            STELLA: {
                "provider": "gemini",
                "response_mode": "execute",
                "provider_options": {
                    "adapter": "gemini-cli",
                    "output_format": "stream-json",
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
    except (ImportError, AttributeError) as exc:
        _debug_log(f"normalize_agent_name import failed: {exc}")
        normalize_agent_name = None

    normalized_agents: Dict[str, Any] = {}
    for raw_name, raw_cfg in raw_agents.items():
        if not isinstance(raw_cfg, dict):
            continue
        canonical_name = str(raw_name)
        if normalize_agent_name is not None:
            try:
                canonical_name = normalize_agent_name(str(raw_name))
            except ValueError as exc:
                _debug_log(f"normalize agent name failed: {exc}")
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
    except (ImportError, AttributeError) as exc:
        _debug_log(f"normalize_agent_name import failed: {exc}")
        normalize_agent_name = None

    normalized = _deep_merge_dict(DEFAULT_CONFIG, config)

    defaults = normalized.get("defaults", {})
    defaults["retry_attempts"] = int(defaults.get("retry_attempts", 1))
    defaults["retry_backoff_s"] = float(defaults.get("retry_backoff_s", 1.0))

    providers = normalized.get("providers", {})
    if isinstance(providers, dict):
        codex_cfg = providers.get("codex", {})
        if isinstance(codex_cfg, dict):
            codex_cfg["use_session"] = bool(codex_cfg.get("use_session", True))
            codex_cfg["exec_mode"] = str(codex_cfg.get("exec_mode", "safe"))

        claude_cfg = providers.get("claude-minimax", {})
        if isinstance(claude_cfg, dict):
            claude_cfg["use_session"] = bool(claude_cfg.get("use_session", True))
            claude_cfg["permission_mode"] = str(
                claude_cfg.get("permission_mode", "bypassPermissions")
            )
            claude_cfg["include_partial_messages"] = bool(
                claude_cfg.get("include_partial_messages", False)
            )
            claude_cfg["print_stderr"] = bool(claude_cfg.get("print_stderr", False))

        gemini_cfg = providers.get("gemini", {})
        if isinstance(gemini_cfg, dict):
            gemini_cfg["use_session"] = bool(gemini_cfg.get("use_session", True))
            gemini_cfg["adapter"] = str(gemini_cfg.get("adapter", "gemini-cli"))
            gemini_cfg["auth_mode"] = str(gemini_cfg.get("auth_mode", "auto"))
            gemini_cfg["approval_mode"] = str(
                gemini_cfg.get("approval_mode", "default")
            )
            gemini_cfg["output_format"] = str(
                gemini_cfg.get("output_format", "stream-json")
            )
            gemini_cfg["yolo"] = bool(gemini_cfg.get("yolo", False))
            gemini_cfg["no_browser"] = bool(gemini_cfg.get("no_browser", False))
            gemini_cfg["proxy"] = str(gemini_cfg.get("proxy", "")).strip()
            gemini_cfg["no_proxy"] = str(gemini_cfg.get("no_proxy", "")).strip()
            gemini_cfg["proxy_args"] = bool(gemini_cfg.get("proxy_args", False))
            raw_include_dirs = gemini_cfg.get("include_directories", [])
            if isinstance(raw_include_dirs, str):
                raw_include_dirs = [raw_include_dirs]
            if isinstance(raw_include_dirs, (list, tuple, set)):
                gemini_cfg["include_directories"] = [
                    str(item).strip()
                    for item in raw_include_dirs
                    if str(item).strip()
                ]
            else:
                gemini_cfg["include_directories"] = []
            gemini_cfg["print_stderr"] = bool(gemini_cfg.get("print_stderr", False))
            gemini_cfg["mcp_callback_dir"] = str(
                gemini_cfg.get("mcp_callback_dir", ".gemini/mcp_bridge")
            )
            try:
                gemini_cfg["mcp_poll_interval_s"] = float(
                    gemini_cfg.get("mcp_poll_interval_s", 0.25)
                )
            except (TypeError, ValueError):
                gemini_cfg["mcp_poll_interval_s"] = 0.25
            try:
                gemini_cfg["mcp_timeout_s"] = float(
                    gemini_cfg.get("mcp_timeout_s", 300.0)
                )
            except (TypeError, ValueError):
                gemini_cfg["mcp_timeout_s"] = 300.0
            gemini_cfg["mcp_cleanup_response"] = bool(
                gemini_cfg.get("mcp_cleanup_response", True)
            )

    friends_bar = normalized.get("friends_bar", {})
    if isinstance(friends_bar, dict):
        friends_bar["default_rounds"] = int(friends_bar.get("default_rounds", 4))

        logging_cfg = friends_bar.get("logging", {})
        if not isinstance(logging_cfg, dict):
            logging_cfg = {}
        logging_cfg["enabled"] = bool(logging_cfg.get("enabled", True))
        logging_cfg["dir"] = str(logging_cfg.get("dir", ".friends-bar/logs"))
        logging_cfg["include_prompt_preview"] = bool(
            logging_cfg.get("include_prompt_preview", True)
        )
        try:
            logging_cfg["max_preview_chars"] = int(
                logging_cfg.get("max_preview_chars", 1200)
            )
        except (TypeError, ValueError):
            logging_cfg["max_preview_chars"] = 1200
        friends_bar["logging"] = logging_cfg

        history_cfg = friends_bar.get("history", {})
        if not isinstance(history_cfg, dict):
            history_cfg = {}
        try:
            history_cfg["max_chars"] = int(history_cfg.get("max_chars", 3000))
        except (TypeError, ValueError):
            history_cfg["max_chars"] = 3000
        try:
            history_cfg["field_max_chars"] = int(history_cfg.get("field_max_chars", 400))
        except (TypeError, ValueError):
            history_cfg["field_max_chars"] = 400
        try:
            history_cfg["evidence_limit"] = int(history_cfg.get("evidence_limit", 3))
        except (TypeError, ValueError):
            history_cfg["evidence_limit"] = 3
        try:
            history_cfg["issue_limit"] = int(history_cfg.get("issue_limit", 5))
        except (TypeError, ValueError):
            history_cfg["issue_limit"] = 5
        try:
            history_cfg["root_cause_limit"] = int(
                history_cfg.get("root_cause_limit", 3)
            )
        except (TypeError, ValueError):
            history_cfg["root_cause_limit"] = 3
        history_cfg["include_key_changes"] = bool(
            history_cfg.get("include_key_changes", True)
        )
        friends_bar["history"] = history_cfg

        safety_cfg = friends_bar.get("safety", {})
        if not isinstance(safety_cfg, dict):
            safety_cfg = {}
        safety_cfg["read_only"] = bool(safety_cfg.get("read_only", False))
        safety_cfg["allowed_roots"] = [
            str(item) for item in safety_cfg.get("allowed_roots", []) if item
        ]
        safety_cfg["command_allowlist"] = [
            str(item) for item in safety_cfg.get("command_allowlist", []) if item
        ]
        safety_cfg["command_denylist"] = [
            str(item) for item in safety_cfg.get("command_denylist", []) if item
        ]
        safety_cfg["codex_sandbox_read_only"] = str(
            safety_cfg.get("codex_sandbox_read_only", "read-only")
        )
        safety_cfg["codex_sandbox_default"] = str(
            safety_cfg.get("codex_sandbox_default", "workspace-write")
        )
        safety_cfg["claude_tools_read_only"] = str(
            safety_cfg.get("claude_tools_read_only", "Read")
        )
        friends_bar["safety"] = safety_cfg

        start_agent = str(friends_bar.get("start_agent", DUFFY))
        if normalize_agent_name is None:
            friends_bar["start_agent"] = start_agent
        else:
            try:
                friends_bar["start_agent"] = normalize_agent_name(start_agent)
            except ValueError as exc:
                _debug_log(f"normalize start_agent failed: {exc}")
                friends_bar["start_agent"] = DUFFY

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
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        _debug_log(f"load toml failed: path={config_file}, err={exc}")
        return {}


def _file_signature(path: Path) -> tuple[bool, int, int]:
    """Return (exists, mtime_ns, size) for cache invalidation."""
    try:
        stat = path.stat()
        return True, int(stat.st_mtime_ns), int(stat.st_size)
    except OSError:
        return False, 0, 0


def load_runtime_config(config_path: str = "config.toml") -> Dict[str, Any]:
    """Load runtime config with optional local override."""
    config_file = Path(config_path)
    local_file = config_file.with_name(f"{config_file.stem}.local{config_file.suffix}")
    cache_key = str(config_file.resolve())
    current_sig = (_file_signature(config_file), _file_signature(local_file))

    cache_entry = _CONFIG_CACHE.get(cache_key)
    if cache_entry and cache_entry.get("sig") == current_sig:
        return copy.deepcopy(cache_entry["config"])

    merged = copy.deepcopy(DEFAULT_CONFIG)
    merged = _deep_merge_dict(merged, _load_toml_dict(config_file))
    merged = _deep_merge_dict(merged, _load_toml_dict(local_file))
    normalized = _normalize_config(merged)
    _CONFIG_CACHE[cache_key] = {"sig": current_sig, "config": normalized}
    return copy.deepcopy(normalized)
