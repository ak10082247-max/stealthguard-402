import json
import logging
import time
import uuid
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from .config import (
    SERVICE_NAME,
    SERVICE_VERSION,
    NETWORK,
    CHAIN_ID,
    ASSET,
    TOOL_PRICING,
    get_recipient_address,
    get_public_url,
)
from .sanitizer import sanitize_content
from .scrapling_engine import stealth_scrape_and_sanitize
from .polymarket_engine import scan_polymarket_alpha
from .token_gate_engine import pre_trade_agent_gate
from .x402_middleware import (
    build_402_challenge,
    verify_x402_payment,
    create_payment_response_header,
    build_bazaar_extension,
)
from .mcp_server import handle_mcp_request, generate_health_and_sample_payload

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("stealthguard.api")

app = FastAPI(
    title="StealthGuard-402",
    description="Stealth web extraction and prediction-market/on-chain alpha fused with CanaryGuard prompt-injection firewall. Monetized via Base x402 and Apify PPE.",
    version=SERVICE_VERSION,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=[
        "Content-Type", "Accept", "Authorization", "X-PAYMENT", "PAYMENT-SIGNATURE",
        "X-402-Version", "MCP-Protocol-Version", "Mcp-Session-Id"
    ],
    expose_headers=[
        "WWW-Authenticate", "X-PAYMENT", "PAYMENT-SIGNATURE", "X-402-Version",
        "PAYMENT-REQUIRED", "X-Payment-Required", "X-402-Payment-Required",
        "PAYMENT-RESPONSE", "X-402-Payment-To", "X-402-Amount", "X-402-Amount-Units",
        "X-402-Asset", "X-402-Network", "X-402-Chain-Id", "X-Request-Id"
    ],
)

@app.middleware("http")
async def request_logger_and_header_middleware(request: Request, call_next):
    start = time.time()
    req_id = str(uuid.uuid4())[:8]
    response: Response = await call_next(request)
    duration_ms = int((time.time() - start) * 1000)
    response.headers["X-Request-Id"] = req_id
    response.headers["X-402-Version"] = "2"

    if request.url.path != "/health":
        settled = "PAYMENT-RESPONSE" in response.headers
        logger.info(
            f"reqId={req_id} method={request.method} path={request.url.path} "
            f"status={response.status_code} duration={duration_ms}ms settled={settled}"
        )
    return response

# Pydantic Request Models
class StealthScrapeRequest(BaseModel):
    url: str = Field(..., description="Target URL to fetch")
    extract_schema: Optional[Dict[str, Any]] = Field(None, description="Optional structured JSON extraction schema")
    render_js: bool = Field(False, description="Whether to trigger headless stealth browser rendering")
    strict_mode: bool = Field(True, description="CanaryGuard prompt-injection strictness")

class PolymarketAlphaRequest(BaseModel):
    category: Optional[str] = Field(None, description="Category filter (e.g., crypto, politics)")
    limit: int = Field(25, ge=1, le=50, description="Max markets to analyze")
    strict_mode: bool = Field(True, description="CanaryGuard prompt-injection strictness")

class PreTradeGateRequest(BaseModel):
    token_or_service_address: str = Field(..., description="EVM or Solana address")
    chain: str = Field("base", description="base or solana")
    target_url: Optional[str] = Field(None, description="Optional associated website URL")
    strict_mode: bool = Field(True, description="CanaryGuard prompt-injection strictness")

# 1. Health & Discovery
@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME, "version": SERVICE_VERSION}

@app.get("/stats")
async def stats():
    return {
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "network": NETWORK,
        "chainId": CHAIN_ID,
        "asset": ASSET,
        "recipient": get_recipient_address(),
        "pricing": TOOL_PRICING,
        "limits": {
            "max_scrape_timeout_seconds": 30,
            "max_polymarket_markets": 50,
            "idempotency_cache": "24h LRU replay prevention",
        },
    }

@app.get("/llms.txt", response_class=PlainTextResponse)
async def llms_txt():
    return f"""# {SERVICE_NAME}
Production-ready stealth web extraction, prediction-market alpha, and on-chain pre-trade gating fused with CanaryGuard prompt-injection firewall.

## Endpoints:
- POST /v1/stealth_scrape_and_sanitize: 0.02 USDC on Base (1 Apify PPE event)
- POST /v1/polymarket_alpha_divergence: 0.05 USDC on Base (2 Apify PPE events)
- POST /v1/pre_trade_agent_gate: 0.03 USDC on Base (1 Apify PPE event)
- GET /v1/health_and_sample: 0.00 USDC (Free Discovery)
- POST /mcp: Streamable HTTP Model Context Protocol JSON-RPC

Settlement Asset: Base USDC (0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913)
Payee Wallet: {get_recipient_address()}
"""

@app.get("/")
async def root():
    public_url = get_public_url()
    return {
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "manifest": f"{public_url}/.well-known/x402.json",
        "health": f"{public_url}/health",
        "stats": f"{public_url}/stats",
        "mcp": f"{public_url}/mcp",
        "free_sample": f"{public_url}/v1/health_and_sample",
        "paid_tools": [
            f"POST {public_url}/v1/stealth_scrape_and_sanitize",
            f"POST {public_url}/v1/polymarket_alpha_divergence",
            f"POST {public_url}/v1/pre_trade_agent_gate",
        ],
    }

# 2. x402 Manifest and OpenAPI
@app.get("/.well-known/x402")
@app.get("/.well-known/x402.json")
async def x402_manifest():
    public_url = get_public_url()
    pay_to = get_recipient_address()
    endpoints = []
    for tool_name, pricing in TOOL_PRICING.items():
        if pricing["amount_microunits"] != "0":
            endpoints.append({
                "method": "POST",
                "url": f"{public_url}{pricing['path']}",
                "price": pricing["price_formatted"],
                "amount": pricing["amount_microunits"],
                "extensions": build_bazaar_extension(tool_name, pricing["description"], mode="http"),
            })

    return {
        "name": SERVICE_NAME,
        "description": "High-margin stealth web extraction and prediction-market/on-chain alpha with CanaryGuard prompt-injection firewall.",
        "version": SERVICE_VERSION,
        "x402Version": 2,
        "facilitator": "https://api.cdp.coinbase.com/platform/mobile/x402",
        "payment_recipient": pay_to,
        "accepted_tokens": [ASSET],
        "pricing": {
            "asset": ASSET,
            "network": NETWORK,
            "chainId": CHAIN_ID,
            "payTo": pay_to,
            "tools": TOOL_PRICING,
        },
        "endpoints": endpoints,
        "mcp": {
            "url": f"{public_url}/mcp",
            "transport": "streamable-http",
            "tools": list(TOOL_PRICING.keys()),
        },
    }

@app.get("/openapi.json")
@app.get("/.well-known/openapi.json")
async def openapi_spec():
    return app.openapi()

# 3. Free Discovery Tool
@app.get("/v1/health_and_sample")
@app.post("/v1/health_and_sample")
async def health_and_sample(include_samples: bool = True):
    return generate_health_and_sample_payload(include_samples)

# 4. Paid Tool 1: stealth_scrape_and_sanitize
@app.post("/v1/stealth_scrape_and_sanitize")
async def stealth_scrape_endpoint(req: StealthScrapeRequest, request: Request):
    tool_name = "stealth_scrape_and_sanitize"
    payment_header = request.headers.get("PAYMENT-SIGNATURE") or request.headers.get("X-PAYMENT")

    is_valid, payment_info, err_msg, status_code = verify_x402_payment(payment_header, tool_name)
    if not is_valid:
        headers, challenge_body = build_402_challenge(
            tool_name=tool_name,
            resource_url=str(request.url),
            mode="http",
            reason=err_msg,
            input_schema={"url": "string", "extract_schema": "object", "render_js": "boolean"},
            example_input={"url": req.url, "render_js": req.render_js},
        )
        return JSONResponse(status_code=status_code, content=challenge_body, headers=headers)

    result = await stealth_scrape_and_sanitize(
        url=req.url,
        extract_schema=req.extract_schema,
        render_js=req.render_js,
        strict_mode=req.strict_mode,
    )

    response_headers = {}
    if payment_info:
        response_headers["PAYMENT-RESPONSE"] = create_payment_response_header(payment_info)

    return JSONResponse(content=result, headers=response_headers)

# 5. Paid Tool 2: polymarket_alpha_divergence
@app.post("/v1/polymarket_alpha_divergence")
async def polymarket_alpha_endpoint(req: PolymarketAlphaRequest, request: Request):
    tool_name = "polymarket_alpha_divergence"
    payment_header = request.headers.get("PAYMENT-SIGNATURE") or request.headers.get("X-PAYMENT")

    is_valid, payment_info, err_msg, status_code = verify_x402_payment(payment_header, tool_name)
    if not is_valid:
        headers, challenge_body = build_402_challenge(
            tool_name=tool_name,
            resource_url=str(request.url),
            mode="http",
            reason=err_msg,
            input_schema={"category": "string", "limit": "integer"},
            example_input={"category": req.category, "limit": req.limit},
        )
        return JSONResponse(status_code=status_code, content=challenge_body, headers=headers)

    result = await scan_polymarket_alpha(
        category=req.category,
        limit=req.limit,
        strict_mode=req.strict_mode,
    )

    response_headers = {}
    if payment_info:
        response_headers["PAYMENT-RESPONSE"] = create_payment_response_header(payment_info)

    return JSONResponse(content=result, headers=response_headers)

# 6. Paid Tool 3: pre_trade_agent_gate
@app.post("/v1/pre_trade_agent_gate")
async def pre_trade_gate_endpoint(req: PreTradeGateRequest, request: Request):
    tool_name = "pre_trade_agent_gate"
    payment_header = request.headers.get("PAYMENT-SIGNATURE") or request.headers.get("X-PAYMENT")

    is_valid, payment_info, err_msg, status_code = verify_x402_payment(payment_header, tool_name)
    if not is_valid:
        headers, challenge_body = build_402_challenge(
            tool_name=tool_name,
            resource_url=str(request.url),
            mode="http",
            reason=err_msg,
            input_schema={"token_or_service_address": "string", "chain": "string", "target_url": "string"},
            example_input={"token_or_service_address": req.token_or_service_address, "chain": req.chain},
        )
        return JSONResponse(status_code=status_code, content=challenge_body, headers=headers)

    result = await pre_trade_agent_gate(
        token_or_service_address=req.token_or_service_address,
        chain=req.chain,
        target_url=req.target_url,
        strict_mode=req.strict_mode,
    )

    response_headers = {}
    if payment_info:
        response_headers["PAYMENT-RESPONSE"] = create_payment_response_header(payment_info)

    return JSONResponse(content=result, headers=response_headers)

# 7. MCP Streamable HTTP JSON-RPC endpoint
@app.post("/mcp")
async def mcp_post(request: Request):
    raw_payment_header = request.headers.get("PAYMENT-SIGNATURE") or request.headers.get("X-PAYMENT")
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error: Invalid JSON"}}
        )

    response_data, payment_response_hdr = await handle_mcp_request(body, raw_payment_header)
    headers = {}
    if payment_response_hdr:
        headers["PAYMENT-RESPONSE"] = payment_response_hdr

    return JSONResponse(content=response_data, headers=headers)

@app.api_route("/mcp", methods=["GET", "PUT", "DELETE", "PATCH"])
async def mcp_other_methods():
    raise HTTPException(status_code=405, detail="Method Not Allowed: MCP endpoint requires POST")
