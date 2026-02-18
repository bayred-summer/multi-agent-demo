# multi-agent-demo

一个基于 Node.js 的最小多 AI 调用示例，重点演示：

- 统一入口 `invoke(cli, prompt)`
- `codex` 的流式 JSON 解析
- 本地 session 记忆与 `resume` 继续对话
- 预留其它 provider（`xxx` 占位）

## 目录结构

```text
multi-agent-demo/
├─ minimal-codex.js          # 最小入口：只调用 codex
├─ demo-invoke.js            # 统一接口演示（xxx + codex）
├─ src/
│  ├─ invoke.js              # 统一调用入口 invoke(cli, prompt)
│  ├─ providers/
│  │  ├─ codex.js            # codex provider（含流式解析与 resume）
│  │  └─ xxx.js              # 预留 provider（占位）
│  └─ utils/
│     └─ session-store.js    # session 本地读写
└─ .sessions/                # 运行后自动生成（已在 .gitignore 中忽略）
```

## 运行前准备

1. 安装 Node.js（建议 LTS）
2. 安装并登录 Codex CLI

```bash
npm i -g @openai/codex
codex login
```

## 快速使用

### 1) 最小 Codex 调用（支持自动续聊）

```bash
node minimal-codex.js "你好，请用一句话介绍自己"
```

脚本内部会调用：

```bash
codex exec --json --skip-git-repo-check "<你的问题>"
```

如果本地已有会话，会自动切换为：

```bash
codex exec resume --json --skip-git-repo-check "<sessionId>" "<你的问题>"
```

### 2) 统一接口示例

```bash
node demo-invoke.js
```

这个示例会先调用预留 provider `xxx`，再调用 `codex`。

## 统一接口说明

`src/invoke.js` 提供：

```js
await invoke("xxx", "你好");
await invoke("codex", "你好");
```

返回值结构（统一）：

```js
{
  cli: "codex",
  prompt: "你好",
  text: "模型回复文本",
  sessionId: "thread-id-or-null"
}
```

## Session 恢复机制

- 会话文件位置：`.sessions/session-store.json`
- 以 provider 名称为 key（例如 `codex`）
- 每次调用成功后更新 `sessionId`
- 下次调用同一 provider 自动 `resume`

如果你想重置会话，删除 `.sessions/session-store.json` 即可。

## 开发流程记录（从 Codex CLI 安装开始）

以下为本项目本次开发的实际流程记录：

1. 安装 Node.js LTS（Windows，`winget` 用户级安装）。
2. 安装 Codex CLI：`npm i -g @openai/codex`。
3. 验证登录状态：`codex login status`（已登录）。
4. 实现首版 `minimal-codex.js`，完成 `spawn + readline + JSONL` 流式解析。
5. 修复 Windows `spawn codex ENOENT` 问题，加入可执行文件自动定位策略。
6. 抽象统一入口 `invoke(cli, prompt)`，新增 provider 注册机制。
7. 增加 `xxx` 预留 provider，用于后续接入其它 AI。
8. 增加 session 本地持久化，并接入 `codex exec resume` 自动续聊。
9. 重构入口脚本并补充示例、文档与 `.gitignore`。

