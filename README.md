# multi-agent-demo

这是一个基于 Python 的 CLI 多模型调用示例，核心能力：

- 统一调用入口：`invoke(cli, prompt)`
- 支持 `codex` 与 `claude-minimax`
- 流式 JSON 解析
- 本地 session 持久化与自动续聊
- 面向生产的子进程治理（超时、优雅终止、重试、信号清理）

## 项目结构

```text
multi-agent-demo/
|-- config.toml
|-- minimal-codex.py
|-- minimal-claude-minimax.py
|-- demo-invoke.py
|-- src/
|   |-- invoke.py
|   |-- providers/
|   |   |-- codex.py
|   |   |-- claude_minimax.py
|   |   `-- xxx.py
|   `-- utils/
|       |-- process_runner.py
|       |-- runtime_config.py
|       `-- session_store.py
`-- .sessions/
```

## 环境要求

- Python 3.11+（`runtime_config.py` 使用内置 `tomllib` 读取 TOML）
- 已安装并登录 Codex CLI
- 已安装并配置 Claude CLI（MiniMax Coding Plan）

## 快速开始

```bash
python minimal-codex.py "你好，请用一句话介绍自己"
python minimal-claude-minimax.py "你好，请用一句话介绍自己"
python demo-invoke.py
```

## 统一接口

```python
from src.invoke import invoke

invoke("codex", "你好")
invoke("claude-minimax", "你好")
invoke("claude_minimax", "你好")  # 别名，内部归一为 claude-minimax
```

返回结构：

```python
{
    "cli": "claude-minimax",
    "prompt": "你好",
    "text": "...",
    "session_id": "...",
    "elapsed_ms": 1234,
    "timeout_level": "standard",
    "retry_count": 0,
}
```

## 配置文件（config.toml）

项目根目录下的 `config.toml` 用于管理生产参数。  
你也可以创建 `config.local.toml` 做本机覆盖（已加入 `.gitignore`）。

优先级：

1. 调用 `invoke()` 时显式传入的参数
2. `config.local.toml`
3. `config.toml`
4. 代码内置默认值

### 示例配置

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
timeout_level = "complex"
retry_attempts = 2

[timeouts.quick]
idle_timeout_s = 60
max_timeout_s = 300
terminate_grace_s = 3

[timeouts.standard]
idle_timeout_s = 300
max_timeout_s = 1800
terminate_grace_s = 5

[timeouts.complex]
idle_timeout_s = 900
max_timeout_s = 3600
terminate_grace_s = 8
```

## 为什么选 TOML（而不是 YAML/.env）

1. 对 Python 友好：`tomllib` 是 Python 内置库（3.11+），不需要额外依赖。  
2. 可读性好：层级清晰，适合表达 `defaults/providers/timeouts` 这类结构化配置。  
3. 类型更明确：数字、布尔值、字符串天然有类型，避免 `.env` 全是字符串导致转换问题。  
4. 维护成本低：比 YAML 语法更收敛，减少缩进和语法陷阱。  
5. 适合版本管理：`config.toml` 可提交；`config.local.toml` 可本地覆盖，不污染团队基线。

## 生产能力摘要

1. 双通道活跃心跳：同时监听 stdout/stderr。  
2. 任务级超时：`quick/standard/complex` + 显式覆盖。  
3. 超时优雅终止：`terminate()` -> 等待 -> `kill()`。  
4. 生命周期治理：SIGINT/SIGTERM、atexit、异常回收。  
5. 重试机制：对可重试错误做指数退避。  
6. 结构化错误：包含 reason、command、elapsed_ms、stderr_tail 等。

## Session 机制

- 文件：`.sessions/session-store.json`
- 按 provider key 保存 session_id
- 成功调用后自动更新
- 下一次同 provider 自动续聊

重置上下文：删除 `.sessions/session-store.json`。

