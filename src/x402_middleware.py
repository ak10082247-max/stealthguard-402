import base64
import hashlib
import json
import logging
import os
import re
import secrets
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple
from eth_account import Account
from eth_account.messages import encode_typed_data
import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


_BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _base58(raw):
    number = int.from_bytes(raw, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = _BASE58[remainder] + encoded
    return "1" * (len(raw)-len(raw.lstrip(b"\0"))) + encoded


def _solana_buyer(serialized):
    if serialized[0] != 2 or len(serialized) <= 166:
        raise ValueError("Expected the advertised two-signer sponsored transaction")
    message = serialized[129:]
    if message[0] != 0x80 or message[1] != 2:
        raise ValueError("Expected a two-signer Solana v0 message")
    offset, count, shift = 4, 0, 0
    while True:
        if offset >= len(message) or shift > 14:
            raise ValueError("Invalid Solana account vector")
        byte = message[offset]
        offset += 1
        count |= (byte & 127) << shift
        if not byte & 128:
            break
        shift += 7
    if count < 2 or count > 64 or len(message) < offset + count*32 + 34:
        raise ValueError("Invalid Solana account layout")
    sponsor, buyer = message[offset:offset+32], message[offset+32:offset+64]
    if _base58(sponsor) != SOLANA_FEE_PAYER:
        raise ValueError("Unexpected Solana sponsor")
    try:
        Ed25519PublicKey.from_public_bytes(buyer).verify(serialized[65:129], message)
    except Exception as exc:
        raise ValueError("Invalid Solana buyer signature") from exc
    return _base58(buyer)

def enforce_https(url: str) -> str:
    """Enforces https:// on URLs in production or hosted on Render."""
    if not url:
        return url
    if url.startswith("http://") and ("onrender.com" in url or not ("localhost" in url or "127.0.0.1" in url or "test" in url)):
        return "https://" + url[7:]
    return url

def build_ietf_mpp_www_authenticate(amount_units: str, recipient: str, realm: str = "stealthguard-402.onrender.com") -> str:
    """
    Constructs an IETF MPP compliant WWW-Authenticate header:
    WWW-Authenticate: Payment id="<uuid>", realm="stealthguard-402.onrender.com", method="evm", intent="charge", request="<base64url_no_pad_json>", expires="<iso8601_utc_plus_5m>"
    """
    challenge_id = str(uuid.uuid4())
    req_dict = {
        "amount": str(amount_units),
        "chainId": CHAIN_ID,
        "currency": ASSET,
        "decimals": 6,
        "recipient": recipient,
    }
    canonical_json = json.dumps(req_dict, separators=(",", ":"), sort_keys=True)
    req_b64url = base64.urlsafe_b64encode(canonical_json.encode("utf-8")).decode("utf-8").rstrip("=")
    expires = (datetime.now(timezone.utc) + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f'Payment id="{challenge_id}", realm="{realm}", method="evm", intent="charge", request="{req_b64url}", expires="{expires}"'


from .config import (
    NETWORK,
    CHAIN_ID,
    ASSET,
    SERVICE_NAME,
    TOOL_PRICING,
    get_recipient_address,
    get_public_url,
    SOLANA_NETWORK,
    SOLANA_USDC_MINT,
    SOLANA_FEE_PAYER,
    PAYAI_FACILITATOR_URL,
    get_solana_recipient_address,
)

logger = logging.getLogger("stealthguard.x402")

COINBASE_FACILITATOR_BASE_URL = "https://api.cdp.coinbase.com"
COINBASE_FACILITATOR_V2_ROUTE = "/platform/v2/x402"
CDP_SDK_VERSION = "1.29.0"
X402_SDK_VERSION = "2.1.0"

# In-memory replay cache: signature_hash -> expiry_timestamp
REPLAY_CACHE: Dict[str, float] = {}

def clean_replay_cache():
    now = time.time()
    expired = [k for k, exp in REPLAY_CACHE.items() if exp <= now]
    for k in expired:
        del REPLAY_CACHE[k]

def clean_pem_private_key(raw_key: str) -> str:
    """Robustly cleans and normalizes a PEM private key from environment variables or files."""
    if not raw_key:
        return ""
    k = raw_key.strip().strip('"').strip("'")
    k = k.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\r", "")
    
    match = re.search(r"-----BEGIN ((?:EC )?PRIVATE KEY)-----\s*(.*?)\s*-----END (?:EC )?PRIVATE KEY-----", k, re.DOTALL)
    if match:
        key_type = match.group(1)
        body = "".join(match.group(2).split())
        lines = [body[i:i+64] for i in range(0, len(body), 64)]
        return f"-----BEGIN {key_type}-----\n" + "\n".join(lines) + f"\n-----END {key_type}-----\n"
    
    if not k.endswith("\n"):
        k += "\n"
    return k

def load_cdp_credentials() -> Tuple[Optional[str], Optional[str]]:
    """Use only explicitly configured credentials; never search neighbors or Downloads."""
    key_id = os.getenv("CDP_API_KEY_NAME") or os.getenv("CDP_API_KEY_ID")
    secret = os.getenv("CDP_API_KEY_PRIVATE_KEY") or os.getenv("CDP_API_KEY_SECRET")
    return (key_id.strip().strip('"').strip("'") if key_id else None,
            clean_pem_private_key(secret) if secret else None)


def generate_cdp_jwt(key_id: str, private_key: str, method: str, host: str, path: str) -> str:
    """Generates an ES256-signed JWT for Coinbase CDP Facilitator authentication."""
    now = int(time.time())
    uri_str = f"{method.upper()} {host}{path}"
    payload = {
        "sub": key_id,
        "iss": "cdp",
        "aud": ["cdp_service"],
        "nbf": now,
        "exp": now + 120,
        "uri": uri_str,
        "uris": [uri_str],
    }
    headers = {
        "alg": "ES256",
        "kid": key_id,
        "typ": "JWT",
        "nonce": secrets.token_hex(16),
    }
    clean_key = clean_pem_private_key(private_key)
    return jwt.encode(payload, clean_key, algorithm="ES256", headers=headers)

def verify_via_cdp_facilitator(
    payment_payload: Dict[str, Any],
    payment_requirements: Dict[str, Any]
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """Calls POST /platform/v2/x402/verify on Coinbase CDP Facilitator."""
    key_id, key_secret = load_cdp_credentials()
    if not key_id or not key_secret:
        return False, None, "CDP verification credentials are not configured"

    host = "api.cdp.coinbase.com"
    path = f"{COINBASE_FACILITATOR_V2_ROUTE}/verify"
    url = f"{COINBASE_FACILITATOR_BASE_URL}{path}"

    try:
        token = generate_cdp_jwt(key_id, key_secret, "POST", host, path)
        headers = {
            "Authorization": f"Bearer {token}",
            "Correlation-Context": f"sdk_version={CDP_SDK_VERSION},sdk_language=python,source=x402,source_version={X402_SDK_VERSION}",
            "Content-Type": "application/json",
        }
        body = {
            "x402Version": payment_payload.get("x402Version", 2),
            "paymentPayload": payment_payload,
            "paymentRequirements": payment_requirements,
        }

        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=body, headers=headers)
            try:
                res_data = resp.json()
            except Exception:
                res_data = {"error": resp.text}

            if resp.status_code == 200 and (res_data.get("isValid") or res_data.get("valid")):
                return True, res_data, None
            else:
                err = res_data.get("invalidReason") or res_data.get("errorMessage") or res_data.get("error") or f"HTTP {resp.status_code}"
                return False, None, str(err)
    except Exception as e:
        logger.warning(f"CDP verify error: {e}")
        return False, None, "CDP verification is unavailable"

def _settle_via_payai_facilitator(
    payment_payload: Dict[str, Any],
    payment_requirements: Dict[str, Any]
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """Settle directly through PayAI; no dependency on another merchant endpoint."""
    try:
        relay_url = f"{PAYAI_FACILITATOR_URL}/settle"
        with httpx.Client(timeout=35.0) as client:
            r = client.post(
                relay_url,
                json={"x402Version": 2, "paymentPayload": payment_payload, "paymentRequirements": payment_requirements},
            )
            try:
                res_data = r.json()
            except Exception:
                res_data = {"error": r.text}
            if r.status_code == 200 and res_data.get("success") is True:
                logger.info(
                    f"CDP Relay settled successfully on-chain! "
                    f"tx={res_data.get('transaction')} payer={res_data.get('payer')}"
                )
                return True, res_data, None
            err = res_data.get("errorReason") or res_data.get("errorMessage") or res_data.get("error") or f"Relay HTTP {r.status_code}"
            if r.status_code >= 500 or r.status_code == 200 or res_data.get("transaction"):
                return False, res_data, f"SETTLEMENT_UNKNOWN: {err}"
            return False, None, str(err)
    except Exception as e:
        return False, None, f"SETTLEMENT_UNKNOWN: CDP settlement relay exception: {type(e).__name__}"

def settle_via_cdp_facilitator(
    payment_payload: Dict[str, Any],
    payment_requirements: Dict[str, Any]
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Submits an EIP-3009 transfer authorization to the Coinbase CDP Facilitator /settle
    endpoint to broadcast on-chain on Base Mainnet (eip155:8453).
    Use PayAI when CDP credentials/JWT are unavailable before any settlement submission.
    """
    key_id, key_secret = load_cdp_credentials()
    if not key_id or not key_secret:
        return _settle_via_payai_facilitator(payment_payload, payment_requirements)

    host = "api.cdp.coinbase.com"
    path = f"{COINBASE_FACILITATOR_V2_ROUTE}/settle"
    url = f"{COINBASE_FACILITATOR_BASE_URL}{path}"

    try:
        token = generate_cdp_jwt(key_id, key_secret, "POST", host, path)
    except Exception:
        return _settle_via_payai_facilitator(payment_payload, payment_requirements)
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Correlation-Context": f"sdk_version={CDP_SDK_VERSION},sdk_language=python,source=x402,source_version={X402_SDK_VERSION}",
            "Content-Type": "application/json",
        }
        body = {
            "x402Version": payment_payload.get("x402Version", 2),
            "paymentPayload": payment_payload,
            "paymentRequirements": payment_requirements,
        }

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=body, headers=headers)
            try:
                res_data = resp.json()
            except Exception:
                res_data = {"error": resp.text}

            if resp.status_code == 200 and res_data.get("success") is True:
                ext_resp = resp.headers.get("EXTENSION-RESPONSES")
                if ext_resp:
                    try:
                        ext_json = json.loads(base64.b64decode(ext_resp).decode("utf-8"))
                        logger.info(f"CDP Facilitator EXTENSION-RESPONSES: {ext_json}")
                        res_data["extension_responses"] = ext_json
                    except Exception as e:
                        logger.debug(f"Failed decoding EXTENSION-RESPONSES: {e}")
                logger.info(
                    f"CDP Facilitator settled successfully on-chain! "
                    f"tx={res_data.get('transaction')} payer={res_data.get('payer')} network={res_data.get('network')}"
                )
                return True, res_data, None
            else:
                # A timeout, malformed response or server error may follow a broadcast.
                # Never submit that authorization to a second settler automatically.
                err = res_data.get("errorReason") or res_data.get("errorMessage") or f"HTTP {resp.status_code}"
                if resp.status_code >= 500 or resp.status_code == 200 or res_data.get("transaction"):
                    return False, res_data, f"SETTLEMENT_UNKNOWN: {err}"
                return False, None, str(err)
    except Exception as e:
        return False, None, f"SETTLEMENT_UNKNOWN: CDP settlement exception: {type(e).__name__}"

def build_bazaar_extension(
    tool_name: str,
    description: str = "",
    mode: str = "http",
    input_schema: Optional[Dict[str, Any]] = None,
    example_input: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Implements the exact JSON structure of declareDiscoveryExtension from @x402/extensions/bazaar
    so x402 facilitators, Coinbase Bazaar, and vet402.com L1/L2 output verifiers pass 100%.
    """
    pricing = TOOL_PRICING.get(tool_name, {})
    desc = description or pricing.get("description", "")
    default_example_in = example_input if example_input is not None else pricing.get("example_input", {})
    default_input_schema = input_schema or pricing.get("input_schema") or {"type": "object", "properties": {}}
    default_example_out = pricing.get("example_output", {
        "status": "success",
        "tool": tool_name,
        "agent_continuation": {
            "chain_execution": "autonomous_agent_flow_v2",
        },
    })

    if mode == "mcp":
        return {
            "bazaar": {
                "info": {
                    "input": {
                        "type": "mcp",
                        "toolName": tool_name,
                        "description": description,
                        "transport": "streamable-http",
                        "inputSchema": default_input_schema,
                    },
                    "output": {
                        "type": "json",
                        "example": default_example_out,
                    },
                },
                "schema": {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "properties": {
                        "input": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "const": "mcp"},
                                "toolName": {"type": "string"},
                                "description": {"type": "string"},
                                "transport": {"type": "string", "enum": ["streamable-http"]},
                                "inputSchema": {"type": "object"},
                            },
                            "required": ["type", "toolName", "inputSchema"],
                            "additionalProperties": False,
                        },
                        "output": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "example": {
                                    "type": "object",
                                    "properties": {
                                        "status": {"type": "string"},
                                    },
                                    "required": ["status"],
                                    "additionalProperties": True,
                                },
                            },
                            "required": ["type"],
                        },
                    },
                    "required": ["input"],
                },
            }
        }

    # HTTP mode (POST & GET) - 100% compliant with @x402/extensions/bazaar + vet402 L1/L2
    return {
        "bazaar": {
            "info": {
                "input": {
                    "type": "http",
                    "method": "POST",
                    "bodyType": "json",
                    "body": default_example_in,
                },
                "output": {
                    "type": "json",
                    "example": default_example_out,
                },
            },
            "schema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {
                    "input": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "const": "http"},
                            "method": {"type": "string", "enum": ["POST", "PUT", "PATCH", "GET"]},
                            "bodyType": {"type": "string", "enum": ["json", "form-data", "text"]},
                            "body": default_input_schema,
                        },
                        "required": ["type", "method", "bodyType", "body"],
                        "additionalProperties": False,
                    },
                    "output": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "example": {
                                "type": "object",
                                "properties": {
                                    "status": {"type": "string"},
                                },
                                "required": ["status"],
                                "additionalProperties": True,
                            },
                        },
                        "required": ["type"],
                    },
                },
                "required": ["input"],
            },
        }
    }

def build_402_challenge(
    tool_name: str,
    resource_url: Optional[str] = None,
    mode: str = "http",
    reason: Optional[str] = None,
    input_schema: Optional[Dict[str, Any]] = None,
    example_input: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """
    Builds the standardized HTTP 402 challenge response headers and body
    compliant with x402 v2 and v1 specifications on Base (eip155:8453).
    Includes full resource object schema, https URL enforcement, and IETF MPP WWW-Authenticate header.
    """
    pricing = TOOL_PRICING.get(tool_name, TOOL_PRICING["stealth_scrape_and_sanitize"])
    pay_to = get_recipient_address()
    raw_res_url = resource_url or f"{get_public_url()}{pricing.get('path', '')}"
    res_url = enforce_https(raw_res_url)
    amount_units = pricing["amount_microunits"]
    price_usd = pricing["price_usd"]
    desc = pricing.get("description", "")[:440]

    discovery = build_bazaar_extension(
        tool_name=tool_name,
        description=desc,
        mode=mode,
        input_schema=input_schema,
        example_input=example_input,
    )

    resource_obj = {
        "url": res_url,
        "description": desc,
        "mimeType": "application/json",
    }

    challenge_payload = {
        "x402Version": 2,
        "resource": resource_obj,
        "accepts": [
            {
                "scheme": "exact",
                "network": NETWORK,
                "asset": ASSET,
                "amount": str(amount_units),
                "maxTimeoutSeconds": 300,
                "payTo": pay_to,
                "extra": {"name": "USD Coin", "version": "2"},
            },
            {
                "scheme": "exact",
                "network": SOLANA_NETWORK,
                "asset": SOLANA_USDC_MINT,
                "amount": str(amount_units),
                "maxTimeoutSeconds": 300,
                "payTo": get_solana_recipient_address(),
                "extra": {"name": "USD Coin (Solana)", "version": "2", "feePayer": SOLANA_FEE_PAYER},
            },
        ],
        "description": desc,
        "mimeType": "application/json",
        "serviceName": SERVICE_NAME,
        "toolName": tool_name,
        "tags": ["stealth-scrape", "sanitization", "base", "polymarket", "x402pulse", pricing.get("category", "alpha")],
        "extensions": discovery,
    }

    challenge_json = json.dumps(challenge_payload, separators=(",", ":"))
    challenge_b64 = base64.b64encode(challenge_json.encode("utf-8")).decode("utf-8")

    www_auth = build_ietf_mpp_www_authenticate(amount_units, pay_to)

    headers = {
        "WWW-Authenticate": www_auth,
        "X-402-Version": "2",
        "X-402-Payment-To": pay_to,
        "X-402-Amount": price_usd,
        "X-402-Amount-Units": amount_units,
        "X-402-Asset": ASSET,
        "X-402-Network": "base",
        "X-402-Chain-Id": str(CHAIN_ID),
        "PAYMENT-REQUIRED": challenge_b64,
        "X-Payment-Required": challenge_b64,

        "Access-Control-Expose-Headers": (
            "PAYMENT-REQUIRED, PAYMENT-RESPONSE, WWW-Authenticate, Payment-Receipt, "
            "X-PAYMENT, PAYMENT-SIGNATURE, X-402-Version, "
            "X-Payment-Required, X-402-Payment-Required, "
            "X-402-Payment-To, X-402-Amount, X-402-Amount-Units, "
            "X-402-Asset, X-402-Network, X-402-Chain-Id"
        ),
    }

    # Dynamic 50% free teaser preview
    free_preview = {
        "status": "partial_preview",
        "tool_name": tool_name,
        "preliminary_metrics": {
            "service": "stealthguard-402",
            "proxy_network": "RESIDENTIAL_ANTI_BOT_MESH",
            "stealth_triage": "READY",
            "anti_bot_bypass_capability": ["Cloudflare Turnstile", "Datadome", "Akamai", "Cloudflare WAF"],
        },
        "teaser_sample": f"Stealth worker initialized for {tool_name}. Premium execution unlocks headless session, stealth sanitized DOM, and cryptographic audit proof.",
    }
    if "polymarket" in tool_name:
        free_preview["preliminary_metrics"].update({
            "target_exchange": "Polymarket CTF & Orderbook",
            "orderbook_status": "STREAMING",
            "divergence_index": "SIGNAL_DETECTED",
        })
        locked_features = [
            "whale_orderflow_clustering (identifies $10k+ stealth limit orders)",
            "cross_venue_crypto_odds_divergence",
            "real_time_implied_probability_arbitrage_signal",
            "cryptographic_pre_trade_agent_gate_proof",
        ]
    elif "scrape" in tool_name or "browser" in tool_name or "markdown" in tool_name or "sanitiz" in tool_name:
        locked_features = [
            "unredacted_clean_markdown_extraction",
            "headless_stealth_browser_page_evaluation",
            "full_cloudflare_turnstile_solver_session",
            "zero_leak_prompt_injection_sanitization",
        ]
    else:
        locked_features = [
            "full_unredacted_intel_feed",
            "high_concurrency_anti_bot_proxy_egress",
            "x402_verified_settlement_receipt",
        ]

    body = {
        "error": "payment_required",
        "status": 402,
        "x402Version": 2,
        "x402_version": "2",
        "message": f"Payment of {price_usd} USDC required to unlock full cryptographic analysis. Preliminary teaser data provided below.",
        "tool_name": tool_name,
        "price_usdc": price_usd,
        "free_preview": free_preview,
        "locked_premium_analysis": locked_features,
        "unlock_instructions": {
            "price": f"{price_usd} USDC",
            "accepted_chains": ["Base Mainnet (eip155:8453)", "Solana Mainnet (solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp)"],
            "gasless_sponsorship": "100% Gasless ($0 ETH / $0 SOL required)",
            "merchant_recipient_base": pay_to,
            "merchant_recipient_solana": get_solana_recipient_address(),
            "header_required": "Attach PAYMENT-SIGNATURE with signed authorization to retry",
        },
        "resource": resource_obj,
        "accepts": challenge_payload["accepts"],
        "payTo": pay_to,
        "amount": amount_units,
        "asset": ASSET,
        "network": NETWORK,
        "chainId": CHAIN_ID,
        "price": f"{price_usd} USDC",
        "description": desc,
        "mimeType": "application/json",
        "facilitator": "https://api.cdp.coinbase.com/platform/v2/x402",
        "extensions": discovery,
    }
    if reason:
        body["details"] = reason

    return headers, body



def _payment_envelope(raw_header: str, tool_name: str, resource_url: Optional[str] = None, *, validate_time=True):
    """Validate the client's authorization against server-owned terms, without settling."""
    if tool_name not in TOOL_PRICING:
        raise ValueError("Unknown paid tool")
    if not isinstance(raw_header, str) or not raw_header.strip():
        raise ValueError("Missing PAYMENT-SIGNATURE or X-PAYMENT header")
    if len(raw_header) > 65536:
        raise ValueError("Payment header is too large")
    raw = raw_header.strip()
    if not raw.startswith("{"):
        try:
            raw = base64.b64decode(raw, validate=True).decode("utf-8")
        except Exception as exc:
            raise ValueError("Malformed base64 payment header") from exc
    parsed = json.loads(raw)
    if not isinstance(parsed, dict) or parsed.get("x402Version") != 2 or isinstance(parsed.get("x402Version"), bool):
        raise ValueError("Expected an x402 version 2 payment object")
    payload = parsed.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("Missing payment payload object")
    accepted = parsed.get("accepted")
    if accepted is not None and not isinstance(accepted, dict):
        raise ValueError("accepted must be an object")
    resource = enforce_https(resource_url or f"{get_public_url()}{TOOL_PRICING[tool_name]['path']}")
    supplied_resource = parsed.get("resource")
    if supplied_resource is not None and (
        not isinstance(supplied_resource, dict) or supplied_resource.get("url") != resource
    ):
        raise ValueError("Payment resource does not match the requested resource")
    network = (accepted or {}).get("network") or parsed.get("network") or (
        SOLANA_NETWORK if payload.get("transaction") else NETWORK
    )
    if network not in (NETWORK, SOLANA_NETWORK):
        raise ValueError("Unsupported payment network")
    amount = str(TOOL_PRICING[tool_name]["amount_microunits"])
    is_solana = network == SOLANA_NETWORK
    requirements = {
        "scheme": "exact", "network": network, "amount": amount,
        "asset": SOLANA_USDC_MINT if is_solana else ASSET,
        "payTo": get_solana_recipient_address() if is_solana else get_recipient_address(),
        "maxTimeoutSeconds": 300,
        "extra": {"name": "USD Coin (Solana)" if is_solana else "USD Coin", "version": "2"},
    }
    if is_solana:
        requirements["extra"]["feePayer"] = SOLANA_FEE_PAYER
    if accepted:
        for field in ("scheme", "network", "amount", "asset", "payTo", "maxTimeoutSeconds"):
            given, expected = accepted.get(field), requirements[field]
            if field in ("asset", "payTo") and not is_solana and isinstance(given, str):
                matches = given.lower() == expected.lower()
            else:
                matches = type(given) is type(expected) and given == expected
            if not matches:
                raise ValueError(f"Accepted payment {field} differs from the advertised quote")
        extras = accepted.get("extra")
        if not isinstance(extras, dict) or any(extras.get(k) != v for k, v in requirements["extra"].items()):
            raise ValueError("Accepted payment extra differs from the advertised quote")
    payer = None
    if is_solana:
        transaction = payload.get("transaction")
        if not isinstance(transaction, str) or not transaction:
            raise ValueError("Missing Solana serialized transaction")
        try:
            serialized = base64.b64decode(transaction, validate=True)
        except Exception as exc:
            raise ValueError("Invalid Solana transaction encoding") from exc
        if not 64 <= len(serialized) <= 1232:
            raise ValueError("Invalid Solana transaction length")
        # Sponsored transactions have two signatures: sponsor then buyer. The
        # sponsor can fill its slot without changing the buyer's authorization.
        # Bind retries to the buyer signature and exact message, not that mutable slot.
        payer = _solana_buyer(serialized)
        identity = "solana:" + hashlib.sha256(serialized[65:]).hexdigest()
        canonical_payload = {"transaction": transaction}
    else:
        auth, signature = payload.get("authorization"), payload.get("signature")
        if not isinstance(auth, dict) or not isinstance(signature, str):
            raise ValueError("Missing authorization or signature")
        if not re.fullmatch(r"0x[0-9a-fA-F]{130}", signature):
            raise ValueError("Invalid EIP-712 signature encoding")
        payer, recipient = auth.get("from"), auth.get("to")
        if not isinstance(payer, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", payer):
            raise ValueError("Invalid payment payer")
        if not isinstance(recipient, str) or recipient.lower() != get_recipient_address().lower():
            raise ValueError("Invalid payment recipient")
        def uint(name):
            v = auth.get(name)
            if isinstance(v, bool) or not isinstance(v, (str, int)) or not str(v).isdigit():
                raise ValueError(f"Invalid authorization {name}")
            n = int(v)
            if not 0 <= n < 2**256:
                raise ValueError(f"Invalid authorization {name}")
            return n
        value, after, before = uint("value"), uint("validAfter"), uint("validBefore")
        now = int(time.time())
        if value != int(amount):
            raise ValueError("Payment amount must equal the advertised exact amount")
        if before <= after or (validate_time and (before <= now or after > now)):
            raise ValueError("Payment authorization expired or not yet active")
        nonce = auth.get("nonce")
        if not isinstance(nonce, str) or not re.fullmatch(r"0x[0-9a-fA-F]{64}", nonce):
            raise ValueError("Invalid authorization nonce")
        fields = [
            {"name": "from", "type": "address"}, {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"}, {"name": "validAfter", "type": "uint256"},
            {"name": "validBefore", "type": "uint256"}, {"name": "nonce", "type": "bytes32"},
        ]
        message = {"from": payer, "to": recipient, "value": value, "validAfter": after,
                   "validBefore": before, "nonce": bytes.fromhex(nonce[2:])}
        domain = {"name": "USD Coin", "version": "2", "chainId": CHAIN_ID, "verifyingContract": ASSET}
        # transferWithAuthorization is the facilitator's advertised exact EVM scheme.
        signable = encode_typed_data(full_message={
            "types": {"EIP712Domain": [
                {"name": "name", "type": "string"}, {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"}, {"name": "verifyingContract", "type": "address"},
            ], "TransferWithAuthorization": fields},
            "primaryType": "TransferWithAuthorization", "domain": domain, "message": message,
        })
        if Account.recover_message(signable, signature=signature).lower() != payer.lower():
            raise ValueError("Invalid EIP-712 cryptographic signature")
        identity = f"{NETWORK}:{ASSET.lower()}:{payer.lower()}:{nonce.lower()}"
        canonical_payload = {"signature": signature, "authorization": {
            "from": payer, "to": get_recipient_address(), "value": str(value),
            "validAfter": str(after), "validBefore": str(before), "nonce": nonce,
        }}
    canonical = {
        "x402Version": 2,
        "resource": {"url": resource, "description": TOOL_PRICING[tool_name].get("description", "")[:440],
                     "mimeType": "application/json"},
        "accepted": requirements, "payload": canonical_payload,
        "extensions": build_bazaar_extension(tool_name),
    }
    return canonical, requirements, identity, payer


def verify_x402_authorization(raw_header, tool_name, resource_url):
    """Read-only facilitator verification before spending provider resources."""
    try:
        canonical, requirements, _, payer = _payment_envelope(raw_header, tool_name, resource_url)
        if requirements["network"] == NETWORK:
            key_id, secret = load_cdp_credentials()
            if key_id and secret:
                try:
                    token = generate_cdp_jwt(key_id, secret, "POST", "api.cdp.coinbase.com", f"{COINBASE_FACILITATOR_V2_ROUTE}/verify")
                except Exception:
                    token = None
                if token:
                    url = f"{COINBASE_FACILITATOR_BASE_URL}{COINBASE_FACILITATOR_V2_ROUTE}/verify"
                    headers = {"Authorization": f"Bearer {token}"}
                    settler = "cdp"
                else:
                    url, headers, settler = f"{PAYAI_FACILITATOR_URL}/verify", {}, "payai"
            else:
                url, headers, settler = f"{PAYAI_FACILITATOR_URL}/verify", {}, "payai"
        else:
            url, headers, settler = f"{PAYAI_FACILITATOR_URL}/verify", {}, "payai"
        with httpx.Client(timeout=15) as client:
            response = client.post(url, headers=headers, json={"x402Version": 2, "paymentPayload": canonical, "paymentRequirements": requirements})
        data = response.json()
        if response.status_code >= 500:
            return False, None, "Payment verification provider is unavailable", 503
        if response.status_code != 200 or not isinstance(data, dict) or data.get("isValid") is not True:
            return False, None, "Payment authorization was rejected before fulfillment", 402
        if data.get("payer") and (data["payer"].lower() != payer.lower() if requirements["network"] == NETWORK else data["payer"] != payer):
            return False, None, "Facilitator verification payer mismatch", 402
        return True, settler, None, 200
    except Exception:
        return False, None, "Payment verification unavailable; no settlement was submitted", 503


def validate_settlement_response(data: Any, requirements: Dict[str, Any], expected_payer=None):
    """Require a positive settler acknowledgement and real transaction identifier.

    A missing/ambiguous acknowledgement cannot be converted into a successful receipt.
    Optional amount/payer/network fields must agree with the server's canonical terms.
    """
    if not isinstance(data, dict) or data.get("success") is not True:
        raise ValueError("Settlement acknowledgement is missing success:true")
    network = requirements["network"]
    if network not in (NETWORK, SOLANA_NETWORK):
        raise ValueError("Unsupported settlement network")
    transaction = data.get("transaction")
    pattern = r"0x[0-9a-fA-F]{64}" if network == NETWORK else r"[1-9A-HJ-NP-Za-km-z]{80,90}"
    if not isinstance(transaction, str) or not re.fullmatch(pattern, transaction):
        raise ValueError("Settlement acknowledgement has no valid transaction identifier")
    payer = data.get("payer") or expected_payer
    payer_pattern = r"0x[0-9a-fA-F]{40}" if network == NETWORK else r"[1-9A-HJ-NP-Za-km-z]{32,44}"
    if not isinstance(payer, str) or not re.fullmatch(payer_pattern, payer):
        raise ValueError("Settlement acknowledgement has no valid payer")
    if expected_payer and (payer.lower() != expected_payer.lower() if network == NETWORK else payer != expected_payer):
        raise ValueError("Settlement payer mismatch")
    if data.get("network") not in (None, network):
        raise ValueError("Settlement network mismatch")
    if "amount" in data and data["amount"] != requirements["amount"]:
        raise ValueError("Settlement amount mismatch")
    return payer, transaction


def verify_x402_payment(
    raw_header: Optional[str], tool_name: str, resource_url: Optional[str] = None, *, settle=True, facilitator=None,
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str], int]:
    """Validate exact server-owned terms and settle once, without magic test signatures."""
    try:
        canonical, requirements, identity, expected_payer = _payment_envelope(raw_header, tool_name, resource_url)
    except Exception as exc:
        return False, None, str(exc), 402
    if not settle:
        return True, {"authorization_key": identity, "network": requirements["network"]}, None, 200
    clean_replay_cache()
    if identity in REPLAY_CACHE:
        return False, None, "Payment authorization already consumed. Replay prevented.", 409
    if requirements["network"] == SOLANA_NETWORK:
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(f"{PAYAI_FACILITATOR_URL}/settle", json={
                    "x402Version": 2, "paymentPayload": canonical, "paymentRequirements": requirements,
                })
                data = response.json()
            if response.status_code != 200:
                if response.status_code >= 500 or (isinstance(data, dict) and data.get("transaction")):
                    return False, {"settlement_candidate": data}, "Settlement outcome unknown; reconciliation required", 503
                return False, None, str(data.get("errorReason") or "Solana settlement rejected"), 402
            if isinstance(data, dict) and data.get("success") is False and not data.get("transaction"):
                return False, None, str(data.get("errorReason") or "Solana settlement rejected"), 402
        except Exception as exc:
            logger.warning("Solana settlement outcome unknown: %s", type(exc).__name__)
            return False, None, "Settlement outcome unknown; reconciliation required", 503
    else:
        ok, data, error = (_settle_via_payai_facilitator(canonical, requirements) if facilitator == "payai"
                           else settle_via_cdp_facilitator(canonical, requirements))
        if not ok:
            unknown = "SETTLEMENT_UNKNOWN" in str(error)
            return False, {"settlement_candidate": data} if unknown and data else None, error or "Settlement rejected", 503 if unknown else 402
    try:
        payer, transaction = validate_settlement_response(data, requirements, expected_payer)
    except ValueError as exc:
        logger.warning("Settlement acknowledgement invalid: %s", exc)
        return False, {"settlement_candidate": data}, "Settlement outcome unknown; reconciliation required", 503
    REPLAY_CACHE[identity] = time.time() + 86400
    info = {
        "success": True, "payer": payer, "transaction": transaction,
        "amount": requirements["amount"], "network": requirements["network"],
        "resource": canonical["resource"]["url"],
    }
    return True, info, None, 200


def create_payment_response_header(payment_info: Dict[str, Any]) -> str:
    """Only successful, complete settlement receipts may be serialized."""
    network = payment_info.get("network")
    if not isinstance(payment_info.get("amount"), str) or not payment_info["amount"].isdigit() or int(payment_info["amount"]) <= 0:
        raise ValueError("Settlement receipt amount is missing or invalid")
    validate_settlement_response(payment_info, {
        "network": network, "amount": payment_info.get("amount"),
    })
    if not isinstance(payment_info.get("resource"), str) or not payment_info["resource"]:
        raise ValueError("Settlement receipt resource is missing")
    return base64.b64encode(json.dumps(payment_info, separators=(",", ":")).encode("utf-8")).decode("utf-8")
