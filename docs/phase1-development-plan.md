# Friends Bar Phase1 开发计划（基于 `docs/target.md`）

## 1. 目标与结论

Phase1 的核心目标是把当前固定轮转协作升级为“可控路由协作”，最小可交付能力包括：

1. `@mention` 路由：支持在消息中显式指定下一跳 agent。
2. 深度限制与去重：避免循环转发和无穷链路。
3. 取消传播：用户中断后，整条执行链路可停止并可审计。

本计划以“先不破坏现有 schema/日志/执行链路”为原则，增量建设在 `orchestrator` 之上。

## 2. 范围定义

### 2.1 In Scope

1. 增加路由层（规则解析 + 下一跳决策）。
2. 增加链路上下文（hop_count、visited_agents、route_reason）。
3. 增加中断控制（SIGINT/主动取消）。
4. 增加路由与中断的审计事件。
5. 增加单元测试与最小回归脚本。

### 2.2 Out of Scope

1. Web/API 控制面。
2. 长期记忆与向量检索。
3. provider 故障切换（可在后续 Phase1.x/Phase2 做）。

## 3. 设计方案

### 3.1 路由模型

新增 `src/friends_bar/router.py`：

1. `parse_mentions(text) -> list[str]`：解析 `@linabell/@duffy/@stella`（含中文别名）。
2. `decide_next_agent(...) -> RouteDecision`：
   - 优先级 1：显式 mention。
   - 优先级 2：配置规则命中（关键字/当前角色/状态）。
   - 优先级 3：回退固定顺序（兼容现有行为）。
3. `RouteDecision` 字段：`next_agent`, `reason`, `matched_rule`, `is_fallback`。

### 3.2 深度限制与去重

在 `orchestrator` 每轮维护：

1. `hop_count`：当前链路步数。
2. `visited_agents`：短窗口访问历史（如最近 N 步）。
3. `route_fingerprint`：`(current_agent, next_agent, intent_hash)`。

阻断条件：

1. `hop_count > max_hops` 直接失败并记录 `E_ROUTE_MAX_HOPS_EXCEEDED`。
2. 指纹在窗口内重复命中超过阈值，触发 `E_ROUTE_LOOP_DETECTED`。

### 3.3 取消传播

在编排层增加 `cancel_token`：

1. 捕获 SIGINT/SIGTERM 后设置 `cancelled=true`。
2. 当前回合结束后不再调度下一轮。
3. 输出 `run.cancelled` 审计事件，携带 `turn/agent/reason`。

### 3.4 配置扩展（`config.toml`）

新增：

1. `[friends_bar.routing]`
   - `enabled = true`
   - `mode = "mention_first"`（`mention_first|rule_first|round_robin`）
   - `max_hops = 12`
   - `dedupe_window = 6`
2. `[[friends_bar.routing.rules]]`
   - `name`, `when_agent`, `when_contains`, `next_agent`, `priority`

## 4. 任务拆解

### M1. 路由内核（第 1 周）

1. 新建 `router.py` + mention 解析。
2. orchestrator 接入 `RouteDecision`。
3. 默认配置回退到现有轮转，保证兼容。

验收：

1. mention 生效且可审计。
2. 未命中规则时行为与当前版本一致。

### M2. 深度与去重（第 1-2 周）

1. 增加 hop/de-dupe 状态机。
2. 新增循环阻断错误码与日志事件。
3. 失败路径进入结构化 `run.failed`。

验收：

1. 构造循环路由时可在阈值内阻断。
2. 不影响正常 3-agent 链路。

### M3. 取消传播（第 2 周）

1. 增加 cancel token 与信号传播。
2. 统一中断后的返回结构（status=cancelled）。
3. CLI 输出中断摘要。

验收：

1. 手动 Ctrl+C 可稳定退出，无僵尸子进程。
2. 产生 `run.cancelled` 事件。

### M4. 测试与文档（第 2 周）

1. 新增 `tests/test_router.py`。
2. 补齐 `tests/test_orchestrator_*` 路由/取消分支。
3. 更新 `README.md`、`docs/phase0-friends-bar.md`、`docs/target.md` 的状态说明。

验收：

1. 新增测试通过，且全量测试通过。
2. 文档与代码行为一致。

## 5. 测试计划

1. 单测：
   - mention 解析（中文/英文别名、大小写、非法 mention）。
   - 规则优先级冲突与回退。
   - max_hops 与 loop-dedupe 阻断。
2. 集成：
   - dry-run 下的路由决策快照验证。
   - execute 模式下 3-agent 链路验证。
3. 中断：
   - SIGINT 后子进程清理与状态码验证。

## 6. 风险与缓解

1. 风险：路由规则过于灵活导致行为不可预测。  
   缓解：先限制规则表达能力（contains + when_agent），并要求审计输出 `route_reason`。
2. 风险：取消传播与 provider 流式读取竞争。  
   缓解：只在回合边界切断调度，并复用现有 `process_runner` 终止机制。
3. 风险：phase0 行为回归。  
   缓解：保留 `round_robin` 兼容模式作为默认回退。

## 7. 交付清单

1. `src/friends_bar/router.py`（新增）
2. `src/friends_bar/orchestrator.py`（路由与取消接入）
3. `src/utils/runtime_config.py`（routing 配置归一化）
4. `config.toml`（routing 配置示例）
5. `tests/test_router.py`（新增）
6. `tests/test_orchestrator_*.py`（扩展）
7. `README.md` 与 `docs/*`（同步更新）

## 8. Phase1 结束判定（DoD）

满足以下条件可判定 Phase1 完成：

1. `@mention` 路由、深度限制、去重、取消传播均可用。
2. 回归测试全部通过，且新增测试覆盖核心分支。
3. 审计日志可追踪每轮路由决策与中断原因。
4. 兼容模式下不破坏现有 round-robin 运行结果。
