# stealthguard-mcp

Zero-config stdio Model Context Protocol (MCP) proxy for [StealthGuard-402](https://github.com/ak10082247-max/stealthguard-402).

Allows Cursor, Claude Desktop, Windsurf, Cline, and custom LLM agents to use StealthGuard's tools directly over standard input/output (stdio) with automatic routing to the live production server.

## Installation / 1-Click Setup

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "stealthguard": {
      "command": "npx",
      "args": ["-y", "stealthguard-mcp"],
      "env": {
        "STEALTHGUARD_URL": "https://stealthguard-402.onrender.com/mcp"
      }
    }
  }
}
```

### Cursor (`.cursor/mcp.json`)

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

### Free & Paid Tool Discovery

* `health_and_sample`: **Free** discovery probe (`readOnlyHint: true`) returning live status and sample outputs.
* `stealth_scrape_and_sanitize`: Stealth anti-bot web scraping ($0.02 USDC via x402 on Base or Apify PPE).
* `polymarket_alpha_divergence`: Live Polymarket CLOB & Gamma orderbook spread & whale divergence scanner ($0.05 USDC via x402 on Base or Apify PPE).
* `pre_trade_agent_gate`: On-chain honeypot & liquidity pre-trade security verification ($0.03 USDC via x402 on Base or Apify PPE).
