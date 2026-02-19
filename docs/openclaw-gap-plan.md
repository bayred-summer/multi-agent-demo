# Friends Bar 对标 OpenClaw 差距落地计划（Backlog）

## 1. 目的与范围

本计划用于在当前 Friends Bar 阶段（双 Agent CLI 协作）基础上，吸收 OpenClaw 的核心思路并拆成可执行任务。

边界说明：

1. 不追求一次性实现 OpenClaw 全量能力。
2. 仅落地当前阶段可控、低风险、可验证的增量。
3. 本文聚焦工程任务，不替代产品需求文档。

## 2. 里程碑优先级

1. `P0`：稳定性与可验证性，优先落地。
2. `P1`：控制面与容错能力，随后落地。
3. `P2`：扩展性与产品化能力，按资源推进。

## 3. 可执行 Backlog（任务-文件-验收标准）

### P0（建议 1-2 周）

| ID | 任务 | 目标文件 | 验收标准 |
|---|---|---|---|
| FB-OC-001 | 建立最小事件总线（Gateway-lite），统一 turn 事件结构 | `src/friends_bar/events.py`（新建）, `src/friends_bar/orchestrator.py`, `friends-bar-demo.py` | 1) 每轮产生结构化事件（`turn.started/turn.completed/turn.failed`）。2) CLI 输出可选显示事件摘要。3) `pytest` 新增事件结构测试并通过。 |
| FB-OC-002 | 会话键分层（主会话/按 agent/按项目） | `src/utils/session_store.py`, `src/invoke.py`, `src/friends_bar/orchestrator.py`, `config.toml` | 1) `session-store.json` 支持 `scope` 维度。2) 旧格式可兼容读取。3) 提供迁移逻辑与回归测试。 |
| FB-OC-003 | 路由规则配置化（任务类型/目录/显式指定） | `src/friends_bar/router.py`（新建）, `src/friends_bar/orchestrator.py`, `src/utils/runtime_config.py`, `config.toml` | 1) 支持按规则决定起始 agent 或下一跳。2) 默认规则不改变现有行为。3) 新增路由单测覆盖命中与回退。 |
| FB-OC-004 | 评审证据门禁固化（无证据即失败） | `src/friends_bar/orchestrator.py`, `tests/test_protocol_contract.py` | 1) 达菲输出必须含至少 2 条“命令+结果”。2) 出现“未实际读取/基于声明”直接失败并重试。3) 回归测试覆盖通过与失败样例。 |
| FB-OC-005 | 安全最小集：按 agent 工具白名单和危险命令阻断 | `src/providers/codex.py`, `src/providers/claude_minimax.py`, `src/friends_bar/safety.py`（新建）, `config.toml` | 1) 可在配置中定义 allow/deny。2) 命中 deny 时返回结构化错误。3) 不影响默认可运行链路。 |
| FB-OC-006 | `doctor` 诊断命令（环境、配置、provider 可用性） | `scripts/doctor.py`（新建）, `README.md` | 1) 输出配置有效性、CLI 可执行性、会话存储健康状态。2) 失败项返回非零退出码。3) README 增加使用说明。 |

### P1（建议 2-4 周）

| ID | 任务 | 目标文件 | 验收标准 |
|---|---|---|---|
| FB-OC-007 | Provider 故障切换（profile 轮换 + model fallback） | `src/invoke.py`, `src/utils/runtime_config.py`, `config.toml`, `tests/test_invoke_fallback.py`（新建） | 1) 主 provider 失败时按配置切换。2) 错误与切换路径可观测。3) 单测覆盖主失败/备成功/全失败。 |
| FB-OC-008 | 幂等与重试策略分层（只重试可重试错误） | `src/invoke.py`, `src/utils/process_runner.py`, `tests/test_process_runner.py` | 1) 对超时/网络类错误重试。2) 对非幂等操作默认不自动重试。3) 日志显示重试原因与次数。 |
| FB-OC-009 | 流式输出分块与合并（chunk + coalesce） | `src/utils/streaming.py`（新建）, `src/providers/codex.py`, `src/providers/claude_minimax.py`, `friends-bar-demo.py` | 1) 长输出可控分块。2) 避免重复刷屏。3) 对现有 JSONL 解析无回归。 |
| FB-OC-010 | 引入 Skills 目录优先级（workspace > user > bundled） | `src/skills/loader.py`（新建）, `src/friends_bar/orchestrator.py`, `README.md` | 1) 能从三个层级发现技能。2) 同名覆盖按优先级生效。3) 输出当前命中来源用于排障。 |
| FB-OC-011 | 审计日志与执行证据持久化 | `src/utils/audit_log.py`（新建）, `src/friends_bar/orchestrator.py`, `config.toml` | 1) 每轮记录输入摘要、命令证据、结论。2) 支持按会话检索。3) 默认可关闭以控制开销。 |

### P2（按资源推进）

| ID | 任务 | 目标文件 | 验收标准 |
|---|---|---|---|
| FB-OC-012 | Web 控制面最小版（会话列表 + 轮次详情） | `src/web/app.py`（新建）, `src/utils/audit_log.py`, `README.md` | 1) 可查看会话和轮次详情。2) 不影响 CLI 主流程。3) 基础鉴权可用。 |
| FB-OC-013 | 远程接入安全基线（token + 本地绑定 + 可选隧道） | `src/web/security.py`（新建）, `config.toml`, `README.md` | 1) 默认仅本机访问。2) token 缺失时拒绝外部调用。3) 安全配置可审计。 |
| FB-OC-014 | 多 Agent 图路由（从固定双 Agent 升级） | `src/friends_bar/graph_router.py`（新建）, `src/friends_bar/orchestrator.py`, `tests/test_graph_router.py`（新建） | 1) 支持节点与边配置。2) 支持深度限制与环路保护。3) 兼容现有双 Agent 配置。 |

## 4. 建议实施顺序（最小风险）

1. 第一批：`FB-OC-004` -> `FB-OC-001` -> `FB-OC-002`
2. 第二批：`FB-OC-003` -> `FB-OC-006` -> `FB-OC-005`
3. 第三批：`FB-OC-007` -> `FB-OC-008` -> `FB-OC-009`

## 5. 每个任务的统一完成定义（DoD）

1. 代码实现完成且通过本地 `pytest`。
2. README 或 docs 至少补 1 条使用说明。
3. 新增配置项有默认值且兼容旧配置。
4. 输出至少 1 条命令级验证证据。

## 6. 当前建议的“立即开工”任务

1. `FB-OC-001`（事件总线）  
2. `FB-OC-002`（会话键分层）  
3. `FB-OC-003`（路由配置化）

这三项完成后，Friends Bar 的控制面、状态管理与可扩展性会明显提升，且不会破坏当前双 Agent 可运行链路。
