#!/usr/bin/env node
"use strict";

// 统一接口示例：
// 1) 先调用预留 provider（xxx）
// 2) 再调用 codex provider
const { invoke } = require("./src/invoke");

(async () => {
  try {
    await invoke("xxx", "你好", { useSession: false, stream: true });
    await invoke("codex", "你好", { useSession: true, stream: true });
  } catch (err) {
    console.error(err.message || String(err));
    process.exit(1);
  }
})();

