# Friends Bar

这是一个基于 Python 的多 Agent CLI 协作原型项目，当前聚焦 **Phase0**：

- 统一调用入口：`invoke(cli, prompt)`
- 双 provider：`codex` 与 `claude-minimax`
- Friends Bar 角色命名：
  - `玲娜贝儿` -> `codex`
  - `达菲` -> `claude-minimax`
- 两个 Agent 的最小轮转协作（先跑通交互闭环）
- 面向生产的子进程治理（超时、优雅终止、重试、信号清理）

## 项目结构

```text
multi-agent/
|-- config.toml
|-- minimal-codex.py
|-- minimal-claude-minimax.py
|-- friends-bar-demo.py
|-- demo-invoke.py
|-- docs/
|   `-- phase0-friends-bar.md
`-- src/
    |-- invoke.py
    |-- protocol/
    |   |-- models.py
    |   |-- validators.py
    |   `-- errors.py
    |-- friends_bar/
    |   |-- agents.py
    |   `-- orchestrator.py
    |-- providers/
    |   |-- codex.py
    |   `-- claude_minimax.py
    `-- utils/
        |-- process_runner.py
        |-- runtime_config.py
        `-- session_store.py
```

## 环境要求

- Python 3.11+
- 已安装并登录 Codex CLI
- 已安装并配置 Claude CLI（MiniMax）

## 快速开始

```bash
python minimal-codex.py "你好，请用一句话介绍自己"
python minimal-claude-minimax.py "你好，请用一句话介绍自己"
```

运行 Phase0 双 Agent 协作演示：

```bash
python friends-bar-demo.py "请你们一起给出一个 ToDo App 的最小上线方案" --rounds 4
```

让 agent 直接在目标项目目录执行任务：

```bash
python friends-bar-demo.py "请直接开始实现并提交最小可运行版本" --rounds 2 --project-path E:\PythonProjects\test_project
```

## 统一接口

```python
from src.invoke import invoke

invoke("codex", "你好")
invoke("claude-minimax", "你好")

# Friends Bar 中文别名
invoke("玲娜贝儿", "你好")  # 等价于 codex
invoke("达菲", "你好")      # 等价于 claude-minimax
```

返回结构：

```python
{
    "cli": "codex",
    "prompt": "你好",
    "text": "...",
    "session_id": "...",
    "elapsed_ms": 1234,
    "timeout_level": "standard",
    "retry_count": 0,
}
```

## 配置文件（config.toml）

配置优先级：

1. `invoke()` 显式参数
2. `config.local.toml`
3. `config.toml`
4. 代码默认值

示例：

```toml
[defaults]
provider = "codex"
use_session = true
stream = true
timeout_level = "standard"
retry_attempts = 1
retry_backoff_s = 1.0

[providers.codex]
timeout_level = "standard"
retry_attempts = 1
exec_mode = "safe" # safe / full_auto / bypass

[providers.claude-minimax]
timeout_level = "standard"
retry_attempts = 1
permission_mode = "acceptEdits" # 由 provider 决定可用值

[friends_bar.logging]
enabled = true
dir = ".friends-bar/logs"
include_prompt_preview = true
max_preview_chars = 1200

[friends_bar]
name = "Friends Bar"
default_rounds = 4
start_agent = "linabell"

[friends_bar.agents."玲娜贝儿"]
provider = "codex"
response_mode = "execute" # execute / text_only

[friends_bar.agents."玲娜贝儿".provider_options]
exec_mode = "bypass"

[friends_bar.agents."达菲"]
provider = "claude-minimax"
response_mode = "execute"

[friends_bar.agents."达菲".provider_options]
permission_mode = "acceptEdits"
```

## Phase0 说明

- 设计文档：`docs/phase0-friends-bar.md`
- 目标：先跑通两个 Agent 的协作链路，为后续 A2A 路由、MCP 回传、共享记忆做准备

## 角色输出协议（JSON Schema Only）

Friends Bar 已切换为 **严格 JSON 输出**，不再接受自然语言区块协议，也不做自然语言兜底补丁。

- 玲娜贝儿输出：`friendsbar.delivery.v1`
- 达菲输出：`friendsbar.review.v1`
- 未来新角色：按同一模式新增 schema（`build_agent_output_schema()`）

运行时通过两层约束保证结构化输出：

1. Provider 约束
  - Codex：`codex exec --output-schema <schema.json>`
  - Claude CLI：`claude ... --json-schema '<schema>'`
2. Orchestrator 二次校验
  - `json.loads` 解析必须成功
  - `validate_json_protocol_content()` 语义校验必须通过
  - 失败即重试；超过重试次数直接报错终止

## 协议规范化设计（I/O v1）

为减少多-agent 协作中的“格式漂移、语义歧义、证据缺失”问题，当前实现采用 **结构化协议优先**：

1. 统一 Envelope（链路追踪）
2. Role Schema（角色输出结构）
3. 运行时强校验（失败即重试/终止）

### Core Envelope（全局统一）

每条消息在内部都映射到统一信封模型，核心字段包括：

- `message_id`
- `trace_id`
- `schema_version`（`friendsbar.envelope.v1`）
- `sender` / `recipient`
- `role`（`task|review|final|error|observation`）
- `timestamp`
- `content`
- `attachments`
- `meta`

### Role Schema（按角色）

- `friendsbar.task.v1`：orchestrator 发给 agent 的任务消息
- `friendsbar.delivery.v1`：玲娜贝儿交付消息（任务理解/实施/证据/风险/问题）
- `friendsbar.review.v1`：达菲评审消息（验收/核验/问题/门禁/下一问）

### 运行时校验

`src/protocol/validators.py` 在每轮输出上执行：

1. Envelope 基础字段与枚举校验
2. Role Schema 必填项校验
3. 达菲证据门禁校验（至少 2 条 `命令 + 结果`）
4. 语义一致性校验（如高优问题与放行结论冲突）

校验结果会写入审计日志；失败时只允许“同 schema 下重试”，不会做自然语言自动修补。

### 错误码（稳定）

- `E_SCHEMA_MISSING_FIELD`
- `E_SCHEMA_INVALID_ENUM`
- `E_SCHEMA_INVALID_FORMAT`
- `E_REVIEW_EVIDENCE_MISSING`
- `E_REVIEW_GATE_INCONSISTENT`
- `E_PROTOCOL_RETRY_EXCEEDED`

## 日志与排障

每次 `friends-bar-demo.py` 运行都会写审计日志（默认开启）：

- 目录：`.friends-bar/logs/`
- 文件：
  - `<run_id>.jsonl`：事件流（run/turn/attempt）
  - `<run_id>.summary.json`：本次运行汇总

日志会记录：

1. 用户输入任务（全文）
2. 每个子 agent 的原始回答与最终回答（全文）
3. 协议校验错误、重试次数、超时档位、耗时、会话 ID
4. 失败异常类型与 traceback（若有）

本次 JSON Schema 迁移的详细踩坑复盘见：

- `docs/json-schema-migration-postmortem-2026-02-19.md`

## Protocol IDs (Stable)

To avoid terminal/codepage issues, internal agent IDs are ASCII-only:

- `linabell` (display name: 玲娜贝儿)
- `duffy` (display name: 达菲)

You can still call `invoke()` and Friends Bar with provider names or Chinese names. They are normalized to canonical IDs.

## 达菲职责（Code Review）

达菲当前定位为资深 Code Reviewer（兼 QA 测试负责人），不是实现角色。

- 核心目标：发现会导致功能错误、回归、安全或稳定性风险的问题
- 输出要求：所有结论必须有证据（命令输出、日志、测试结果、文件定位）
- 阻塞规则：P0/P1 问题未关闭时，结论必须为“不通过”或“有条件合入”
- 建议要求：每条建议都要可执行，包含修复方向和回归验证方法
- 非阻塞项：纯样式/偏好类建议不得作为阻塞理由
