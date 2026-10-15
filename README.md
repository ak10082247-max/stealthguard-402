# StealthGuard-402 🛡️⚡

[![Base Mainnet](https://img.shields.io/badge/Network-Base%20Mainnet%20(8453)-blue)](https://base.org)
[![MCPize](https://img.shields.io/badge/MCPize-Subscribe%20%2419%2Fmo-8A2BE2?logo=stripe&logoColor=white)](https://mcpize.com)
[![Apify PPE](https://img.shields.io/badge/Apify-Pay--Per--Event-00A65A?logo=apify&logoColor=white)](https://apify.com)
[![Protocol](https://img.shields.io/badge/Protocol-x402%20v2-green)](https://x402.org)

> High-margin, production-ready revenue service fusing **CanaryGuard** (`io.github.ak10082247-max/canaryguard-402`) with **Scrapling** anti-bot stealth extraction and **Polymarket/on-chain prediction alpha**, monetized concurrently via **Direct x402 on Base**, **Apify Pay-Per-Event (PPE)**, and **MCPize Fiat Subscriptions**.

---

## 💳 Subscribe on MCPize / Apify ($19/mo Pro)

For developers, automated agents, and enterprise teams that prefer traditional fiat billing (credit card via Stripe) over per-request crypto micro-settlements, **StealthGuard-402** is available as a turnkey hosted subscription on **[MCPize](https://mcpize.com)** and **Apify**:

| Plan | Price | Monthly Quota | Key Features |
|---|---|---|---|
| **Starter** | **$9.99 / mo** | 1,000 calls | Scrapling anti-bot bypass, CanaryGuard injection firewall, Polymarket divergence |
| **Pro (Recommended)** | **$19.99 / mo** | 10,000 calls | Pre-warmed cache (<50ms), DEX pre-trade honeypot gating, priority SLA |
| **Enterprise** | **$49.99 / mo** | 50,000 calls | Dedicated isolated instance, custom fingerprint rotation, developer channel |

- **Instant 1-Click Subscribe**: Paste `https://github.com/ak10082247-max/stealthguard-402` into your **[MCPize Dashboard](https://mcpize.com/dashboard)**.
- **Direct Remote MCP Endpoint**: `https://stealthguard-402.onrender.com/mcp`

---

## 🚀 Dual-Rail Monetization Architecture

```
                    ┌────────────────────────────────────────┐
                    │            StealthGuard-402            │
                    │   CanaryGuard Deterministic Firewall   │
                    └───────────────────┬────────────────────┘
                                        │
             ┌──────────────────────────┴──────────────────────────┐
             ▼                                                     ▼
┌─────────────────────────┐                             ┌─────────────────────────┐
│     Rail A: Direct      │                             │     Rail B: Apify PPE   │
│        x402 Base        │                             │    Pay-Per-Event Actor  │
├─────────────────────────┤                             ├─────────────────────────┤
│ • Base USDC (eip155:8453│                             │ • Apify Fiat Billing    │
│ • HTTP 402 Challenges   │                             │ • Apify Direct x402     │
│ • Bazaar Auto-Discovery │                             │ • Skyfire AI Network    │
│ • Render / Railway      │                             │ • mcp.apify.com bridge  │
└─────────────────────────┘                             └─────────────────────────┘
```

---

## 🛠️ Tool Catalog (HTTP REST & MCP)

Every paid tool runs scraped content and external metadata through **CanaryGuard's deterministic prompt-injection firewall**, returning a cryptographically verifiable `canaryguard_receipt` (`risk_score`, `threats_neutralized`, `safe_to_persist: boolean`).

| Tool Name | Price (x402 Base) | Apify PPE Events | Method | Description |
|---|---|---|---|---|
| `stealth_scrape_and_sanitize` | **$0.02 USDC** (20,000 units) | **1 event** ($0.02) | `POST /v1/stealth_scrape_and_sanitize` | Bypasses Cloudflare Turnstile & anti-bot shields via Scrapling `StealthyFetcher`, parses DOM into token-compressed LLM Markdown, and strips prompt injection / wallet-drain attacks before memory persistence. |
| `polymarket_alpha_divergence` | **$0.05 USDC** (50,000 units) | **2 events** ($0.025 × 2 = $0.05) | `POST /v1/polymarket_alpha_divergence` | Scans Polymarket Gamma + CLOB orderbooks for volume spikes and smart-money spread divergence, scrapes market resolution source URLs via Scrapling, and sanitizes resolution rules to flag fake-news or prompt-injection manipulation. |
| `pre_trade_agent_gate` | **$0.03 USDC** (30,000 units) | **1 event** ($0.03) | `POST /v1/pre_trade_agent_gate` | Upgrades CanaryGuard token inspection by combining DexScreener liquidity analysis & Base/Solana RPC honeypot checks with CanaryGuard website/metadata inspection. Returns deterministic `TRUST` / `BLOCK` verdict. |
| `health_and_sample` | **$0.00 (Free)** | **0 events** | `GET /v1/health_and_sample` | Zero-barrier probe endpoint returning live server status, payment recipient address, and representative sample payloads. Ensures 100% uptime score across MCP registries (Glama, Smithery, x402Atlas, Apify). |

---

## 🔒 CanaryGuard Receipt Schema

All paid responses include a tamper-evident inspection receipt:

```json
{
  "canaryguard_receipt": {
    "status": "clean",
    "risk_score": 0.01,
    "injection_detected": false,
    "threats_neutralized": [],
    "sanitized_content": "# Clean Markdown Output",
    "safe_to_persist": true,
    "safety_receipt": "canary-v1-verified",
    "crypto_addresses": [],
    "inspection": {
      "method": "deterministic-rules",
      "guaranteed_safe": false,
      "risk_score_semantics": "heuristic severity, not a probability"
    }
  }
}
```

---

## ⚡ Integration & Discovery

### 1. Model Context Protocol (MCP) Streamable HTTP
- **URL**: `POST https://stealthguard-402.onrender.com/mcp`
- **Protocol**: JSON-RPC 2.0 (Streamable HTTP)
- **Tool Listing**: `tools/list` returns Glama TDQS-compliant tool schemas with `readOnlyHint: true` and explicit pricing tags.

### 2. x402 Discovery & Bazaar Auto-Indexing
Facilitators querying `/.well-known/x402` or evaluating `PAYMENT-REQUIRED` headers automatically receive the `@x402/extensions/bazaar` declaration:
- Manifest: `https://stealthguard-402.onrender.com/.well-known/x402.json`
- OpenAPI: `https://stealthguard-402.onrender.com/openapi.json`
- LLMs Text: `https://stealthguard-402.onrender.com/llms.txt`

### 3. Apify Pay-Per-Event (PPE) Mode
The actor entrypoint `apify_main.py` is configured with `.actor/actor.json` and `.actor/pay_per_event.json`:
```bash
# Run locally with Apify SDK
python apify_main.py
```

---

## 🧪 Verification & Test Suite

The comprehensive pytest test suite verifies:
- 402 challenge formatting with Base USDC parameters
- Bazaar discovery extension schema compliance
- EIP-712 TransferWithAuthorization cryptographic signature recovery
- 24-hour LRU signature replay attack prevention (HTTP 409)
- All 4 tool execution pipelines
- Glama TDQS schema compliance for MCP Streamable HTTP
- Apify PPE charging events and dataset push flows

```bash
pytest -v
```

```
tests/test_api_endpoints.py::test_api_health_and_stats PASSED
tests/test_api_endpoints.py::test_api_x402_manifest_and_discovery PASSED
tests/test_api_endpoints.py::test_api_unpaid_endpoints_return_402 PASSED
tests/test_api_endpoints.py::test_api_mcp_streamable_http PASSED
tests/test_apify_ppe.py::test_apify_ppe_stealth_scrape_charge_and_push PASSED
tests/test_apify_ppe.py::test_apify_ppe_polymarket_charge_and_push PASSED
tests/test_apify_ppe.py::test_apify_ppe_pre_trade_gate_charge_and_push PASSED
tests/test_mcp.py::test_mcp_initialize PASSED
tests/test_mcp.py::test_mcp_tools_list_glama_tdqs PASSED
tests/test_mcp.py::test_mcp_tools_call_free_discovery PASSED
tests/test_mcp.py::test_mcp_tools_call_unpaid_returns_402 PASSED
tests/test_sanitizer.py::test_clean_content PASSED
tests/test_sanitizer.py::test_instruction_override_strict PASSED
tests/test_sanitizer.py::test_role_delimiter_override PASSED
tests/test_sanitizer.py::test_wallet_drainer_command PASSED
tests/test_sanitizer.py::test_hidden_html_removal PASSED
tests/test_sanitizer.py::test_active_html_script_removal PASSED
tests/test_tools.py::test_health_and_sample_tool PASSED
tests/test_tools.py::test_stealth_scrape_and_sanitize_tool PASSED
tests/test_tools.py::test_polymarket_alpha_divergence_tool PASSED
tests/test_tools.py::test_pre_trade_agent_gate_usdc_trust PASSED
tests/test_tools.py::test_pre_trade_agent_gate_invalid_address_block PASSED
tests/test_x402_challenge.py::test_build_402_challenge_headers_and_body PASSED
tests/test_x402_challenge.py::test_unpaid_verification_returns_402 PASSED
tests/test_x402_challenge.py::test_valid_eip712_payment_verification_and_replay_protection PASSED

======================= 25 passed in 6.92s ========================
```

---

## ⚡ Zero-Config Stdio Client Packages (Cursor / Claude / Windsurf)

Most AI developer tools and desktop agent environments connect to MCP servers via `stdio`. StealthGuard provides zero-config proxy wrappers for Node and Python that automatically route stdio calls to the live production server:

### Option A: Node / NPX
```bash
npx -y stealthguard-mcp
```

**Claude Desktop Configuration (`claude_desktop_config.json`):**
```json
{
  "mcpServers": {
    "stealthguard": {
      "command": "npx",
      "args": ["-y", "stealthguard-mcp"]
    }
  }
}
```

### Option B: Python / UVX
```bash
uvx stealthguard-mcp
```
or via pip:
```bash
pip install stealthguard-mcp
```

---

## 📊 Live Polymarket Alpha & Proof-of-Quality Feed

StealthGuard scans live Polymarket prediction markets every 2 hours via automated GitHub Actions, publishing top whale divergences, orderbook spreads, and deterministic CanaryGuard safety receipts directly to the repository:

* 📄 **Markdown Feed**: [LIVE_POLYMARKET_ALPHA.md](./LIVE_POLYMARKET_ALPHA.md)
* 🤖 **Machine-Readable JSON**: [feed/latest_alpha.json](./feed/latest_alpha.json)
* 🔄 **Automated Schedule**: Runs every 2 hours via [`workflows/live_alpha_feed.yml`](./workflows/live_alpha_feed.yml)

---

## 🚢 Production Deployment

### Live Service
- **Render Production URL**: `https://stealthguard-402.onrender.com`
- **Streamable HTTP MCP**: `https://stealthguard-402.onrender.com/mcp`
- **Discovery Manifest**: `https://stealthguard-402.onrender.com/.well-known/x402`
- **Apify Actor**: [kuroxreal/stealthguard-402](https://apify.com/kuroxreal/stealthguard-402)
- **Base Payout Wallet**: `0x73279fa4BadA7CAC888c62CDa4f5c8104765f6f1`

