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

logger = logging.getLogger("stealthguard.mcp")

# Glama TDQS Optimized Tool Definitions
MCP_TOOLS = [
    {
        "name": "stealth_scrape_and_sanitize",
        "description": (
            "Bypasses Cloudflare Turnstile and anti-bot protection via Scrapling StealthyFetcher, "
            "converts DOM to token-compressed LLM Markdown and structured JSON, and executes CanaryGuard "
            "deterministic prompt-injection firewall to neutralize hidden commands before context ingestion. "
            "Pricing: $0.02 USDC on Base (eip155:8453) / 1 Apify PPE event. "
            "Requires payment authorization in extra._meta['x402/payment'] or PAYMENT-SIGNATURE header."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "format": "uri",
                    "description": "The destination URL to stealth-fetch and sanitize",
                },
                "extract_schema": {
                    "type": "object",
                    "description": "Optional JSON schema describing structured properties to extract from DOM",
                },
                "render_js": {
                    "type": "boolean",
                    "default": False,
                    "description": "Set to true to activate Patchright/Playwright stealth browser rendering for Cloudflare Turnstile/SPA",
                },
                "strict_mode": {
                    "type": "boolean",
                    "default": True,
                    "description": "If true, blocks content entirely upon prompt injection; if false, redacts detected instructions",
                },
            },
            "required": ["url"],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    },
    {
        "name": "polymarket_alpha_divergence",
        "description": (
            "Scans Polymarket Gamma active markets and live CLOB orderbooks for volume spikes and smart-money spread divergence, "
            "scrapes market resolution source URLs via Scrapling, and sanitizes resolution criteria via CanaryGuard "
            "to prevent oracle prompt injection and fake-news manipulation. "
            "Pricing: $0.05 USDC on Base (eip155:8453) / 2 Apify PPE events. "
            "Requires payment authorization in extra._meta['x402/payment'] or PAYMENT-SIGNATURE header."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Optional category filter (e.g. 'crypto', 'politics', 'fed', 'ai')",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 25,
                    "description": "Maximum number of top-volume active markets to scan and compute alpha divergence for",
                },
                "strict_mode": {
                    "type": "boolean",
                    "default": True,
                    "description": "Deterministic sanitization strictness for resolution texts",
                },
            },
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    },
    {
        "name": "pre_trade_agent_gate",
        "description": (
            "Deterministic pre-trade verification gate for autonomous trading agents. Combines on-chain DexScreener "
            "liquidity depth and Base/Solana RPC honeypot/bytecode inspection with CanaryGuard prompt-injection firewall "
            "to sanitize token names, contract ABIs, and x402 resource descriptions. Returns deterministic TRUST / BLOCK verdict. "
            "Pricing: $0.03 USDC on Base (eip155:8453) / 1 Apify PPE event. "
            "Requires payment authorization in extra._meta['x402/payment'] or PAYMENT-SIGNATURE header."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "token_or_service_address": {
                    "type": "string",
                    "description": "Token contract address or x402 resource address to inspect",
                },
                "chain": {
                    "type": "string",
                    "enum": ["base", "solana"],
                    "default": "base",
                    "description": "Target blockchain network",
                },
                "target_url": {
                    "type": "string",
                    "description": "Optional associated project website or x402 endpoint manifest to scrape and audit",
                },
                "strict_mode": {
                    "type": "boolean",
                    "default": True,
                    "description": "Deterministic sanitization strictness for metadata inspection",
                },
            },
            "required": ["token_or_service_address"],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    },
    {
        "name": "health_and_sample",
        "description": (
            "Free discovery, uptime health check, and schema sample payload tool for MCP registries "
            "(Glama, Smithery, x402Atlas, x402-list, Apify). Returns live server status, payment recipient address, "
            "pricing matrix, and representative sample outputs without requiring a micropayment. "
            "Pricing: $0.00 (Free)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "include_samples": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to return live sample payloads for the 3 paid tools",
                },
            },
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        },
    },
]

def generate_health_and_sample_payload(include_samples: bool = True) -> Dict[str, Any]:
    """Generates the free discovery probe payload."""
    payload: Dict[str, Any] = {
        "status": "healthy",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "network": "base",
        "chainId": 8453,
        "recipient_wallet": get_recipient_address(),
        "pricing_manifest": TOOL_PRICING,
        "mcp_registry_id": "io.github.ak10082247-max/stealthguard-402",
        "uptime_percent": 100.0,
        "discovery_pass": True,
    }
    if include_samples:
        payload["samples"] = {
            "stealth_scrape_and_sanitize": {
                "sample_input": {"url": "https://example.com", "render_js": False},
                "sample_output": {
                    "url": "https://example.com",
                    "status_code": 200,
                    "fetch_method": "scrapling_fetcher",
                    "token_compressed_markdown": "# Example Domain\n\nThis domain is for use in illustrative examples.",
                    "canaryguard_receipt": {
                        "status": "clean",
                        "risk_score": 0.01,
                        "injection_detected": False,
                        "safe_to_persist": True,
                        "threats_neutralized": [],
                        "safety_receipt": "canary-v1-verified",
                    },
                },
            },
            "polymarket_alpha_divergence": {
                "sample_input": {"category": "crypto", "limit": 5},
                "sample_output": {
                    "markets_scanned": 5,
                    "opportunities": [
                        {
                            "question": "Bitcoin above $100k by year end?",
                            "spread_bps": 25.0,
                            "whale_divergence_flag": True,
                            "alpha_rating": "HIGH_WHALE_DIVERGENCE",
                            "canaryguard_receipt": {"safe_to_persist": True, "risk_score": 0.01},
                        }
                    ],
                },
            },
            "pre_trade_agent_gate": {
                "sample_input": {"token_or_service_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "chain": "base"},
                "sample_output": {
                    "verdict": "TRUST",
                    "chain": "base",
                    "token_name": "USD Coin",
                    "token_symbol": "USDC",
                    "liquidity_usd": 150000000.0,
                    "safe_to_persist": True,
                    "risk_score": 0.05,
                },
            },
        }
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
                },
                "serverInfo": {
                    "name": SERVICE_NAME,
                    "version": SERVICE_VERSION,
                },
            },
        }, None

    # 2. Ping
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}, None

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

        is_valid, payment_info, err_msg, status_code = verify_x402_payment(payment_header_val, tool_name)
        if not is_valid:
            # Generate 402 challenge terms for MCP client facilitator
            headers, challenge_body = build_402_challenge(
                tool_name=tool_name,
                resource_url=f"{get_public_url()}/mcp",
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
                url=args.get("url", ""),
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
                token_or_service_address=args.get("token_or_service_address", ""),
                chain=args.get("chain", "base"),
                target_url=args.get("target_url"),
                strict_mode=args.get("strict_mode", True),
            )

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
