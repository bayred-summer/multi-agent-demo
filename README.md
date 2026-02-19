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
permission_mode = "default" # default / plan / dontAsk / bypassPermissions

[friends_bar]
name = "Friends Bar"
default_rounds = 4
start_agent = "玲娜贝儿"

[friends_bar.agents."玲娜贝儿"]
provider = "codex"
response_mode = "execute" # execute / text_only

[friends_bar.agents."玲娜贝儿".provider_options]
exec_mode = "bypass"

[friends_bar.agents."达菲"]
provider = "claude-minimax"
response_mode = "text_only"

[friends_bar.agents."达菲".provider_options]
permission_mode = "plan"
```

## Phase0 说明

- 设计文档：`docs/phase0-friends-bar.md`
- 目标：先跑通两个 Agent 的协作链路，为后续 A2A 路由、MCP 回传、共享记忆做准备

## 角色输出协议（Friends Bar）

为保证玲娜贝儿与达菲可以稳定互调，当前回合输出采用固定区块协议。

- 玲娜贝儿（开发实现 + 发布运维）必须输出区块：
  - `[接收方]`
  - `[任务理解]`
  - `[实施清单]`
  - `[执行证据]`
  - `[风险与回滚]`
  - `[给达菲的问题]`
- 达菲（QA测试负责人 + 评审官）必须输出区块：
  - `[接收方]`
  - `[验收结论]`
  - `[核验清单]`
  - `[根因链]`
  - `[问题清单]`
  - `[回归门禁]`
  - `[给玲娜贝儿的问题]`

公共约束：

- 第一行必须是：`发送给<对方>：路由确认`
- 最后一行必须是：`发送给<对方>：<一个明确问题>`
- 无证据结论一律标注为“未验证”
- 禁止寒暄、禁止自我介绍、禁止元请求（例如“请授权”“请提供文件列表”）

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
