"use strict";

const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const readline = require("readline");

// 安全列出目录下的子目录名称。
function listDirectories(dir) {
  try {
    return fs
      .readdirSync(dir, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name);
  } catch {
    return [];
  }
}

// Windows 场景：尝试定位 VS Code 扩展里自带的 codex.exe。
// 这样即使 PATH 里没有 codex，也能尽量运行起来。
function findVscodeBundledCodex() {
  if (process.platform !== "win32") return null;

  const userProfile = process.env.USERPROFILE;
  if (!userProfile) return null;

  const extensionsDir = path.join(userProfile, ".vscode", "extensions");
  const extensionDirs = listDirectories(extensionsDir)
    .filter((name) => name.startsWith("openai.chatgpt-"))
    .sort((a, b) => b.localeCompare(a, undefined, { numeric: true }));

  for (const extensionDir of extensionDirs) {
    const exePath = path.join(
      extensionsDir,
      extensionDir,
      "bin",
      "windows-x86_64",
      "codex.exe"
    );
    if (fs.existsSync(exePath)) return exePath;
  }

  return null;
}

// 决定要启动的 codex 命令。
// 优先级：CODEX_BIN > VS Code 内置 codex.exe > PATH 中的 codex。
function resolveCodexCommand() {
  if (process.env.CODEX_BIN) return process.env.CODEX_BIN;

  const bundled = findVscodeBundledCodex();
  if (bundled) return bundled;

  return "codex";
}

// 从可能的嵌套结构中提取纯文本。
function textFromParts(value) {
  if (typeof value === "string") return value;
  if (!value) return "";

  if (Array.isArray(value)) return value.map(textFromParts).join("");

  if (typeof value === "object") {
    if (typeof value.text === "string") return value.text;
    if (typeof value.output_text === "string") return value.output_text;
    if (Array.isArray(value.content)) return textFromParts(value.content);
    if (value.delta) return textFromParts(value.delta);
    if (value.message) return textFromParts(value.message);
  }

  return "";
}

// 兼容多种事件格式，统一抽取“助手文本”。
function extractAssistantText(event, state) {
  if (!event || typeof event !== "object") return "";

  // 记录/更新线程 id，用于后续 resume。
  if (event.type === "thread.started" && typeof event.thread_id === "string") {
    state.threadId = event.thread_id;
  }

  if (event.type === "item.completed" && event.item) {
    const itemType = event.item.type;
    if (itemType === "agent_message" || itemType === "assistant") {
      if (state.sawDelta) return "";
      return textFromParts(event.item.text || event.item.message || event.item.content);
    }
  }

  if (event.type === "agent_message_delta") {
    state.sawDelta = true;
    return textFromParts(event.delta);
  }

  if (event.type === "agent_message") {
    if (state.sawDelta) return "";
    return textFromParts(event.message);
  }

  if (event.type === "assistant") {
    if (state.sawDelta) return "";
    return textFromParts(event.message || event.content);
  }

  if (event.role === "assistant") {
    if (state.sawDelta) return "";
    return textFromParts(event.content || event.message || event.delta);
  }

  return "";
}

// 调用 codex 并流式返回文本。
// options:
// - prompt: 当前要发送的问题
// - sessionId: 若存在则使用 exec resume 继续会话
// - stream: 是否实时打印输出（默认 true）
function invokeCodex(options) {
  const { prompt, sessionId = null, stream = true } = options;

  return new Promise((resolve, reject) => {
    const codexCommand = resolveCodexCommand();
    const baseFlags = ["--json", "--skip-git-repo-check"];

    const args = sessionId
      ? ["exec", "resume", ...baseFlags, sessionId, prompt]
      : ["exec", ...baseFlags, prompt];

    const child = spawn(codexCommand, args, {
      stdio: ["ignore", "pipe", "pipe"],
    });

    const state = {
      sawDelta: false,
      threadId: sessionId,
      printedAny: false,
      needsNewline: false,
      output: "",
      stderr: [],
    };

    const stdoutRl = readline.createInterface({
      input: child.stdout,
      crlfDelay: Infinity,
    });

    stdoutRl.on("line", (line) => {
      const trimmed = line.trim();
      if (!trimmed) return;

      let event;
      try {
        event = JSON.parse(trimmed);
      } catch {
        return;
      }

      const text = extractAssistantText(event, state);
      if (!text) return;

      state.output += text;

      if (stream) {
        process.stdout.write(text);
        state.printedAny = true;
        state.needsNewline = !text.endsWith("\n");
      }
    });

    const stderrRl = readline.createInterface({
      input: child.stderr,
      crlfDelay: Infinity,
    });

    stderrRl.on("line", (line) => {
      if (!line.trim()) return;
      state.stderr.push(line);
      if (stream) {
        console.error(`[codex stderr] ${line}`);
      }
    });

    child.on("error", (err) => {
      if (err.code === "ENOENT") {
        reject(
          new Error(
            `Failed to start codex: ${err.message}. Tried command: ${codexCommand}.`
          )
        );
        return;
      }
      reject(new Error(`Failed to start codex: ${err.message}`));
    });

    child.on("close", (code, signal) => {
      if (stream && state.printedAny && state.needsNewline) {
        process.stdout.write("\n");
      }

      if (signal) {
        reject(new Error(`codex terminated by signal: ${signal}`));
        return;
      }

      if (code !== 0) {
        reject(
          new Error(
            `codex exited with code ${code}${
              state.stderr.length ? `: ${state.stderr.join(" | ")}` : ""
            }`
          )
        );
        return;
      }

      resolve({
        provider: "codex",
        text: state.output,
        sessionId: state.threadId || null,
      });
    });
  });
}

module.exports = {
  invokeCodex,
};

