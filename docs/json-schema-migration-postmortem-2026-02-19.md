# Friends Bar JSON Schema 迁移踩坑复盘（2026-02-19）

## 1. 背景与目标

本次改造目标是把 Friends Bar 从“自然语言协议 + 兜底修补”切到“JSON Schema Only”：

1. 玲娜贝儿与达菲都只输出单个 JSON 对象。
2. provider 层先做 schema 约束，orchestrator 层再做二次校验。
3. 失败只允许重试，不再做自然语言补丁（`[protocol_adapted]`）。

## 2. 关键时间线（北京时间，UTC+8）

### 2026-02-20 03:32 左右：Codex `--output-schema` 首次失败

现象：

- 手动调用 `codex exec --output-schema` 报错：
  - `Invalid schema ... schema must have a 'type' key`

根因：

- 我们生成的 schema 使用了 `const/enum`，但部分类字段没显式 `type`。
- Codex 的 schema 校验更严格，要求对象字段完整声明类型。

修复：

- 修改 `src/protocol/validators.py` 的 `build_agent_output_schema()`：
  - 为 `schema_version/status/acceptance/...` 补齐 `type`。
  - 补齐 `warnings/errors` 的 `items`。
  - 强制 `additionalProperties: false`。

---

### 2026-02-20 03:35 ~ 03:50：达菲多次重试，最终失败

对应日志：

- `.friends-bar/logs/20260219T193511704594Z_0022ce4a3aef4815a92df462aad84652.jsonl`

现象 1：

- `E_SCHEMA_INVALID_FORMAT: output is not valid JSON (Extra data)`
- 达菲一次输出里出现两个拼接 JSON 对象：`{...}{...}`

根因 1：

- Claude 流里同时出现 delta / assistant / result 文本。
- 旧解析器把多个来源拼接，导致重复对象。
- 配置里 `include_partial_messages = true` 放大了这个问题。

修复 1：

- `src/providers/claude_minimax.py`：
  - 新增 `_collapse_repeated_json_objects()` 去重拼接对象。
  - 新增 `_pick_final_text()`，优先选择“单个可解析 JSON 对象”。
  - 调整为“delta 主要用于流式打印，最终返回优先用 assistant/result 文本”。
- `config.toml`：
  - 将达菲 `include_partial_messages` 默认改为 `false`。

现象 2：

- 同一轮重试后又出现：
  - `E_SCHEMA_INVALID_FORMAT: output is not valid JSON (Expecting value)`
- 原因是返回内容前后混入自然语言（例如“现在让我验证...”）。

修复 2：

- `src/friends_bar/orchestrator.py`：
  - 强制 `json.loads` 单对象校验。
  - 失败时仅注入 schema 重试提示，不做文本修补。
  - 清理旧文本协议兜底链路（`protocol_adapted` 相关）。

---

### 2026-02-20 03:49：联调成功但暴露“静默吞错”

对应日志：

- `.friends-bar/logs/20260219T194315359403Z_6414376e30934b6b90711a48ecda5fa7.jsonl`

现象：

- 达菲返回 JSON 看似通过，但 `verification` 第一项键名被污染：
  - 例：`"m pytest tests/testcommand": "python -_protocol_json.py -v"`
- 解析器把坏条目静默丢弃，仍然放行。

根因：

- `validate_json_protocol_content()` 对 `verification` / `execution_evidence` 条目“只收集正确项”，没有把坏项直接判错。

修复：

- `src/protocol/validators.py`：
  - 对条目级格式错误改为硬错误（含 index）。
  - 对未知字段、缺失字段、unexpected field 全部报错。
  - 保持 “2 条以上有效命令证据”门禁。
- 新增回归测试：
  - `tests/test_protocol_json.py::test_review_json_rejects_malformed_verification_item`

---

### 2026-02-20 03:55：回归稳定

对应日志：

- `.friends-bar/logs/20260219T195119404101Z_cf1a438a8fb94594b2a4c6cb81427cf9.summary.json`

结果：

1. 两轮都成功输出 JSON。
2. 无 `protocol_adapted` 文本修补。
3. 达菲 `verification` 字段结构正确。
4. `pytest` 回归通过。

## 3. 本次踩坑清单（按影响排序）

1. **Provider schema 兼容性低估**
   - 不同 CLI 对 JSON Schema 子集支持不完全一致。
   - 经验：只用最基础、最严格可移植子集（`type/enum/required/additionalProperties/items`）。

2. **流式事件去重策略不足**
   - 同时消费 delta + assistant + result 易重复。
   - 经验：流式展示和最终落盘要分离，最终文本要单源优先。

3. **“校验通过”不等于“数据可信”**
   - 归一化时静默丢弃错误字段会掩盖问题。
   - 经验：条目级错误必须可见，宁可失败重试也不隐式修复。

4. **重试成本高（达菲耗时明显）**
   - 一次失败会触发高成本全量重跑。
   - 经验：优先在 provider 层把输出收敛好，减少 orchestrator 重试压力。

## 4. 当前落地状态

### 已落地

1. JSON Schema Only 路径可运行。
2. `codex --output-schema` 与 `claude --json-schema` 均接入。
3. 自然语言补丁链路已从主执行路径移除。
4. 条目级严格校验与回归测试已补齐。

### 仍需持续观察

1. 达菲回合耗时较长（复杂任务可能接近 `standard` 上限）。
2. Claude CLI 在个别场景仍可能产出前后说明文本，需要继续观察日志。

## 5. 后续防回归动作（建议）

1. 新增端到端 smoke（双 agent 各 1 轮）到 CI。
2. 在日志汇总里增加“schema_error_topN”统计。
3. 对达菲单独设定“失败阈值告警”（连续 N 次 schema 失败即报警）。
4. 若后续增加新 agent，先写 schema + validator + malformed case 测试，再接入编排器。

## 6. 快速排障命令

```powershell
# 查看最近一次运行摘要
Get-ChildItem .friends-bar/logs/*.summary.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1

# 看某次运行中协议失败原因
rg -n "E_SCHEMA_|run.failed|turn.attempt.completed" .friends-bar/logs/<run_id>.jsonl

# 本地回归
python -m pytest -q
python friends-bar-demo.py "请仅做最小 JSON 协作演示，不要执行文件修改" --rounds 2 --start-agent linabell --timeout-level quick --project-path "e:\PythonProjects\multi-agent"
```

