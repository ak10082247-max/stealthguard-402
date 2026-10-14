# @elizaos/plugin-stealthguard

Official [ElizaOS (ai16z)](https://github.com/elizaOS/eliza) plugin for **StealthGuard-402**, **CanaryGuard**, and **RugShield** on Base Mainnet (`eip155:8453`).

Gives autonomous Twitter, Telegram, and Discord AI agents three critical superpowers:
1. **Cloudflare Stealth Web Scraping**: Bypass anti-bot protections to ingest news, articles, and whitepapers.
2. **Polymarket CLOB Alpha**: Stream real-time prediction market probability spikes and whale accumulation.
3. **Pre-Trade DEX Gate**: Inspect Base DEX tokens for honeypots and verify with CanaryGuard prompt-injection firewall before executing trades.

## Installation

```bash
npm install @elizaos/plugin-stealthguard
```

## Adding to Character

In your Eliza character JSON file (e.g., `characters/alpha-bot.json`):

```json
{
  "name": "AlphaBot",
  "plugins": ["@elizaos/plugin-stealthguard"],
  "settings": {
    "secrets": {
      "STEALTHGUARD_URL": "https://stealthguard-402.onrender.com"
    }
  }
}
```

## Available Actions

- `STEALTH_SCRAPE`: Scrape any URL into LLM markdown without being blocked by Cloudflare.
- `POLYMARKET_ALPHA`: Retrieve top prediction market divergences with volume and probability spreads.

Settlement: Base USDC (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`).
License: MIT
