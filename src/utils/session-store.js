"use strict";

const fs = require("fs");
const path = require("path");

// 会话文件放在项目目录下，便于和项目绑定，不污染全局环境。
const SESSION_FILE = path.join(process.cwd(), ".sessions", "session-store.json");

// 读取会话缓存文件。
// 文件不存在或内容异常时，返回空对象，保证主流程不崩溃。
function loadSessionStore() {
  try {
    const raw = fs.readFileSync(SESSION_FILE, "utf8");
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

// 把会话缓存写回磁盘；目录不存在时自动创建。
function saveSessionStore(store) {
  const dir = path.dirname(SESSION_FILE);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(SESSION_FILE, JSON.stringify(store, null, 2), "utf8");
}

// 读取某个 provider 的 session id（例如 codex）。
function getSessionId(provider) {
  const store = loadSessionStore();
  return store[provider]?.sessionId || null;
}

// 更新某个 provider 的 session id，并记录更新时间。
function setSessionId(provider, sessionId) {
  const store = loadSessionStore();
  store[provider] = {
    sessionId,
    updatedAt: new Date().toISOString(),
  };
  saveSessionStore(store);
}

module.exports = {
  SESSION_FILE,
  getSessionId,
  setSessionId,
  loadSessionStore,
};

