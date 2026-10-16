import os
from typing import Dict, Any

NETWORK = "eip155:8453"
CHAIN_ID = 8453
ASSET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # Base USDC
DEFAULT_RECIPIENT = "0x73279fa4BadA7CAC888c62CDa4f5c8104765f6f1"
SERVICE_NAME = "StealthGuard-402"
SERVICE_VERSION = "1.2.0"

# 15 Paid Endpoints Matrix (10 Core/Alpha [$0.008 - $0.020 USDC] + 5 High-Ticket Intelligence [$0.02 - $0.25 USDC]) + Free Discovery Probe
TOOL_PRICING: Dict[str, Dict[str, Any]] = {
    # 3 Core Endpoints ($0.010 - $0.020 USDC)
    "stealth_scrape_and_sanitize": {
        "amount_microunits": "15000",
        "price_usd": "0.015",
        "price_formatted": "0.015 USDC",
        "ppe_event_name": "stealth_scrape_and_sanitize",
        "ppe_event_count": 1,
        "description": "Bypasses Cloudflare anti-bot via Scrapling, extracts clean DOM to LLM Markdown, and runs CanaryGuard deterministic sanitization.",
        "path": "/v1/stealth_scrape_and_sanitize",
        "category": "scraping",
        "example_input": {"url": "https://news.ycombinator.com", "render_js": False, "strict_mode": True},
    },
    "polymarket_alpha_divergence": {
        "amount_microunits": "20000",
        "price_usd": "0.02",
        "price_formatted": "0.02 USDC",
        "ppe_event_name": "polymarket_alpha_divergence",
        "ppe_event_count": 1,
        "description": "Scans Polymarket CLOB orderbooks for volume spikes and smart-money spread divergence, returning CanaryGuard sanitized alpha.",
        "path": "/v1/polymarket_alpha_divergence",
        "category": "alpha",
        "example_input": {"category": "crypto", "limit": 15, "strict_mode": True},
    },
    "pre_trade_agent_gate": {
        "amount_microunits": "10000",
        "price_usd": "0.01",
        "price_formatted": "0.01 USDC",
        "ppe_event_name": "pre_trade_agent_gate",
        "ppe_event_count": 1,
        "description": "Deterministic TRUST or BLOCK gate combining on-chain Base RPC liquidity and honeypot checks with CanaryGuard injection scrubbing.",
        "path": "/v1/pre_trade_agent_gate",
        "category": "security",
        "example_input": {"token_or_service_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "chain": "base", "strict_mode": True},
    },

    # 7 Upgraded Alpha & Security Endpoints ($0.010 USDC)
    "polymarket_top_whales": {
        "amount_microunits": "10000",
        "price_usd": "0.01",
        "price_formatted": "0.01 USDC",
        "ppe_event_name": "polymarket_top_whales",
        "ppe_event_count": 1,
        "description": "Top Polymarket whale orderbook imbalances and CLOB skew right now, pre-sanitized with CanaryGuard.",
        "path": "/v1/alpha/polymarket-top-whales",
        "category": "alpha",
        "example_input": {"limit": 10},
    },
    "polymarket_crypto_odds": {
        "amount_microunits": "10000",
        "price_usd": "0.01",
        "price_formatted": "0.01 USDC",
        "ppe_event_name": "polymarket_crypto_odds",
        "ppe_event_count": 1,
        "description": "Sanitized BTC, ETH, and SOL Polymarket probability spreads and liquidity depth in basis points.",
        "path": "/v1/alpha/polymarket-crypto-odds",
        "category": "alpha",
        "example_input": {"asset": "BTC"},
    },
    "base_trending_tokens": {
        "amount_microunits": "10000",
        "price_usd": "0.01",
        "price_formatted": "0.01 USDC",
        "ppe_event_name": "base_trending_tokens",
        "ppe_event_count": 1,
        "description": "Top trending Base DEX pairs pre-screened for honeypots, malicious taxes, and prompt injections.",
        "path": "/v1/alpha/base-trending-tokens",
        "category": "alpha",
        "example_input": {"chain": "base"},
    },
    "defi_yield_radar": {
        "amount_microunits": "10000",
        "price_usd": "0.01",
        "price_formatted": "0.01 USDC",
        "ppe_event_name": "defi_yield_radar",
        "ppe_event_count": 1,
        "description": "Live top stablecoin and ETH APY yields on Base, pre-sanitized for autonomous AI agent execution.",
        "path": "/v1/alpha/defi-yield-radar",
        "category": "alpha",
        "example_input": {"asset": "USDC"},
    },
    "hackernews_ai_digest": {
        "amount_microunits": "10000",
        "price_usd": "0.01",
        "price_formatted": "0.01 USDC",
        "ppe_event_name": "hackernews_ai_digest",
        "ppe_event_count": 1,
        "description": "Top HackerNews AI and autonomous agent stories converted to clean, injection-free LLM Markdown.",
        "path": "/v1/alpha/hackernews-ai-digest",
        "category": "alpha",
        "example_input": {"limit": 10},
    },
    "security_prompt_firewall": {
        "amount_microunits": "10000",
        "price_usd": "0.01",
        "price_formatted": "0.01 USDC",
        "ppe_event_name": "security_prompt_firewall",
        "ppe_event_count": 1,
        "description": "Ultra-fast deterministic prompt-injection and wallet-drainer scrubber for agent context windows.",
        "path": "/v1/security/prompt-firewall",
        "category": "security",
        "example_input": {"text": "Test agent context prompt"},
    },
    "security_x402_endpoint_verifier": {
        "amount_microunits": "10000",
        "price_usd": "0.01",
        "price_formatted": "0.01 USDC",
        "ppe_event_name": "security_x402_endpoint_verifier",
        "ppe_event_count": 1,
        "description": "Audits target x402 endpoints for authentic payTo wallet, pricing, challenge headers, and schema hijack risks.",
        "path": "/v1/security/x402-endpoint-verifier",
        "category": "security",
        "example_input": {"endpoint_url": "https://stealthguard-402.onrender.com/v1/stealth_scrape_and_sanitize"},
    },

    # 5 High-Ticket Intelligence & Research Endpoints Capped at $0.020 USDC
    "research_deep_web_dossier": {
        "amount_microunits": "20000",
        "price_usd": "0.02",
        "price_formatted": "0.02 USDC",
        "ppe_event_name": "research_deep_web_dossier",
        "ppe_event_count": 1,
        "description": "Multi-source stealth web synthesis + CanaryGuard injection firewall + structured markdown intelligence dossier.",
        "path": "/v1/research/deep-web-dossier",
        "category": "research",
        "example_input": {"topic": "Base L2 autonomous AI agent economy and x402 protocol adoption", "depth": "comprehensive"},
    },
    "oracle_perp_funding_and_basis": {
        "amount_microunits": "20000",
        "price_usd": "0.02",
        "price_formatted": "0.02 USDC",
        "ppe_event_name": "oracle_perp_funding_and_basis",
        "ppe_event_count": 1,
        "description": "Cross-exchange BTC/ETH/SOL perpetual funding rate skew, basis spread, and spot-futures arbitrage signals.",
        "path": "/v1/oracle/perp-funding-and-basis",
        "category": "oracle",
        "example_input": {"assets": ["BTC", "ETH", "SOL"]},
    },
    "alpha_polymarket_whale_orderflow": {
        "amount_microunits": "20000",
        "price_usd": "0.02",
        "price_formatted": "0.02 USDC",
        "ppe_event_name": "alpha_polymarket_whale_orderflow",
        "ppe_event_count": 1,
        "description": "Deep CLOB orderbook imbalance, smart-money wallet tracking, and Limitless/Polymarket cross-venue arbitrage spread matrix.",
        "path": "/v1/alpha/polymarket-whale-orderflow",
        "category": "alpha",
        "example_input": {"min_order_usd": 10000, "include_cross_venue": True},
    },
    "security_attestation_bundle": {
        "amount_microunits": "20000",
        "price_usd": "0.02",
        "price_formatted": "0.02 USDC",
        "ppe_event_name": "security_attestation_bundle",
        "ppe_event_count": 1,
        "description": "Cryptographic prompt-safety + URL threat + token contract verification bundle for autonomous AI agent workflows.",
        "path": "/v1/security/attestation-bundle",
        "category": "security",
        "example_input": {
            "prompt_text": "Verify swap parameters for Base USDC",
            "target_url": "https://app.uniswap.org",
            "token_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        },
    },
    "research_topic_news_scanner": {
        "amount_microunits": "20000",
        "price_usd": "0.02",
        "price_formatted": "0.02 USDC",
        "ppe_event_name": "research_topic_news_scanner",
        "ppe_event_count": 1,
        "description": "Real-time sanitized news, HackerNews, and ArXiv intelligence scanner for any target keyword or protocol.",
        "path": "/v1/research/topic-news-scanner",
        "category": "research",
        "example_input": {"query": "x402 autonomous agents Base"},
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
            "endpoint": "https://canaryguard-402.onrender.com/v1/risk/full-portfolio-audit",
            "method": "POST",
            "cost": "0.02 USDC",
            "reason": "Institutional Base token & portfolio security audit with bytecode + LP lock verification",
        },
        {
            "service": "RugShield-402",
            "endpoint": "https://rugshield-402.onrender.com/v1/risk/institutional-token-report",
            "method": "POST",
            "cost": "0.02 USDC",
            "reason": "Full 7-vector token risk audit: bytecode, taxes, LP lock, whale clusters, and swap simulation",
        },
        {
            "service": "StealthGuard-402",
            "endpoint": "https://stealthguard-402.onrender.com/v1/research/deep-web-dossier",
            "method": "POST",
            "cost": "0.02 USDC",
            "reason": "Multi-source stealth web synthesis + CanaryGuard injection firewall dossier",
        },
    ],
}
