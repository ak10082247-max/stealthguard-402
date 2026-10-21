import os
from typing import Dict, Any

NETWORK = "eip155:8453"
CHAIN_ID = 8453
ASSET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # Base USDC
DEFAULT_RECIPIENT = "0x73279fa4BadA7CAC888c62CDa4f5c8104765f6f1"
SOLANA_NETWORK = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"
SOLANA_USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
DEFAULT_SOLANA_RECIPIENT = "3tQ4GthjUMqNsyrb1rZMocMHoNewFQWjDUvHZqWeYuCN"
SOLANA_FEE_PAYER = "CjNFTjvBhbJJd2B5ePPMHRLx1ELZpa8dwQgGL727eKww"
PAYAI_FACILITATOR_URL = "https://facilitator.payai.network"
SERVICE_NAME = "StealthGuard-402"
SERVICE_VERSION = "1.3.0"

def get_solana_recipient_address() -> str:
    return os.getenv("SOLANA_MERCHANT_ADDRESS") or DEFAULT_SOLANA_RECIPIENT

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
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target destination URL to scrape in stealth mode"},
                "render_js": {"type": "boolean", "default": False, "description": "Enable headless browser rendering for JS-heavy dApps"},
                "strict_mode": {"type": "boolean", "default": True, "description": "Deterministic prompt-injection sanitization strictness"},
            },
            "required": ["url"],
        },
        "example_output": {
            "status": "success",
            "url": "https://news.ycombinator.com",
            "title": "Hacker News",
            "content_markdown": "# Hacker News\n1. Show HN: x402 V2 Dual-Chain Autonomous Agent Protocol\n2. New advancements in LLM security...",
            "sanitized": True,
            "threats_detected": [],
            "safety_receipt": "canary-v1-verified",
            "bytes_extracted": 14200,
        },
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
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "default": "crypto", "description": "Category filter (crypto, politics, fed, ai)"},
                "limit": {"type": "integer", "default": 15, "description": "Max markets to analyze"},
                "strict_mode": {"type": "boolean", "default": True, "description": "Deterministic prompt-injection sanitization strictness"},
            },
        },
        "example_output": {
            "status": "success",
            "category": "crypto",
            "markets_scanned": 15,
            "divergence_signals": [
                {
                    "market": "Bitcoin reaches $100k before December 31",
                    "volume_usd": 8920000,
                    "clob_imbalance_bps": 215.0,
                    "whale_sentiment": "BULLISH_SKEW",
                    "divergence_score": 0.89,
                    "implied_probability": 0.78,
                },
                {
                    "market": "Ethereum gas fee average below 5 gwei",
                    "volume_usd": 3410000,
                    "clob_imbalance_bps": 180.0,
                    "whale_sentiment": "NEUTRAL",
                    "divergence_score": 0.76,
                    "implied_probability": 0.62,
                },
            ],
            "sanitized": True,
        },
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
        "input_schema": {
            "type": "object",
            "properties": {
                "token_or_service_address": {"type": "string", "description": "EVM contract address or Solana mint/account"},
                "chain": {"type": "string", "enum": ["base", "solana"], "default": "base", "description": "Target blockchain ecosystem"},
                "target_url": {"type": "string", "description": "Optional associated project or dApp URL"},
                "strict_mode": {"type": "boolean", "default": True, "description": "Deterministic prompt-injection sanitization strictness"},
            },
            "required": ["token_or_service_address"],
        },
        "example_output": {
            "status": "success",
            "token_or_service_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "chain": "base",
            "verdict": "TRUST",
            "honeypot_detected": False,
            "buy_tax_bps": 0,
            "sell_tax_bps": 0,
            "liquidity_usd": 145000,
            "risk_score": 0.0,
            "checks": {
                "honeypot": False,
                "liquidity_depth_adequate": True,
                "mev_sandwich_risk": "LOW",
                "slippage_bps_recommended": 50,
                "prompt_injection_in_metadata": False,
            },
            "safety_receipt": "canary-v1-verified",
        },
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
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 10, "description": "Max whales to analyze"},
            },
        },
        "example_output": {
            "status": "success",
            "feed": "polymarket_top_whales",
            "latency_mode": "memory_prewarmed_sub_50ms",
            "top_whales": [
                {
                    "market": "Fed cuts 25bps in upcoming FOMC meeting",
                    "volume_usd": 12450000,
                    "clob_imbalance_bps": 312.0,
                    "whale_sentiment": "BULLISH_SKEW",
                    "divergence_score": 0.94,
                },
                {
                    "market": "Bitcoin reaches $100k before December 31",
                    "volume_usd": 8920000,
                    "clob_imbalance_bps": 215.0,
                    "whale_sentiment": "BULLISH_SKEW",
                    "divergence_score": 0.89,
                },
            ],
        },
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
        "input_schema": {
            "type": "object",
            "properties": {
                "asset": {"type": "string", "default": "BTC", "description": "Crypto asset symbol (BTC, ETH, SOL)"},
            },
        },
        "example_output": {
            "status": "success",
            "feed": "polymarket_crypto_odds",
            "pairs": [
                {"asset": "BTC", "target": ">$100,000", "implied_prob": 0.78, "spread_bps": 12, "clob_depth_usd": 1540000},
                {"asset": "ETH", "target": ">$3,500", "implied_prob": 0.62, "spread_bps": 18, "clob_depth_usd": 890000},
                {"asset": "SOL", "target": ">$220", "implied_prob": 0.71, "spread_bps": 15, "clob_depth_usd": 920000},
            ],
        },
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
        "input_schema": {
            "type": "object",
            "properties": {
                "chain": {"type": "string", "default": "base", "description": "Target blockchain network"},
            },
        },
        "example_output": {
            "status": "success",
            "network": "base",
            "chain_id": 8453,
            "trending_tokens": [
                {"symbol": "USDC", "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "liquidity_usd": 450000000, "honeypot": False, "verdict": "SAFE"},
                {"symbol": "WETH", "address": "0x4200000000000000000000000000000000000006", "liquidity_usd": 280000000, "honeypot": False, "verdict": "SAFE"},
            ],
        },
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
        "input_schema": {
            "type": "object",
            "properties": {
                "asset": {"type": "string", "default": "USDC", "description": "Target asset (USDC, ETH)"},
            },
        },
        "example_output": {
            "status": "success",
            "asset": "USDC",
            "yields": [
                {"protocol": "Aave V3 Base", "pool": "USDC", "supply_apy": 0.052, "tvl_usd": 185000000, "risk_grade": "A"},
                {"protocol": "Aerodrome", "pool": "USDC-USDbC", "lp_apr": 0.084, "tvl_usd": 42000000, "risk_grade": "A-"},
            ],
        },
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
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 10, "description": "Number of stories"},
            },
        },
        "example_output": {
            "status": "success",
            "source": "HackerNews",
            "stories_count": 10,
            "stories": [
                {"title": "Autonomous Agent Payment Standards on L2", "url": "https://news.ycombinator.com/item?id=40201", "score": 342, "sanitized": True},
                {"title": "Deterministic Prompt Firewalls in Production", "url": "https://news.ycombinator.com/item?id=40202", "score": 218, "sanitized": True},
            ],
        },
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
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Raw text context to scrub for prompt injections"},
            },
            "required": ["text"],
        },
        "example_output": {
            "status": "success",
            "tool": "security_prompt_firewall",
            "threat_level": "CLEAN",
            "sanitized_text": "Sample verified agent context",
            "verdict": "SAFE_TO_PERSIST",
            "canaryguard_meta": {"risk_score": 0.0, "injection_detected": False, "safety_receipt": "canary-v1-verified"},
        },
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
        "input_schema": {
            "type": "object",
            "properties": {
                "endpoint_url": {"type": "string", "description": "Target x402 endpoint URL to audit"},
            },
            "required": ["endpoint_url"],
        },
        "example_output": {
            "status": "success",
            "audited_url": "https://stealthguard-402.onrender.com/v1/stealth_scrape_and_sanitize",
            "verdict": "AUTHENTIC_X402_PROVIDER",
            "settlement_safe": True,
            "verified_recipient": "0x73279fa4BadA7CAC888c62CDa4f5c8104765f6f1",
            "pricing_verified": "0.015 USDC",
        },
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
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Research topic or target entity"},
                "depth": {"type": "string", "default": "comprehensive", "description": "Research depth (summary, comprehensive, technical)"},
            },
            "required": ["topic"],
        },
        "example_output": {
            "status": "success",
            "topic": "Base L2 autonomous AI agent economy and x402 protocol adoption",
            "depth": "comprehensive",
            "dossier_markdown": "# Intelligence Dossier: Base L2 Agentic Economy\n\n## Key Protocols\n- x402 V2 dual-chain payment settlement...\n## Market Depth & Autonomous Volume...",
            "sources_audited": 8,
            "injection_threats_scrubbed": 0,
            "verdict": "VERIFIED_INTELLIGENCE",
        },
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
        "input_schema": {
            "type": "object",
            "properties": {
                "assets": {"type": "array", "items": {"type": "string"}, "description": "Assets to analyze (e.g. ['BTC', 'ETH', 'SOL'])"},
            },
        },
        "example_output": {
            "status": "success",
            "oracle": "perp_funding_and_basis",
            "timestamp": 1740000000,
            "rates": [
                {"asset": "BTC", "funding_rate_8h": 0.0001, "annualized_basis_pct": 10.95, "skew": "LONG_BIAS", "arbitrage_bps": 8.5},
                {"asset": "ETH", "funding_rate_8h": 0.00008, "annualized_basis_pct": 8.76, "skew": "NEUTRAL", "arbitrage_bps": 6.2},
            ],
        },
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
        "input_schema": {
            "type": "object",
            "properties": {
                "min_order_usd": {"type": "number", "default": 10000, "description": "Minimum order size in USD to track"},
                "include_cross_venue": {"type": "boolean", "default": True, "description": "Include cross-venue arbitrage matrix"},
            },
        },
        "example_output": {
            "status": "success",
            "feed": "polymarket_whale_orderflow",
            "order_filter_usd": 10000,
            "large_orders": [
                {"market": "US Presidential Election 2028", "side": "BUY", "size_usd": 48500, "price": 0.54, "whale_cluster": "0x9a...b4"},
                {"market": "Fed cuts rate 50bps in Q1", "side": "SELL", "size_usd": 32000, "price": 0.18, "whale_cluster": "0x3f...12"},
            ],
            "cross_venue_spread_bps": 45,
        },
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
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt_text": {"type": "string", "description": "Prompt text to attest for prompt safety"},
                "target_url": {"type": "string", "description": "Target dApp or contract URL to screen"},
                "token_address": {"type": "string", "description": "Token contract address on Base or Solana"},
            },
            "required": ["prompt_text"],
        },
        "example_output": {
            "status": "success",
            "verdict": "TRUST",
            "honeypot_detected": False,
            "buy_tax_bps": 0,
            "sell_tax_bps": 0,
            "liquidity_usd": 145000,
            "attestation": {
                "prompt_safety": {"risk_score": 0.0, "verdict": "SAFE"},
                "domain_safety": {"url": "https://app.uniswap.org", "verdict": "SAFE_DOMAIN"},
                "contract_safety": {"address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "verdict": "VERIFIED_SAFE_CONTRACT"},
            },
            "composite_verdict": "ALL_CLEAR",
            "safety_receipt": "canary-v1-verified",
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
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Target search topic or protocol keyword"},
            },
            "required": ["query"],
        },
        "example_output": {
            "status": "success",
            "query": "x402 autonomous agents Base",
            "news_count": 5,
            "items": [
                {"title": "x402 protocol enables gasless micropayments for AI agents on Base", "source": "CryptoSlate", "sentiment": "POSITIVE"},
                {"title": "Autonomous agent economies expand on Layer 2 networks", "source": "CoinDesk", "sentiment": "BULLISH"},
            ],
            "sanitized": True,
        },
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
        "example_input": {},
        "input_schema": {"type": "object", "properties": {}},
        "example_output": {"status": "ok", "service": "StealthGuard-402", "uptime": "100%"},
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
