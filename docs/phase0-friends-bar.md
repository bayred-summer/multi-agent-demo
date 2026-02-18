# Friends Bar Phase0 设计与落地

## 1. Phase0 目标

在不引入 Web 前端的前提下，先跑通最小“多 Agent 协作”闭环：

1. 统一调用层只保留两个可用 provider：`codex` 与 `claude-minimax`
2. 对外角色命名统一为：
   - `玲娜贝儿` -> `codex`
   - `达菲` -> `claude-minimax`
3. 支持两个 Agent 轮转协作（最少 1 轮，可配置多轮）
4. 为后续 Phase1/2 的路由、记忆、回传机制保留结构化扩展点

## 2. 当前目录增量

```text
src/
`-- friends_bar/
    |-- __init__.py
    |-- agents.py
    `-- orchestrator.py
friends-bar-demo.py
docs/phase0-friends-bar.md
```

## 3. 模块职责

### 3.1 `src/friends_bar/agents.py`

- 定义 Agent 配置结构 `AgentProfile`
- 维护 Friends Bar 的标准角色映射
- 提供 `normalize_agent_name()`，兼容中文名与 provider 别名输入

### 3.2 `src/friends_bar/orchestrator.py`

- Phase0 编排核心：`run_two_agent_dialogue()`
- 负责轮转顺序、历史注入、单轮提示词构建
- 把每轮调用结果记录为结构化转录（turn/agent/provider/text/elapsed）

### 3.3 `friends-bar-demo.py`

- 终端演示入口
- 支持 `--rounds`、`--start-agent`、`--use-session`、`--timeout-level`

## 4. 事件/状态模型（Phase0 简化版）

### 4.1 Turn 记录结构

```python
{
  "turn": 1,
  "agent": "玲娜贝儿",
  "provider": "codex",
  "text": "...",
  "session_id": "...",
  "elapsed_ms": 1234
}
```

### 4.2 协作状态机

1. `INIT`：校验输入参数与起始 Agent
2. `RUNNING`：按轮次调用当前 Agent，写入转录
3. `SWITCHING`：切换到另一个 Agent
4. `COMPLETED`：达到轮次上限并返回结果
5. `FAILED`：任意一轮抛异常，终止并返回错误

## 5. 配置策略

`config.toml` 新增 `friends_bar` 区域：

- `default_rounds`
- `start_agent`
- `friends_bar.agents.*.provider`

Phase0 仅使用其中基础字段，后续可扩展：

- 每个 Agent 的独立超时策略
- 每个 Agent 的系统提示模板
- 每个 Agent 的成本与配额限制

## 6. 下一阶段接口预留

为 Phase1 预留的明确扩展点：

1. 在 `orchestrator.py` 中插入路由器（A2A mention）
2. 在每轮前后挂接记忆层读写
3. 将输出通道从 CLI stdout 切到 callback/post_message
4. 从“固定双 Agent”扩展到“多 Agent 图路由”
