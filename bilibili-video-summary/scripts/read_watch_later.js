#!/usr/bin/env node
"use strict";

const fs = require("fs");

function usage() {
  console.log(`Usage: node read_watch_later.js [options]

Options:
  --debug-port <port>     Bilibili client DevTools port (default: 9223)
  --page <number>         1-based API page (default: 1)
  --limit <number>        Number of items, 1-100 (default: 20)
  --output <file>         Write normalized JSON to this file
  --sources-output <file> Write one canonical video URL per line
  --help                  Show this help
`);
}

function parseArgs(argv) {
  const args = { debugPort: 9223, page: 1, limit: 20 };
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    if (key === "--help") {
      args.help = true;
    } else if (key === "--debug-port") {
      args.debugPort = Number(argv[++index]);
    } else if (key === "--page") {
      args.page = Number(argv[++index]);
    } else if (key === "--limit") {
      args.limit = Number(argv[++index]);
    } else if (key === "--output") {
      args.output = argv[++index];
    } else if (key === "--sources-output") {
      args.sourcesOutput = argv[++index];
    } else {
      throw new Error(`Unknown argument: ${key}`);
    }
  }
  if (!Number.isInteger(args.debugPort) || args.debugPort < 1 || args.debugPort > 65535) {
    throw new Error("--debug-port must be an integer between 1 and 65535");
  }
  if (!Number.isInteger(args.page) || args.page < 1) {
    throw new Error("--page must be a positive integer");
  }
  if (!Number.isInteger(args.limit) || args.limit < 1 || args.limit > 100) {
    throw new Error("--limit must be an integer between 1 and 100");
  }
  return args;
}

function connectWebSocket(url) {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(url);
    socket.addEventListener("open", () => resolve(socket), { once: true });
    socket.addEventListener("error", () => reject(new Error("DevTools WebSocket connection failed")), { once: true });
  });
}

function makeEvaluator(socket) {
  let requestId = 0;
  return (expression) => new Promise((resolve, reject) => {
    const id = ++requestId;
    const timeout = setTimeout(() => {
      socket.removeEventListener("message", onMessage);
      reject(new Error("DevTools evaluation timed out"));
    }, 30000);
    const onMessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.id !== id) return;
      socket.removeEventListener("message", onMessage);
      clearTimeout(timeout);
      if (message.error) {
        reject(new Error(JSON.stringify(message.error)));
        return;
      }
      if (message.result && message.result.exceptionDetails) {
        reject(new Error("Bilibili client evaluation failed"));
        return;
      }
      const result = message.result && message.result.result;
      resolve(result ? result.value : undefined);
    };
    socket.addEventListener("message", onMessage);
    socket.send(JSON.stringify({
      id,
      method: "Runtime.evaluate",
      params: { expression, awaitPromise: true, returnByValue: true },
    }));
  });
}

async function clientFetch(evaluate, url) {
  const expression = `fetch(${JSON.stringify(url)}, {credentials: 'include'}).then(async (response) => ({status: response.status, text: await response.text()}))`;
  const response = await evaluate(expression);
  if (!response || response.status < 200 || response.status >= 300) {
    throw new Error(`Bilibili client request failed with HTTP ${response && response.status}`);
  }
  const data = JSON.parse(response.text);
  if (data.code !== 0) {
    throw new Error(`Bilibili API error ${data.code}: ${data.message || data.msg}`);
  }
  return data;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    usage();
    return;
  }
  if (typeof WebSocket !== "function") {
    throw new Error("This script requires a Node.js runtime with global WebSocket support");
  }

  const endpoint = `http://127.0.0.1:${args.debugPort}`;
  const targetsResponse = await fetch(`${endpoint}/json/list`);
  if (!targetsResponse.ok) {
    throw new Error(`Bilibili client DevTools endpoint returned HTTP ${targetsResponse.status}`);
  }
  const targets = await targetsResponse.json();
  const target = targets.find((item) => String(item.url).includes("index.html")) || targets[0];
  if (!target || !target.webSocketDebuggerUrl) {
    throw new Error("No Bilibili client page is available on the DevTools endpoint");
  }

  const socket = await connectWebSocket(target.webSocketDebuggerUrl);
  try {
    const evaluate = makeEvaluator(socket);
    const listUrl = `https://api.bilibili.com/x/v2/history/toview/web?ps=${args.limit}&pn=${args.page}`;
    const listData = await clientFetch(evaluate, listUrl);
    const items = [];
    for (const [index, video] of (listData.data?.list || []).slice(0, args.limit).entries()) {
      const bvid = String(video.bvid || "");
      if (!/^BV[0-9A-Za-z]{10}$/.test(bvid)) continue;
      const detail = await clientFetch(
        evaluate,
        `https://api.bilibili.com/x/web-interface/view?bvid=${encodeURIComponent(bvid)}`,
      );
      items.push({
        order: (args.page - 1) * args.limit + index + 1,
        source_type: "watch_later",
        source_url: `https://www.bilibili.com/video/${bvid}`,
        bvid,
        aid: String(video.aid || detail.data?.aid || ""),
        cid: String(video.cid || detail.data?.cid || ""),
        title: video.title || detail.data?.title || bvid,
        owner: video.owner?.name || detail.data?.owner?.name || null,
        duration_seconds: video.duration || detail.data?.duration || null,
        description: detail.data?.desc || "",
      });
    }
    const writeText = (destination, content) => {
      const parent = require("path").dirname(destination);
      fs.mkdirSync(parent, { recursive: true });
      fs.writeFileSync(destination, content, "utf8");
    };
    const json = `${JSON.stringify(items, null, 2)}\n`;
    if (args.output) writeText(args.output, json);
    if (args.sourcesOutput) {
      writeText(args.sourcesOutput, `${items.map((item) => item.source_url).join("\n")}\n`);
    }
    process.stdout.write(json);
  } finally {
    socket.close();
  }
}

main().catch((error) => {
  console.error(`FAIL: ${error.message}`);
  process.exit(2);
});
