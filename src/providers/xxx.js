"use strict";

// 这是“预留 provider”示例：
// 现在不真正调用外部 AI，只返回固定说明，方便统一接口先跑通。
async function invokeXxx(options) {
  const { prompt, stream = true } = options;
  const text = `[xxx placeholder] 已收到你的问题：${prompt}`;

  if (stream) {
    process.stdout.write(`${text}\n`);
  }

  return {
    provider: "xxx",
    text,
    sessionId: null,
  };
}

module.exports = {
  invokeXxx,
};

