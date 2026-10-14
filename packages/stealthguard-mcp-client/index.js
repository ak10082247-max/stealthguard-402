#!/usr/bin/env node
/**
 * StealthGuard-402 MCP Client Proxy
 * Bridges standard stdio MCP clients (Claude Desktop, Cursor, OpenClaw)
 * to https://stealthguard-402.onrender.com/mcp.
 */

const https = require('https');
const readline = require('readline');

const SERVER_URL = process.env.STEALTHGUARD_URL || 'https://stealthguard-402.onrender.com/mcp';

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
  terminal: false
});

rl.on('line', (line) => {
  if (!line.trim()) return;
  try {
    const jsonRpcReq = JSON.parse(line);
    const data = JSON.stringify(jsonRpcReq);

    const url = new URL(SERVER_URL);
    const options = {
      hostname: url.hostname,
      port: 443,
      path: url.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(data),
        'User-Agent': 'StealthGuard-MCP-Client/1.0',
      }
    };

    if (process.env.X402_PAYMENT_SIGNATURE) {
      options.headers['PAYMENT-SIGNATURE'] = process.env.X402_PAYMENT_SIGNATURE;
    }

    const req = https.request(options, (res) => {
      let body = '';
      res.on('data', (chunk) => { body += chunk; });
      res.on('end', () => {
        try {
          process.stdout.write(body + '\n');
        } catch (e) {
          console.error('Error forwarding MCP response:', e);
        }
      });
    });

    req.on('error', (e) => {
      const errResp = {
        jsonrpc: '2.0',
        id: jsonRpcReq.id,
        error: { code: -32603, message: `StealthGuard MCP Proxy Error: ${e.message}` }
      };
      process.stdout.write(JSON.stringify(errResp) + '\n');
    });

    req.write(data);
    req.end();
  } catch (err) {
    console.error('Malformed JSON-RPC request:', err);
  }
});
