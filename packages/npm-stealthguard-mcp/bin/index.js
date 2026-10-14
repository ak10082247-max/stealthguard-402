#!/usr/bin/env node

/**
 * stealthguard-mcp
 * Zero-config stdio Model Context Protocol (MCP) proxy for StealthGuard-402.
 * Bridges Claude Desktop, Cursor, Windsurf, and Cline stdio directly to the live StealthGuard HTTP service.
 */

import readline from "node:readline";

const TARGET_URL = (process.env.STEALTHGUARD_URL || "https://stealthguard-402.onrender.com/mcp").trim();
const APIFY_TOKEN = process.env.APIFY_TOKEN ? process.env.APIFY_TOKEN.trim() : null;
const X402_SIGNATURE = process.env.X402_PAYMENT_SIGNATURE ? process.env.X402_PAYMENT_SIGNATURE.trim() : null;

process.stderr.write(`[stealthguard-mcp] Initialized stdio proxy -> ${TARGET_URL}\n`);

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
  terminal: false,
});

async function forwardMessage(rawLine) {
  const line = rawLine.trim();
  if (!line) return;

  let parsed;
  try {
    parsed = JSON.parse(line);
  } catch (err) {
    process.stderr.write(`[stealthguard-mcp] Invalid JSON received on stdin: ${err.message}\n`);
    const errorResponse = {
      jsonrpc: "2.0",
      id: null,
      error: { code: -32700, message: "Parse error" },
    };
    process.stdout.write(JSON.stringify(errorResponse) + "\n");
    return;
  }

  const reqId = parsed.id !== undefined ? parsed.id : null;

  // Build headers
  const headers = {
    "Content-Type": "application/json",
    "User-Agent": "stealthguard-mcp/1.0.0 (stdio-client)",
  };

  if (APIFY_TOKEN) {
    headers["Authorization"] = `Bearer ${APIFY_TOKEN}`;
    headers["X-Apify-Token"] = APIFY_TOKEN;
  }

  if (X402_SIGNATURE) {
    headers["PAYMENT-SIGNATURE"] = X402_SIGNATURE;
    headers["X-Payment"] = X402_SIGNATURE;
  }

  try {
    const response = await fetch(TARGET_URL, {
      method: "POST",
      headers,
      body: JSON.stringify(parsed),
    });

    const text = await response.text();
    let resJson;
    try {
      resJson = JSON.parse(text);
    } catch {
      resJson = {
        jsonrpc: "2.0",
        id: reqId,
        result: {
          content: [
            {
              type: "text",
              text: text || `HTTP ${response.status} ${response.statusText}`,
            },
          ],
        },
      };
    }

    // Write strictly to process.stdout
    process.stdout.write(JSON.stringify(resJson) + "\n");
  } catch (netErr) {
    process.stderr.write(`[stealthguard-mcp] Upstream error: ${netErr.message}\n`);
    const errorResponse = {
      jsonrpc: "2.0",
      id: reqId,
      error: {
        code: -32603,
        message: `Upstream StealthGuard connection error: ${netErr.message}`,
      },
    };
    process.stdout.write(JSON.stringify(errorResponse) + "\n");
  }
}

rl.on("line", (line) => {
  forwardMessage(line).catch((err) => {
    process.stderr.write(`[stealthguard-mcp] Uncaught forward error: ${err.message}\n`);
  });
});

process.on("SIGINT", () => {
  process.exit(0);
});
process.on("SIGTERM", () => {
  process.exit(0);
});
