# ⚡ Live Polymarket Alpha & Whale Divergence Feed

> **Last Automated Scan**: `2026-10-14 16:02:56 UTC`  
> **Source Engine**: Polymarket Gamma API + Live CLOB Orderbook Divergence + CanaryGuard Firewall  
> **Update Cadence**: Refreshed automatically every 2 hours via GitHub Actions  
> **Uptime & Pay-to-Call**: [`https://stealthguard-402.onrender.com`](https://stealthguard-402.onrender.com) | Wallet: `0x73279fa4BadA7CAC888c62CDa4f5c8104765f6f1`

---

## 🔒 Top #1 Whale Divergence Leader (Locked Preview)

Every 2 hours, StealthGuard identifies the prediction market experiencing the most aggressive smart-money volume surge relative to its orderbook depth:

| Metric | Scanned Live Reading |
| :--- | :--- |
| **Market / Question** | **`[REDACTED: Top Whale-Accumulated Market - 13.3x Volume/Liquidity Ratio]`** |
| **24-Hour Trading Volume** | **$497,924 USD** |
| **Book Liquidity Depth** | **$37,371 USD** |
| **Volume-to-Liquidity Ratio** | **13.32x Surge** |
| **CLOB Spread Bps** | `[LOCKED: Requires $0.05 USDC micropayment]` |
| **Whale Bid/Ask Imbalance** | `[LOCKED: Requires $0.05 USDC micropayment]` |
| **CanaryGuard Safety Receipt** | **`PASSED (Risk Score: 0.00 / Clean Resolution Criteria)`** |

### 🔓 How to Unlock the Unredacted #1 Market & Full 25-Market Live Feed:
1. **Direct HTTP x402 on Base (`$0.05 USDC`)**:
   ```bash
   curl -X POST https://stealthguard-402.onrender.com/v1/polymarket_alpha_divergence \
     -H "Content-Type: application/json" \
     -H "PAYMENT-SIGNATURE: <eip712_signature>" \
     -d '{"limit": 25}'
   ```
2. **Apify Store Pay-Per-Event (PPE)**:
   Run the [StealthGuard-402 Apify Actor](https://apify.com/kuroxreal/stealthguard-402) with `tool: "polymarket_alpha_divergence"`.
3. **Cursor, Windsurf, or Claude Desktop stdio**:
   ```bash
   npx -y stealthguard-mcp
   ```

---

## 🛡️ Proof of Quality: 2 Verified Live Sample Markets

Here are two unredacted live markets scanned in this latest batch with their calculated spread and deterministic CanaryGuard resolution receipts:

| Market Question | Volume (24h) | Liquidity | Vol/Liq Ratio | Spread | Alpha Rating | CanaryGuard |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Will there be no change in Fed interest rates after the October 2026 meeting? | $2,117,021 | $203,947 | **10.38x** | 100.0 bps | `HIGH_WHALE_DIVERGENCE` | `PASSED (0.00)` |
| Will the Fed increase interest rates by 25 bps after the October 2026 meeting? | $1,213,106 | $148,303 | **8.18x** | 100.0 bps | `HIGH_WHALE_DIVERGENCE` | `PASSED (0.00)` |

---

## 🤖 For Autonomous Agents & Trading Bots
* **JSON Feed Endpoint**: [`feed/latest_alpha.json`](./feed/latest_alpha.json)
* **OpenAPI 3.0 Manifest**: [`openapi-rapidapi.json`](./openapi-rapidapi.json)
* **MCP Streamable HTTP Endpoint**: `https://stealthguard-402.onrender.com/mcp`
* **Discovery Manifest**: `https://stealthguard-402.onrender.com/.well-known/x402`
