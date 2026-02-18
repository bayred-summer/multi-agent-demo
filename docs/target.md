# Friends Bar 开发目标与周期记录

## 1. 项目目标（当前版本）

Friends Bar 当前目标是先完成双 Agent 协作闭环，聚焦可运行、可验证、可扩展：

1. 保留两个可用 provider：
   - `codex`（对外角色名：`玲娜贝儿`）
   - `claude-minimax`（对外角色名：`达菲`）
2. 通过统一入口 `invoke(cli, prompt)` 屏蔽 provider 差异。
3. 在编排层实现双 Agent 轮转协作（Phase0）。
4. 保留后续扩展到路由、记忆、回传的接口。

## 2. 已执行开发流程（本轮迭代）

### 2.1 命名与边界重构

1. 项目叙事从 `Cat Cafe` 调整为 `Friends Bar`。
2. 移除占位 provider `xxx`，避免误用和接口噪声。
3. 在统一调用层增加中文别名映射，支持按角色名调用。

### 2.2 核心能力落地

1. 新增 `src/friends_bar/agents.py`：
   - 维护角色与 provider 对应关系
   - 提供角色名标准化
2. 新增 `src/friends_bar/orchestrator.py`：
   - 负责双 Agent 轮转执行
   - 注入历史上下文并构建每轮提示词
   - 输出结构化 turn 记录
3. 新增 `friends-bar-demo.py`：
   - 提供 CLI 演示入口
   - 支持轮次、起始 Agent、超时档位参数

### 2.3 工程化对齐

1. 更新 `config.toml`：
   - 新增 `[friends_bar]` 配置段
   - 支持默认轮次与起始角色
2. 更新 `runtime_config` 默认配置，保证本地开箱可运行。
3. 更新 README 与 Phase0 设计文档，确保文档与代码一致。

### 2.4 提示词策略迭代

1. 去除编排层“兜底回复”机制，改为纯模型输出。
2. 将协作格式统一为“只标记消息接收方”：
   - 第一行：`发送给X：...`
   - 最后一行：`发送给X：...`
3. 禁止问好/寒暄/自我介绍，减少无效内容。
4. 历史问题提取逻辑兼容新旧格式，并优先取最后一行问题。

## 3. 当前阶段定义

当前阶段为 **Phase0（双 Agent 最小协作）**，验收标准：

1. 能以 `玲娜贝儿/达菲` 两个角色连续完成多轮对话。
2. 每轮输出能围绕用户任务推进，并对下一轮提出问题。
3. 子进程调用具备基础稳定性（超时、stderr 监听、错误上报）。

## 4. 后续开发周期（Roadmap v1）

### Phase1：路由控制（计划）

目标：从“固定轮转”升级到“按提及路由”。

1. 增加 `@mention` 路由规则。
2. 增加深度限制与去重逻辑。
3. 增加取消传播（用户中断可终止链路）。

### Phase2：记忆与回传（计划）

目标：让协作具备上下文连续性与主动发言能力。

1. 接入共享记忆层（短期记忆与摘要）。
2. 设计决策记录结构（What/Why/Tradeoff/Open Questions/Next Action）。
3. 引入 callback 通道，区分“内部推理输出”和“外部发言输出”。

### Phase3：产品化接口（计划）

目标：从脚本演示走向可交互系统。

1. 提供 Web/API 会话入口。
2. 统一消息模型、turn 模型与会话存储模型。
3. 增加可观测性（日志、调用链、失败原因）。

### Phase4：生产化（计划）

目标：可持续运行与安全运维。

1. 环境隔离（开发/生产配置与存储隔离）。
2. 错误恢复与重试策略分级。
3. 最小 E2E 回归测试与发布流程。

## 5. 当前文件基线（关键）

1. `src/invoke.py`
2. `src/friends_bar/agents.py`
3. `src/friends_bar/orchestrator.py`
4. `friends-bar-demo.py`
5. `config.toml`
6. `src/utils/runtime_config.py`
7. `docs/phase0-friends-bar.md`

以上文件构成 Friends Bar 当前迭代的可运行主干。
