"use strict";

const { invokeCodex } = require("./providers/codex");
const { invokeXxx } = require("./providers/xxx");
const { getSessionId, setSessionId } = require("./utils/session-store");

// provider 注册表：后续新增其它 AI，只需要在这里挂接即可。
const PROVIDERS = {
  codex: invokeCodex,
  xxx: invokeXxx, // 预留占位
};

// 统一调用入口
// 用法：
//   await invoke("xxx", "你好");
//   await invoke("codex", "你好");
//
// options:
// - useSession: 是否启用 session 恢复（默认 true）
// - stream: 是否实时打印输出（默认 true）
async function invoke(cli, prompt, options = {}) {
  if (typeof prompt !== "string" || !prompt.trim()) {
    throw new Error("prompt must be a non-empty string");
  }

  const providerName = String(cli || "").toLowerCase().trim();
  const provider = PROVIDERS[providerName];

  if (!provider) {
    const supported = Object.keys(PROVIDERS).join(", ");
    throw new Error(`Unsupported cli: ${cli}. Supported: ${supported}`);
  }

  const useSession = options.useSession !== false;
  const stream = options.stream !== false;

  // 若启用 session，则先读取上次会话 id。
  const lastSessionId = useSession ? getSessionId(providerName) : null;

  const result = await provider({
    prompt,
    sessionId: lastSessionId,
    stream,
  });

  // 若 provider 返回了新会话 id，则更新本地缓存。
  if (useSession && result.sessionId) {
    setSessionId(providerName, result.sessionId);
  }

  return {
    cli: providerName,
    prompt,
    text: result.text || "",
    sessionId: result.sessionId || null,
  };
}

module.exports = {
  invoke,
  SUPPORTED_CLIS: Object.keys(PROVIDERS),
};

