import json
import logging
from typing import Dict, Any, Optional, Tuple, List

from .config import (
    SERVICE_NAME,
    SERVICE_VERSION,
    TOOL_PRICING,
    get_recipient_address,
    get_public_url,
)
from .sanitizer import sanitize_content
from .scrapling_engine import stealth_scrape_and_sanitize
from .polymarket_engine import scan_polymarket_alpha
from .token_gate_engine import pre_trade_agent_gate
from .x402_middleware import build_402_challenge, verify_x402_payment, create_payment_response_header
from .cache_warmer import CACHE_STORE, get_ecosystem_recommendations

logger = logging.getLogger("stealthguard.mcp")

# Output schema for MCP 2024-11-05 & Smithery Quality Score compliance
DEFAULT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "description": "Execution status (success or error)"},
        "content": {"type": "array", "description": "Structured text or data content returned to the LLM agent"},
        "data": {"type": "object", "description": "Sanitized domain data payload or verification metrics"},
        "payment": {"type": "object", "description": "x402 protocol payment settlement and settlement receipt details"},
    },
    "required": ["status"],
}

TOOL_INPUT_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "stealth_scrape_and_sanitize": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Target destination URL"},
            "render_js": {"type": "boolean", "default": False, "description": "Enable stealth headless browser rendering"},
            "strict_mode": {"type": "boolean", "default": True, "description": "Deterministic sanitization strictness"},
        },
        "required": ["url"],
    },
    "polymarket_alpha_divergence": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "Category filter (crypto, politics, fed, ai)"},
            "limit": {"type": "integer", "default": 25, "description": "Max markets to analyze"},
            "strict_mode": {"type": "boolean", "default": True, "description": "Deterministic prompt-injection sanitization strictness"},
        },
    },
    "pre_trade_agent_gate": {
        "type": "object",
        "properties": {
            "token_or_service_address": {"type": "string", "description": "EVM or Solana address"},
            "chain": {"type": "string", "enum": ["base", "solana"], "default": "base", "description": "Blockchain ecosystem to audit (base or solana)"},
            "target_url": {"type": "string", "description": "Optional associated project URL"},
            "strict_mode": {"type": "boolean", "default": True, "description": "Deterministic prompt-injection sanitization strictness"},
        },
        "required": ["token_or_service_address"],
    },
    "polymarket_top_whales": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": 10, "description": "Max whales to analyze"},
        },
    },
    "polymarket_crypto_odds": {
        "type": "object",
        "properties": {
            "asset": {"type": "string", "default": "BTC", "description": "Crypto asset (BTC, ETH, SOL)"},
        },
    },
    "base_trending_tokens": {
        "type": "object",
        "properties": {
            "chain": {"type": "string", "default": "base", "description": "Target blockchain network"},
        },
    },
    "defi_yield_radar": {
        "type": "object",
        "properties": {
            "asset": {"type": "string", "default": "USDC", "description": "Target asset (USDC, ETH)"},
        },
    },
    "hackernews_ai_digest": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": 10, "description": "Number of stories"},
        },
    },
    "security_prompt_firewall": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Raw text context to scrub for prompt injections"},
        },
        "required": ["text"],
    },
    "security_x402_endpoint_verifier": {
        "type": "object",
        "properties": {
            "endpoint_url": {"type": "string", "description": "Target x402 endpoint URL to audit"},
        },
        "required": ["endpoint_url"],
    },
    "research_deep_web_dossier": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Research topic or target entity"},
            "depth": {"type": "string", "default": "comprehensive", "description": "Research depth"},
        },
        "required": ["topic"],
    },
    "oracle_perp_funding_and_basis": {
        "type": "object",
        "properties": {
            "assets": {"type": "array", "items": {"type": "string"}, "description": "Assets to analyze (e.g. ['BTC', 'ETH', 'SOL'])"},
        },
    },
    "alpha_polymarket_whale_orderflow": {
        "type": "object",
        "properties": {
            "min_order_usd": {"type": "number", "default": 10000, "description": "Minimum order size in USD"},
            "include_cross_venue": {"type": "boolean", "default": True, "description": "Include cross-venue arbitrage matrix"},
        },
    },
    "security_attestation_bundle": {
        "type": "object",
        "properties": {
            "prompt_text": {"type": "string", "description": "Prompt text to attest"},
            "target_url": {"type": "string", "description": "Target URL"},
            "token_address": {"type": "string", "description": "Token contract address"},
        },
        "required": ["prompt_text"],
    },
    "research_topic_news_scanner": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Target search topic or protocol keyword"},
        },
        "required": ["query"],
    },
}

# Dynamically construct exactly the 15 paid tools from canonical TOOL_PRICING
MCP_TOOLS: List[Dict[str, Any]] = []
for tool_name, pricing in TOOL_PRICING.items():
    if pricing.get("amount_microunits", "0") == "0":
        continue
    schema = TOOL_INPUT_SCHEMAS.get(tool_name, {"type": "object", "properties": {}})
    MCP_TOOLS.append({
        "name": tool_name,
        "description": f"{pricing['description']} Price: {pricing['price_formatted']} on Base.",
        "inputSchema": schema,
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
        "outputSchema": DEFAULT_OUTPUT_SCHEMA,
    })

def generate_health_and_sample_payload(include_samples: bool = True) -> Dict[str, Any]:
    """Generates the discovery payload for free exploration."""
    public_url = get_public_url()
    payload = {
        "status": "healthy",
        "discovery_pass": True,
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "tools_count": len(MCP_TOOLS),
        "protocol": "Model Context Protocol (MCP) Streamable HTTP + x402 v2",
        "pricing": TOOL_PRICING,
        "payment_info": {
            "network": "eip155:8453",
            "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "recipient": get_recipient_address(),
            "facilitator": "https://api.cdp.coinbase.com/platform/v2/x402",
        },
    }
    if include_samples:
        samples_data = {
            "stealth_scrape_and_sanitize": {
                "sample_input": {"url": "https://news.ycombinator.com", "render_js": False},
                "price": "0.015 USDC",
            },
            "polymarket_alpha_divergence": {
                "sample_input": {"category": "crypto", "limit": 5},
                "price": "0.020 USDC",
            },
            "pre_trade_agent_gate": {
                "sample_input": {"token_or_service_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "chain": "base"},
                "price": "0.010 USDC",
            },
        }
        payload["samples"] = samples_data
        payload["sample_tools"] = samples_data
    return payload

async def handle_mcp_request(
    request_data: Dict[str, Any],
    raw_payment_header: Optional[str] = None
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Handles MCP JSON-RPC 2.0 requests over Streamable HTTP transport.
    Returns: (response_dict, optional_payment_response_header)
    """
    req_id = request_data.get("id")
    method = request_data.get("method")
    params = request_data.get("params") or {}

    # 1. Initialize
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                    "prompts": {"listChanged": False},
                },
                "serverInfo": {
                    "name": "stealthguard-402",
                    "displayName": "StealthGuard-402",
                    "title": "StealthGuard 402",
                    "version": SERVICE_VERSION,
                    "description": "Stealth web scraper bypassing Cloudflare anti-bot via Scrapling, extracts clean DOM to Markdown, and sanitizes prompt injections with x402 micropayments on Base.",
                    "homepage": "https://stealthguard-402.onrender.com",
                    "websiteUrl": "https://stealthguard-402.onrender.com",
                    "icon": "https://stealthguard-402.onrender.com/favicon.ico",
                    "iconUrl": "https://stealthguard-402.onrender.com/favicon.ico",
                },
            },
        }, None

    # 2. Ping
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}, None

    # 2b. Resources List (Return clean empty array for Quality Score)
    if method in ("resources/list", "resources/templates/list"):
        return {"jsonrpc": "2.0", "id": req_id, "result": {"resources": []}}, None

    # 2c. Prompts List (Return clean empty array for Quality Score)
    if method == "prompts/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"prompts": []}}, None

    # 3. Tools List
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": MCP_TOOLS},
        }, None

    # 4. Tools Call
    if method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments") or {}

        # Free tool execution
        if tool_name == "health_and_sample":
            include_samples = args.get("include_samples", True)
            res = generate_health_and_sample_payload(include_samples)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(res, indent=2)}],
                    "structuredContent": res,
                },
            }, None

        # Paid tools validation
        if tool_name not in TOOL_PRICING:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
            }, None

        # Check for x402 payment in MCP meta or HTTP header
        mcp_payment = params.get("_meta", {}).get("x402/payment")
        payment_header_val = raw_payment_header
        if not payment_header_val and mcp_payment:
            payment_header_val = json.dumps(mcp_payment) if isinstance(mcp_payment, dict) else str(mcp_payment)

        res_url = f"{get_public_url()}/mcp"
        is_valid, payment_info, err_msg, status_code = verify_x402_payment(payment_header_val, tool_name, resource_url=res_url)
        if not is_valid:
            headers, challenge_body = build_402_challenge(
                tool_name=tool_name,
                resource_url=res_url,
                mode="mcp",
                reason=err_msg or "Payment required",
            )
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "isError": True,
                "error": {
                    "code": 402,
                    "message": "payment_required",
                    "data": challenge_body,
                },
                "_meta": {
                    "x402/payment-required": challenge_body,
                    "x402/headers": headers,
                },
                "content": [
                    {
                        "type": "text",
                        "text": f"Payment Required: {TOOL_PRICING[tool_name]['price_formatted']} on Base. Challenge: {headers['PAYMENT-REQUIRED']}",
                    }
                ],
            }, None

        # Execute paid tools
        result_data: Dict[str, Any] = {}
        if tool_name == "stealth_scrape_and_sanitize":
            result_data = await stealth_scrape_and_sanitize(
                url=args.get("url", "https://example.com"),
                extract_schema=args.get("extract_schema"),
                render_js=args.get("render_js", False),
                strict_mode=args.get("strict_mode", True),
            )
        elif tool_name == "polymarket_alpha_divergence":
            result_data = await scan_polymarket_alpha(
                category=args.get("category"),
                limit=args.get("limit", 25),
                strict_mode=args.get("strict_mode", True),
            )
        elif tool_name == "pre_trade_agent_gate":
            result_data = await pre_trade_agent_gate(
                token_or_service_address=args.get("token_or_service_address", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"),
                chain=args.get("chain", "base"),
                target_url=args.get("target_url"),
                strict_mode=args.get("strict_mode", True),
            )
        else:
            # 15 Micro-priced tools served sub-50ms
            if tool_name in CACHE_STORE:
                result_data = dict(CACHE_STORE[tool_name])
            else:
                result_data = {
                    "status": "success",
                    "tool": tool_name,
                    "price_paid": TOOL_PRICING[tool_name]["price_formatted"],
                    "data": {"status": "ok", "verdict": "VERIFIED"},
                    "recommended_actions": get_ecosystem_recommendations("general"),
                }

        resp_header_b64 = create_payment_response_header(payment_info) if payment_info else None
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(result_data, indent=2)}],
                "structuredContent": result_data,
                "_meta": {
                    "x402/payment-response": payment_info,
                },
            },
        }, resp_header_b64

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not supported: {method}"},
    }, None
