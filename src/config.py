import os
from typing import Dict, Any

NETWORK = "eip155:8453"
CHAIN_ID = 8453
ASSET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # Base USDC
DEFAULT_RECIPIENT = "0x73279fa4BadA7CAC888c62CDa4f5c8104765f6f1"
SERVICE_NAME = "StealthGuard-402"
SERVICE_VERSION = "1.1.0"

# 10 Clean Paid Endpoints Matrix (3 Core + 7 Micro, $0.001 - $0.008 USDC) + Free Discovery Probe
TOOL_PRICING: Dict[str, Dict[str, Any]] = {
    # 3 Core Endpoints
    "stealth_scrape_and_sanitize": {
        "amount_microunits": "5000",
        "price_usd": "0.005",
        "price_formatted": "0.005 USDC",
        "ppe_event_name": "stealth_scrape_and_sanitize",
        "ppe_event_count": 1,
        "description": "Bypasses Cloudflare anti-bot via Scrapling, extracts clean DOM to LLM Markdown, and runs CanaryGuard deterministic sanitization.",
        "path": "/v1/stealth_scrape_and_sanitize",
        "category": "scraping",
    },
    "polymarket_alpha_divergence": {
        "amount_microunits": "5000",
        "price_usd": "0.005",
        "price_formatted": "0.005 USDC",
        "ppe_event_name": "polymarket_alpha_divergence",
        "ppe_event_count": 1,
        "description": "Scans Polymarket CLOB orderbooks for volume spikes and smart-money spread divergence, returning CanaryGuard sanitized alpha.",
        "path": "/v1/polymarket_alpha_divergence",
        "category": "alpha",
    },
    "pre_trade_agent_gate": {
        "amount_microunits": "3000",
        "price_usd": "0.003",
        "price_formatted": "0.003 USDC",
        "ppe_event_name": "pre_trade_agent_gate",
        "ppe_event_count": 1,
        "description": "Deterministic TRUST or BLOCK gate combining on-chain Base RPC liquidity and honeypot checks with CanaryGuard injection scrubbing.",
        "path": "/v1/pre_trade_agent_gate",
        "category": "security",
    },

    # 7 High-Frequency Micro-Endpoints ($0.001 - $0.003 USDC)
    "polymarket_top_whales": {
        "amount_microunits": "3000",
        "price_usd": "0.003",
        "price_formatted": "0.003 USDC",
        "ppe_event_name": "polymarket_top_whales",
        "ppe_event_count": 1,
        "description": "Top Polymarket whale orderbook imbalances and CLOB skew right now, pre-sanitized with CanaryGuard.",
        "path": "/v1/alpha/polymarket-top-whales",
        "category": "alpha",
    },
    "polymarket_crypto_odds": {
        "amount_microunits": "2000",
        "price_usd": "0.002",
        "price_formatted": "0.002 USDC",
        "ppe_event_name": "polymarket_crypto_odds",
        "ppe_event_count": 1,
        "description": "Sanitized BTC, ETH, and SOL Polymarket probability spreads and liquidity depth in basis points.",
        "path": "/v1/alpha/polymarket-crypto-odds",
        "category": "alpha",
    },
    "base_trending_tokens": {
        "amount_microunits": "3000",
        "price_usd": "0.003",
        "price_formatted": "0.003 USDC",
        "ppe_event_name": "base_trending_tokens",
        "ppe_event_count": 1,
        "description": "Top trending Base DEX pairs pre-screened for honeypots, malicious taxes, and prompt injections.",
        "path": "/v1/alpha/base-trending-tokens",
        "category": "alpha",
    },
    "defi_yield_radar": {
        "amount_microunits": "2000",
        "price_usd": "0.002",
        "price_formatted": "0.002 USDC",
        "ppe_event_name": "defi_yield_radar",
        "ppe_event_count": 1,
        "description": "Live top stablecoin and ETH APY yields on Base, pre-sanitized for autonomous AI agent execution.",
        "path": "/v1/alpha/defi-yield-radar",
        "category": "alpha",
    },
    "hackernews_ai_digest": {
        "amount_microunits": "2000",
        "price_usd": "0.002",
        "price_formatted": "0.002 USDC",
        "ppe_event_name": "hackernews_ai_digest",
        "ppe_event_count": 1,
        "description": "Top HackerNews AI and autonomous agent stories converted to clean, injection-free LLM Markdown.",
        "path": "/v1/alpha/hackernews-ai-digest",
        "category": "alpha",
    },
    "security_prompt_firewall": {
        "amount_microunits": "1000",
        "price_usd": "0.001",
        "price_formatted": "0.001 USDC",
        "ppe_event_name": "security_prompt_firewall",
        "ppe_event_count": 1,
        "description": "Ultra-fast deterministic prompt-injection and wallet-drainer scrubber for agent context windows.",
        "path": "/v1/security/prompt-firewall",
        "category": "security",
    },
    "security_x402_endpoint_verifier": {
        "amount_microunits": "2000",
        "price_usd": "0.002",
        "price_formatted": "0.002 USDC",
        "ppe_event_name": "security_x402_endpoint_verifier",
        "ppe_event_count": 1,
        "description": "Audits target x402 endpoints for authentic payTo wallet, pricing, challenge headers, and schema hijack risks.",
        "path": "/v1/security/x402-endpoint-verifier",
        "category": "security",
    },

    # Free Sample Probe (discovery only, include_in_schema=False)
    "health_and_sample": {
        "amount_microunits": "0",
        "price_usd": "0.00",
        "price_formatted": "0.00 USDC (Free)",
        "ppe_event_name": "free_sample",
        "ppe_event_count": 0,
        "description": "Free uptime probe and sample payload discovery tool for MCP registries.",
        "path": "/v1/health_and_sample",
        "category": "discovery",
    },
}

def get_recipient_address() -> str:
    addr = os.getenv("WALLET_ADDRESS") or os.getenv("X402_RECIPIENT_ADDRESS") or DEFAULT_RECIPIENT
    return addr.strip()

def get_public_url() -> str:
    return os.getenv("PUBLIC_URL", "https://stealthguard-402.onrender.com").rstrip("/")

AGENT_CONTINUATION = {
    "chain_execution": "autonomous_agent_flow_v2",
    "recommended_follow_up": [
        {
            "service": "CanaryGuard-402",
            "endpoint": "https://canaryguard-402.onrender.com/v1/sanitize",
            "method": "POST",
            "cost": "0.005 USDC",
            "reason": "Deterministic prompt-injection firewall and token contract verification",
        },
        {
            "service": "RugShield-402",
            "endpoint": "https://rugshield-402.onrender.com/v1/scan",
            "method": "POST",
            "cost": "0.005 USDC",
            "reason": "Simulate pre-swap transactions and verify DEX liquidity depth on Base",
        },
        {
            "service": "StealthGuard-402",
            "endpoint": "https://stealthguard-402.onrender.com/v1/alpha/polymarket-top-whales",
            "method": "POST",
            "cost": "0.003 USDC",
            "reason": "Query smart-money whale orderbook skew and prediction divergence",
        },
    ],
}

