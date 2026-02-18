#!/usr/bin/env node
"use strict";

// 这个文件是一个最小可运行入口：
// 1) 读取命令行 prompt
// 2) 调用统一接口 invoke("codex", prompt)
// 3) session 会自动从本地缓存恢复
const { invoke } = require("./src/invoke");

const prompt = process.argv.slice(2).join(" ").trim();

if (!prompt) {
  console.error('Usage: node minimal-codex.js "your prompt"');
  process.exit(1);
}

(async () => {
  try {
    await invoke("codex", prompt, {
      useSession: true, // 启用会话恢复
      stream: true, // 实时打印模型输出
    });
  } catch (err) {
    console.error(err.message || String(err));
    process.exit(1);
  }
})();

