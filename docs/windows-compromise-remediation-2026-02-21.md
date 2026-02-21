# Windows 妥协点清理补丁（2026-02-21）

## 背景

为统一在 WSL/Linux 下的行为、降低平台分支复杂度，本次对仓库内历史 Windows 妥协逻辑做集中清理，并补齐回归测试。

## 补丁清单（已完成）

1. 路径白名单判定从字符串前缀改为路径分段比较，修复 `root`/`root_evil` 误判风险。  
   文件：`src/friends_bar/orchestrator.py`，`tests/test_orchestrator_audit_logging.py`
2. 清理 `allowed_roots` 报错中的乱码文案，改为稳定英文错误信息。  
   文件：`src/friends_bar/orchestrator.py`
3. 移除 Claude provider 的 Windows `APPDATA`/`.cmd` 特判，统一为 `CLAUDE_BIN` 或 PATH。  
   文件：`src/providers/claude_minimax.py`，`tests/test_provider_parsing.py`
4. 移除 Codex provider 的 VSCode Windows 内置路径扫描，统一为 `CODEX_BIN` 或 PATH。  
   文件：`src/providers/codex.py`，`tests/test_provider_parsing.py`
5. 移除 Gemini provider 的 Windows `APPDATA`/`.cmd` 特判，统一为 `GEMINI_BIN` 或 PATH。  
   文件：`src/providers/gemini.py`，`tests/test_provider_parsing.py`
6. Gemini `prompt_via_stdin` 自动策略改为跨平台按 prompt 大小触发，不再限定 Windows。  
   文件：`src/providers/gemini.py`，`tests/test_gemini_adapter.py`
7. 配置加载不再依赖 `utf-8-sig` 编码名，改为 `utf-8 + BOM strip`。  
   文件：`src/utils/runtime_config.py`，`tests/test_runtime_config_cache.py`
8. 移除 agent 名称中的历史 mojibake 别名映射。  
   文件：`src/friends_bar/agents.py`
9. 文档与测试中的 Windows/PowerShell 示例统一为 Linux/bash 示例。  
   文件：`README.md`，`docs/json-schema-migration-postmortem-2026-02-19.md`，`tests/test_orchestrator_audit_logging.py`，`tests/test_protocol_contract.py`，`tests/test_invoke_provider_defaults.py`，`tests/test_gemini_adapter.py`
10. 控制台与日志注释去 Windows 定向措辞，改为通用编码表述。  
    文件：`src/friends_bar/orchestrator.py`，`src/utils/process_runner.py`
11. 强制三 Agent 统一工作目录闭环：禁止回退到当前仓库目录；仅允许 `--project-path` 或用户请求中的绝对路径作为工作目录来源。  
    文件：`src/friends_bar/orchestrator.py`，`tests/test_orchestrator_audit_logging.py`
12. 对 Delivery/Review 证据命令增加工作目录越界校验，拦截绝对路径指向工作目录外部的命令。  
    文件：`src/friends_bar/orchestrator.py`，`tests/test_orchestrator_audit_logging.py`

## 验证项

1. 新增路径边界回归：`tests/test_orchestrator_audit_logging.py`
2. 新增 provider 命令解析回归：`tests/test_provider_parsing.py`
3. 新增 Gemini 大 prompt 自动 stdin 回归：`tests/test_gemini_adapter.py`
4. 新增 TOML BOM 回归：`tests/test_runtime_config_cache.py`
5. 新增工作目录显式指定回归：`tests/test_orchestrator_audit_logging.py::test_run_requires_explicit_or_inferred_workdir`
6. 新增命令越界校验回归：`tests/test_orchestrator_audit_logging.py::test_command_workdir_guard_detects_outside_paths`

## 兼容性说明

1. 本次有意移除了对旧乱码 agent 别名和 Windows 本地路径探测的隐式兼容。
2. 若需要保留个别机器差异，可通过 `CLAUDE_BIN`/`CODEX_BIN`/`GEMINI_BIN` 显式指定二进制路径。
