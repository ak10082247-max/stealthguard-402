# @kurox_real/stealthguard-client

> Official TypeScript & Node.js client for **StealthGuard 402** — anti-bot stealth web scraping (Scrapling bypassing Cloudflare Turnstile), real-time Polymarket smart-money alpha divergence, and autonomous pre-trade risk gating on Base via x402 micropayments.

---

## ⚡ Quickstart

### 1. Install
```bash
npm install @kurox_real/stealthguard-client viem @x402/fetch @x402/evm @x402/core
```

### 2. Free Zero-Wallet Preview
```typescript
import { StealthGuardClient } from "@kurox_real/stealthguard-client";

const client = new StealthGuardClient();

// Free pre-trade verification for agents before execution
const verdict = await client.preTradeGatePreview("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913");
console.log("Verdict:", verdict.status); // "TRUST" | "BLOCK"
```

### 3. Production Paid x402 Execution
```typescript
import { StealthGuardClient } from "@kurox_real/stealthguard-client";

const client = new StealthGuardClient({
  privateKey: process.env.AGENT_PRIVATE_KEY as `0x${string}`,
});

// 1. Scrape protected target URL bypassing Cloudflare Turnstile ($0.015 USDC)
const page = await client.stealthScrape("https://news.ycombinator.com");
console.log("Clean Markdown:", page.markdown_content);

// 2. Scan Polymarket whale orderbook alpha divergence ($0.020 USDC)
const alpha = await client.polymarketAlpha({ category: "crypto", limit: 10 });
console.log("Divergences:", alpha.divergences_detected);
```

---

## 📄 License
MIT © kurox_real
