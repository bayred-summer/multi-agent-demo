# Friends Bar 整合开发计划（对齐 Phase0 + Target + OpenClaw Gap）

## 1. 文档整合范围

本计划整合以下三份文档，并以当前仓库代码为基线做对比：

1. `docs/target.md`
2. `docs/phase0-friends-bar.md`
3. `docs/openclaw-gap-plan.md`

目标是把“愿景、现状、差距、下一步任务”放在一处，避免重复维护。

## 0. 最近改进（已落地）

1. 运行标识贯穿：`run_id/seed` 进入每条审计日志与最终输出。
2. 调试能力：支持 `--dry-run` 与 `--dump-prompt`，可在不调用 CLI 时生成 prompt/schema。
3. 安全护栏：新增 `friends_bar.safety`（只读模式、工作目录白名单、命令 allow/deny）。

## 2. 统一目标（整合后）

### 2.1 当前阶段目标（Phase0）

1. 双 Agent（玲娜贝儿 / 达菲）协作闭环可持续运行。
2. 统一调用入口 `invoke(cli, prompt)` 屏蔽 provider 差异。
3. 协作输出协议稳定、可校验、可追责。
4. 子进程调用具备最小生产稳定性（超时、重试、清理、证据化）。

### 2.2 下一阶段目标（对标 OpenClaw 核心）

1. 增加最小控制面（统一事件模型、可观测性）。
2. 增强状态治理（会话分层、路由配置化、审计日志）。
3. 提升容错与安全（故障切换、工具白名单、风险阻断）。

## 3. 当前项目对比（代码基线 vs 目标）

### 3.1 已完成（与三份文档一致）

1. 双 provider 可用：`codex`、`claude-minimax`  
   代码：`src/invoke.py`, `src/providers/codex.py`, `src/providers/claude_minimax.py`
2. 双 Agent 编排可运行（轮转、历史注入、结果转录）  
   代码：`src/friends_bar/orchestrator.py`, `friends-bar-demo.py`
3. 配置驱动运行时参数（providers/friends_bar/timeouts）  
   代码：`config.toml`, `src/utils/runtime_config.py`
4. 子进程稳定性基础能力  
   代码：`src/utils/process_runner.py`
   已有：空闲超时、总超时、优雅终止、父进程退出清理、异常上报
5. 达菲评审证据门禁（无命令证据会失败重试）  
   代码：`src/friends_bar/orchestrator.py`, `tests/test_protocol_contract.py`
6. 配置与会话基础稳态优化  
   代码：`src/utils/runtime_config.py`（mtime 缓存），`src/utils/session_store.py`（原子写盘）

### 3.2 部分完成（需补齐）

1. 重试策略：已支持超时/可重试错误，但尚未区分“幂等/非幂等”动作。  
   代码：`src/invoke.py`
2. 协议稳定性：已显著改善，但在极端场景仍可能触发 `[protocol_adapted]` 兜底。  
   代码：`src/friends_bar/orchestrator.py`
3. 会话管理：已有按 provider 的 session 持久化，但未做 `scope` 分层（主会话/按 agent/按项目）。  
   代码：`src/utils/session_store.py`

### 3.3 未开始（OpenClaw Gap 中的核心缺口）

1. 最小事件总线（`turn.started/turn.completed/turn.failed`）  
2. 路由配置化（规则驱动起始 agent / 下一跳）  
3. 工具级安全策略（allow/deny + 命中阻断）  
4. `doctor` 诊断命令（环境、配置、provider 健康检查）  
5. provider 故障切换（profile 轮换 / fallback）  
6. 审计日志持久化（命令证据、结论、回放能力）  

## 4. 开发计划（任务-文件-验收标准）

## Phase A（本周，稳定性优先）

### A1. 事件总线最小落地（FB-OC-001）

- 任务：新增统一 turn 事件模型，脱离“只看 stdout 文本”的状态观察方式。
- 文件：
  - `src/friends_bar/events.py`（新建）
  - `src/friends_bar/orchestrator.py`
  - `friends-bar-demo.py`
- 验收标准：
  1. 每轮至少产出 `turn.started/turn.completed/turn.failed`。
  2. CLI 支持 `--show-events` 输出事件摘要。
  3. 新增单测并通过。

### A2. 会话分层（FB-OC-002）

- 任务：将 session-store 从“按 provider”升级为“按 scope+provider”。
- 文件：
  - `src/utils/session_store.py`
  - `src/invoke.py`
  - `src/friends_bar/orchestrator.py`
  - `config.toml`
- 验收标准：
  1. 支持 scope：`global / agent / project`。
  2. 老格式自动兼容读取，不破坏已有数据。
  3. 新增迁移与回归测试通过。

### A3. 协议兜底压降（增强）

- 任务：把 `[protocol_adapted]` 触发率继续压低到可接受范围。
- 文件：
  - `src/friends_bar/orchestrator.py`
  - `tests/test_protocol_contract.py`
- 验收标准：
  1. 连续 10 次固定脚本回归，`protocol_adapted` 触发率 < 10%。
  2. 达菲每次都包含“命令+结果”证据。

## Phase B（下周，控制面与安全）

### B1. 路由规则配置化（FB-OC-003）

- 任务：从固定轮转扩展到“规则驱动起始/下一跳”。
- 文件：
  - `src/friends_bar/router.py`（新建）
  - `src/friends_bar/orchestrator.py`
  - `src/utils/runtime_config.py`
  - `config.toml`
- 验收标准：
  1. 支持规则字段：任务关键字、project_path、显式 agent 指定。
  2. 不命中规则时保持现有轮转行为。
  3. 路由单测覆盖命中、冲突、回退。

### B2. 安全最小集（FB-OC-005）

- 任务：按 agent 定义工具 allow/deny，阻断危险命令。
- 文件：
  - `src/friends_bar/safety.py`（新建）
  - `src/providers/codex.py`
  - `src/providers/claude_minimax.py`
  - `config.toml`
- 验收标准：
  1. 命中 deny 列表时返回结构化错误。
  2. 不影响默认可运行流程。
  3. 有对应单测。

### B3. `doctor` 命令（FB-OC-006）

- 任务：提供“环境与配置健康检查”脚本。
- 文件：
  - `scripts/doctor.py`（新建）
  - `README.md`
- 验收标准：
  1. 检查 Python 版本、CLI 可执行、配置解析、session-store 读写。
  2. 失败项返回非零退出码。
  3. README 提供示例命令。

## Phase C（2-4 周，容错与可观测）

### C1. Provider 故障切换（FB-OC-007）

- 任务：主 provider 失败时自动按配置切换 profile/fallback。
- 文件：
  - `src/invoke.py`
  - `src/utils/runtime_config.py`
  - `config.toml`
  - `tests/test_invoke_fallback.py`（新建）
- 验收标准：
  1. 支持主失败 -> 备选成功路径。
  2. 输出切换链路日志。
  3. 回归测试覆盖全失败与降级分支。

### C2. 幂等重试分层（FB-OC-008）

- 任务：把“可重试错误”与“可重试动作”分层治理。
- 文件：
  - `src/invoke.py`
  - `src/utils/process_runner.py`
  - `tests/test_process_runner.py`
- 验收标准：
  1. 仅对幂等动作自动重试。
  2. 重试日志含 reason、attempt、backoff。
  3. 与现有超时策略兼容。

### C3. 审计日志（FB-OC-011）

- 任务：持久化关键执行证据，支持问题回放。
- 文件：
  - `src/utils/audit_log.py`（新建）
  - `src/friends_bar/orchestrator.py`
  - `config.toml`
- 验收标准：
  1. 每轮写入输入摘要、命令证据、结论、耗时。
  2. 可按 session 查询。
  3. 可配置关闭。

## 5. 本阶段建议执行顺序

1. `A1` 事件总线
2. `A2` 会话分层
3. `A3` 协议兜底压降
4. `B1` 路由配置化
5. `B2` 安全最小集
6. `B3` doctor

这样能先把“可观测 + 状态正确性”打稳，再做路由和安全，不会破坏当前可运行主链路。

## 6. 验收口径（统一）

每个任务完成都要满足：

1. 代码 + 配置 + 文档同时更新。
2. 至少 1 条命令级验证证据。
3. `pytest` 全绿。
4. 不回退现有双 Agent 演示能力（`friends-bar-demo.py` 可正常运行）。
