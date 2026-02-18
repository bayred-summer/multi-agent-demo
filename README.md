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
|       |-- session_store.py
|       `-- process_runner.py
`-- .sessions/
```

## 环境要求

- Python 3.9+
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
invoke("claude_minimax", "你好")  # 别名，内部会归一化为 claude-minimax
```

返回结构：

```python
{
    "cli": "claude-minimax",
    "prompt": "你好",
    "text": "...",
    "session_id": "...",
    "elapsed_ms": 1234,
}
```

## 生产可用增强

### 1) 双通道活跃心跳

- 同时消费 `stdout` 和 `stderr`
- 任一通道有输出都会刷新活动时间，避免 thinking/tool 阶段误判超时

### 2) 任务级超时配置

- 内置级别：
  - `quick`: 60s 空闲 / 300s 总时长
  - `standard`: 300s 空闲 / 1800s 总时长
  - `complex`: 900s 空闲 / 3600s 总时长
- 支持按调用覆盖：
  - `idle_timeout_s`
  - `max_timeout_s`
  - `terminate_grace_s`

### 3) 超时后的优雅终止

- 先 `terminate()`
- 等待 `terminate_grace_s`
- 仍未退出则 `kill()`

### 4) 生命周期治理

- 注册 `SIGINT` / `SIGTERM` 处理
- 注册 `atexit` 清理
- 保证异常路径下也会 `wait()` 回收子进程，防止僵尸进程

### 5) 重试机制

- `invoke()` 支持 `retry_attempts`（默认 1）
- 对可重试故障自动指数退避重试（空闲超时、总超时、部分瞬时非零退出）

### 6) 结构化错误诊断

- 错误包含：`provider`、`reason`、`command`、`elapsed_ms`、`return_code`、`session_id`、`stderr_tail`
- 便于日志检索和生产排障

## 高级参数示例

```python
invoke(
    "claude-minimax",
    "请分析这个仓库的架构风险",
    use_session=True,
    stream=True,
    timeout_level="complex",
    idle_timeout_s=1200,
    max_timeout_s=3600,
    terminate_grace_s=8,
    retry_attempts=2,
    retry_backoff_s=1.5,
)
```

## Session 机制

- 文件：`.sessions/session-store.json`
- 按 provider key 存储
- 成功调用后更新 session_id
- 下次同 provider 自动续聊

重置上下文：删除 `.sessions/session-store.json`。

