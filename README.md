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

[providers.claude-minimax]
timeout_level = "standard"
retry_attempts = 1

[friends_bar]
name = "Friends Bar"
default_rounds = 4
start_agent = "玲娜贝儿"

[friends_bar.agents."玲娜贝儿"]
provider = "codex"

[friends_bar.agents."达菲"]
provider = "claude-minimax"
```

## Phase0 说明

- 设计文档：`docs/phase0-friends-bar.md`
- 目标：先跑通两个 Agent 的协作链路，为后续 A2A 路由、MCP 回传、共享记忆做准备
