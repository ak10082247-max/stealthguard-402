"""Actual tool fulfillment, shared by HTTP and MCP; never settles payments."""
import base64
import json
import urllib.parse
from typing import Dict, Any
import httpx
from .config import AGENT_CONTINUATION, get_public_url
from .cache_warmer import CACHE_STORE, get_ecosystem_recommendations
from .scrapling_engine import stealth_scrape_and_sanitize
from .polymarket_engine import scan_polymarket_alpha
from .token_gate_engine import pre_trade_agent_gate
from .sanitizer import sanitize_content
from .microtools import fulfill_microtool
from .payment_execution import ToolFailure
import logging
logger = logging.getLogger("stealthguard.tools")

async def fulfill_tool(tool_name: str, merged_args: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    if tool_name == "stealth_scrape_and_sanitize":
        target_url = merged_args.get("url", "https://news.ycombinator.com")
        result = await stealth_scrape_and_sanitize(
            url=target_url, extract_schema=merged_args.get("extract_schema"),
            render_js=merged_args.get("render_js", False), strict_mode=merged_args.get("strict_mode", True),
        )

    elif tool_name == "polymarket_alpha_divergence":
        limit = int(merged_args.get("limit", 15))
        category = merged_args.get("category")
        result = await scan_polymarket_alpha(
            category=category, limit=limit, strict_mode=merged_args.get("strict_mode", True),
        )

    elif tool_name == "pre_trade_agent_gate":
        address = merged_args.get("token_or_service_address", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
        chain = merged_args.get("chain", "base")
        result = await pre_trade_agent_gate(
            token_or_service_address=address,
            chain=chain,
            target_url=merged_args.get("target_url"),
            strict_mode=bool(merged_args.get("strict_mode", True)),
        )

    elif tool_name == "security_prompt_firewall":
        raw_text = merged_args.get("text", "")
        receipt = sanitize_content(raw_text)
        result = {
            "status": "success", "tool": tool_name,
            "threat_level": "CLEAN" if receipt["risk_score"] < 0.3 else "THREAT_DETECTED",
            "sanitized_text": receipt["sanitized_content"], "canaryguard_meta": receipt,
            "recommended_actions": get_ecosystem_recommendations("scrape"),
        }

    elif tool_name == "security_x402_endpoint_verifier":
        ep = merged_args.get("endpoint_url") or f"{get_public_url()}/v1/stealth_scrape_and_sanitize"
        from .public_url import require_public_url
        await __import__("asyncio").to_thread(require_public_url, ep)
        # Probe the endpoint URL to check for authentic x402 headers
        is_authentic_402 = False
        probe_notes = ""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                from .public_url import fetch_pinned
                fetched = await __import__("asyncio").to_thread(fetch_pinned, ep)
                probe_res = httpx.Response(fetched["status"], content=fetched["body"], headers=fetched["headers"], request=httpx.Request("GET", ep))
                pay_hdr = probe_res.headers.get("payment-required") or probe_res.headers.get("x-payment-required")
                parsed_challenge = None
                if pay_hdr:
                    try:
                        raw = pay_hdr.strip()
                        if not raw.startswith("{"):
                            raw = base64.b64decode(raw).decode("utf-8")
                        parsed_challenge = json.loads(raw)
                    except Exception:
                        parsed_challenge = None

                if not parsed_challenge and probe_res.status_code == 402:
                    try:
                        parsed_challenge = probe_res.json()
                    except Exception:
                        pass

                is_valid_x402_schema = (
                    isinstance(parsed_challenge, dict)
                    and not isinstance(parsed_challenge.get("x402Version"), bool)
                    and (
                        (
                            parsed_challenge.get("x402Version") == 2
                            and isinstance(parsed_challenge.get("resource"), dict)
                            and isinstance(parsed_challenge["resource"].get("url"), str)
                            and len(parsed_challenge["resource"]["url"]) > 0
                            and isinstance(parsed_challenge.get("accepts"), list)
                            and len(parsed_challenge["accepts"]) > 0
                            and all(
                                isinstance(a, dict)
                                and a.get("scheme") in ("exact", "upto")
                                and isinstance(a.get("maxTimeoutSeconds"), int)
                                and not isinstance(a.get("maxTimeoutSeconds"), bool)
                                and a["maxTimeoutSeconds"] > 0
                                and isinstance(a.get("amount"), str)
                                and a["amount"].isdigit()
                                and int(a["amount"]) > 0
                                and isinstance(a.get("network"), str)
                                and (
                                    (
                                        (a["network"] == "base" or (a["network"].startswith("eip155:") and len(a["network"]) > 7 and a["network"][7:].isdigit()))
                                        and isinstance(a.get("asset"), str)
                                        and a["asset"].startswith("0x")
                                        and len(a["asset"]) == 42
                                        and all(c in "0123456789abcdefABCDEF" for c in a["asset"][2:])
                                        and isinstance(a.get("payTo"), str)
                                        and a["payTo"].startswith("0x")
                                        and len(a["payTo"]) == 42
                                        and all(c in "0123456789abcdefABCDEF" for c in a["payTo"][2:])
                                    )
                                    or (
                                        (a["network"] == "solana" or (a["network"].startswith("solana:") and len(a["network"]) > 7 and all(c in "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz" for c in a["network"][7:])))
                                        and isinstance(a.get("asset"), str)
                                        and 32 <= len(a["asset"]) <= 44
                                        and all(c in "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz" for c in a["asset"])
                                        and isinstance(a.get("payTo"), str)
                                        and 32 <= len(a["payTo"]) <= 44
                                        and all(c in "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz" for c in a["payTo"])
                                    )
                                )
                                for a in parsed_challenge["accepts"]
                            )
                        )
                        or (
                            parsed_challenge.get("x402Version") == 1
                            and (
                                (isinstance(parsed_challenge.get("accepts"), list) and len(parsed_challenge["accepts"]) > 0)
                                or (isinstance(parsed_challenge.get("paymentRequirements"), list) and len(parsed_challenge["paymentRequirements"]) > 0)
                            )
                            and all(
                                isinstance(r, dict)
                                and r.get("scheme") in ("exact", "upto")
                                and isinstance(r.get("maxTimeoutSeconds"), int)
                                and not isinstance(r.get("maxTimeoutSeconds"), bool)
                                and r["maxTimeoutSeconds"] > 0
                                and (
                                    (isinstance(r.get("maxAmountRequired"), str) and r["maxAmountRequired"].isdigit() and int(r["maxAmountRequired"]) > 0)
                                    or (isinstance(r.get("amount"), str) and r["amount"].isdigit() and int(r["amount"]) > 0)
                                )
                                and isinstance(r.get("network"), str)
                                and (
                                    (
                                        (r["network"] == "base" or (r["network"].startswith("eip155:") and len(r["network"]) > 7 and r["network"][7:].isdigit()))
                                        and isinstance(r.get("asset"), str)
                                        and r["asset"].startswith("0x")
                                        and len(r["asset"]) == 42
                                        and all(c in "0123456789abcdefABCDEF" for c in r["asset"][2:])
                                        and isinstance(r.get("payTo"), str)
                                        and r["payTo"].startswith("0x")
                                        and len(r["payTo"]) == 42
                                        and all(c in "0123456789abcdefABCDEF" for c in r["payTo"][2:])
                                    )
                                    or (
                                        (r["network"] == "solana" or (r["network"].startswith("solana:") and len(r["network"]) > 7 and all(c in "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz" for c in r["network"][7:])))
                                        and isinstance(r.get("asset"), str)
                                        and 32 <= len(r["asset"]) <= 44
                                        and all(c in "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz" for c in r["asset"])
                                        and isinstance(r.get("payTo"), str)
                                        and 32 <= len(r["payTo"]) <= 44
                                        and all(c in "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz" for c in r["payTo"])
                                    )
                                )
                                for r in (parsed_challenge.get("accepts") or parsed_challenge.get("paymentRequirements") or [])
                            )
                        )
                    )
                )

                is_structurally_valid = bool(probe_res.status_code == 402 and is_valid_x402_schema)
                resource_url = parsed_challenge.get("resource", {}).get("url") if isinstance(parsed_challenge, dict) and isinstance(parsed_challenge.get("resource"), dict) else None

                parsed_ep = urllib.parse.urlparse(ep)
                ep_scheme = (parsed_ep.scheme or "").lower()
                ep_host = (parsed_ep.hostname or "").lower()
                ep_port = parsed_ep.port or (443 if ep_scheme == "https" else 80 if ep_scheme == "http" else None)

                parsed_res = urllib.parse.urlparse(resource_url) if resource_url and isinstance(resource_url, str) else None
                res_scheme = (parsed_res.scheme or "").lower() if parsed_res else None
                res_host = (parsed_res.hostname or "").lower() if parsed_res else None
                res_port = (parsed_res.port or (443 if res_scheme == "https" else 80 if res_scheme == "http" else None)) if parsed_res else None

                is_https = bool(ep_scheme == "https" and res_scheme == "https")
                is_standard_https_port = bool(ep_port in (None, 443) and res_port in (None, 443))

                TRUSTED_FLEET_HOSTS = {
                    "canaryguard-402.onrender.com",
                    "rugshield-402.onrender.com",
                    "stealthguard-402.onrender.com",
                    "x402-agent-tollbooth.onrender.com"
                }

                is_verified_provider = bool(ep_host in TRUSTED_FLEET_HOSTS and is_https and is_standard_https_port)

                matches_endpoint = False
                if parsed_res and parsed_ep and is_https and is_standard_https_port:
                    if res_host == ep_host and res_port == ep_port:
                        res_path = parsed_res.path.rstrip("/")
                        ep_path = parsed_ep.path.rstrip("/")
                        if res_path == ep_path:
                            matches_endpoint = True

                FLEET_EVM_PAYEES = {
                    "0x80e0ae84679b7f11be171daadd492fbecf628cd6"
                }
                FLEET_SOL_PAYEES = {
                    "9wuMysgXwNhtQeqJgGByAiMYc4EjzZ5wUSmnjrrt3ffh",
                    "DD3A7jaXFeHcif9eYj6Vhomuxypat5Yxi8ow6wxz27yL"
                }
                BASE_USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
                SOLANA_USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

                # Complete canonical registry of exact registered active offers across all 4 fleet services (57 active canonical routes)
                # Retired (410), redirect (307), and unadvertised aliases are omitted so they evaluate as settlement_safe: false.
                FLEET_REGISTERED_OFFERS: Dict[Tuple[str, str], int] = {
                    # canaryguard-402.onrender.com (26 active canonical routes)
                    ("canaryguard-402.onrender.com", "/v1/sanitize"): 10_000,
                    ("canaryguard-402.onrender.com", "/v1/base/token"): 10_000,
                    ("canaryguard-402.onrender.com", "/v1/wallet-analysis"): 10_000,
                    ("canaryguard-402.onrender.com", "/v1/contract-info"): 10_000,
                    ("canaryguard-402.onrender.com", "/v1/wallet-sanctions-check"): 10_000,
                    ("canaryguard-402.onrender.com", "/v1/uniswap-pool-state"): 10_000,
                    ("canaryguard-402.onrender.com", "/v1/crypto-price-onchain"): 10_000,
                    ("canaryguard-402.onrender.com", "/v1/json-repair-and-sanitize"): 10_000,
                    ("canaryguard-402.onrender.com", "/v1/url-agent-readiness"): 10_000,
                    ("canaryguard-402.onrender.com", "/v1/tx-status-base"): 10_000,
                    ("canaryguard-402.onrender.com", "/v1/defi-yields-safe"): 10_000,
                    ("canaryguard-402.onrender.com", "/v1/llm-token-pricing"): 10_000,
                    ("canaryguard-402.onrender.com", "/v1/eip712-signature-audit"): 10_000,
                    ("canaryguard-402.onrender.com", "/v1/mcp-tool-auditor"): 10_000,
                    ("canaryguard-402.onrender.com", "/v1/security/wallet-drainer-check"): 20_000,
                    ("canaryguard-402.onrender.com", "/v1/security/mcp-tool-poisoning-audit"): 20_000,
                    ("canaryguard-402.onrender.com", "/v1/security/agent-memory-guard"): 20_000,
                    ("canaryguard-402.onrender.com", "/v1/security/phishing-url-inspector"): 20_000,
                    ("canaryguard-402.onrender.com", "/v1/security/smart-contract-honeypot-check"): 20_000,
                    ("canaryguard-402.onrender.com", "/v1/security/eip712-signature-auditor"): 20_000,
                    ("canaryguard-402.onrender.com", "/v1/alpha/safe-base-trending"): 20_000,
                    ("canaryguard-402.onrender.com", "/v1/risk/full_audit"): 20_000,
                    ("canaryguard-402.onrender.com", "/v1/verify/agent-attestation"): 20_000,
                    ("canaryguard-402.onrender.com", "/v1/ondemand/market-snapshot"): 20_000,
                    ("canaryguard-402.onrender.com", "/v1/tokens/history-and-spread"): 20_000,
                    ("canaryguard-402.onrender.com", "/v1/yield/safe-allocation"): 20_000,

                    # stealthguard-402.onrender.com (15 active canonical routes)
                    ("stealthguard-402.onrender.com", "/v1/stealth_scrape_and_sanitize"): 15_000,
                    ("stealthguard-402.onrender.com", "/v1/polymarket_alpha_divergence"): 20_000,
                    ("stealthguard-402.onrender.com", "/v1/pre_trade_agent_gate"): 10_000,
                    ("stealthguard-402.onrender.com", "/v1/alpha/polymarket-top-whales"): 10_000,
                    ("stealthguard-402.onrender.com", "/v1/alpha/polymarket-crypto-odds"): 10_000,
                    ("stealthguard-402.onrender.com", "/v1/alpha/base-trending-tokens"): 10_000,
                    ("stealthguard-402.onrender.com", "/v1/alpha/defi-yield-radar"): 10_000,
                    ("stealthguard-402.onrender.com", "/v1/alpha/hackernews-ai-digest"): 10_000,
                    ("stealthguard-402.onrender.com", "/v1/security/prompt-firewall"): 10_000,
                    ("stealthguard-402.onrender.com", "/v1/security/x402-endpoint-verifier"): 10_000,
                    ("stealthguard-402.onrender.com", "/v1/research/deep-web-dossier"): 20_000,
                    ("stealthguard-402.onrender.com", "/v1/oracle/perp-funding-and-basis"): 20_000,
                    ("stealthguard-402.onrender.com", "/v1/alpha/polymarket-whale-orderflow"): 20_000,
                    ("stealthguard-402.onrender.com", "/v1/security/attestation-bundle"): 20_000,
                    ("stealthguard-402.onrender.com", "/v1/research/topic-news-scanner"): 20_000,

                    # rugshield-402.onrender.com (12 active canonical routes: 6 /v1/* + 6 canonical /api/v1/*)
                    ("rugshield-402.onrender.com", "/v1/scan"): 10_000,
                    ("rugshield-402.onrender.com", "/v1/audit/liquidity-lock-verify"): 20_000,
                    ("rugshield-402.onrender.com", "/v1/audit/holder-cluster-map"): 20_000,
                    ("rugshield-402.onrender.com", "/v1/audit/swap-simulation-proof"): 20_000,
                    ("rugshield-402.onrender.com", "/v1/audit/cross-chain-bridge-risk"): 20_000,
                    ("rugshield-402.onrender.com", "/v1/risk/institutional-token-report"): 20_000,
                    ("rugshield-402.onrender.com", "/api/v1/token-screener"): 10_000,
                    ("rugshield-402.onrender.com", "/api/v1/smart-money/netflow"): 10_000,
                    ("rugshield-402.onrender.com", "/api/v1/smart-money/dex-trades"): 10_000,
                    ("rugshield-402.onrender.com", "/api/v1/tgm/who-bought-sold"): 10_000,
                    ("rugshield-402.onrender.com", "/api/v1/tgm/holders"): 10_000,
                    ("rugshield-402.onrender.com", "/api/v1/profiler/address/current-balance"): 10_000,

                    # x402-agent-tollbooth.onrender.com (4 active canonical routes)
                    ("x402-agent-tollbooth.onrender.com", "/toll/ai_intel"): 1_000,
                    ("x402-agent-tollbooth.onrender.com", "/toll/arbitrage_scan"): 2_000,
                    ("x402-agent-tollbooth.onrender.com", "/toll/smart_router"): 1_000,
                    ("x402-agent-tollbooth.onrender.com", "/api/audit"): 20_000,
                }

                accepts_list = parsed_challenge.get("accepts") or parsed_challenge.get("paymentRequirements") or []
                is_v2_challenge = parsed_challenge.get("x402Version") == 2

                def is_supported_fleet_alternative(alt: Dict[str, Any]) -> bool:
                    if not isinstance(alt, dict) or not is_v2_challenge:
                        return False
                    scheme = str(alt.get("scheme", "")).lower()
                    if scheme != "exact":
                        return False
                    network = str(alt.get("network", ""))
                    asset = str(alt.get("asset", ""))
                    pay_to = str(alt.get("payTo", ""))
                    amt_raw = alt.get("amount") if alt.get("amount") is not None else alt.get("maxAmount")
                    ep_path = parsed_ep.path.rstrip("/") if parsed_ep else ""
                    route_key = (ep_host, ep_path)
                    if route_key not in FLEET_REGISTERED_OFFERS:
                        # Unregistered route on fleet host cannot be certified settlement-safe
                        return False
                    expected_exact_amt = FLEET_REGISTERED_OFFERS[route_key]
                    try:
                        amt_num = int(float(amt_raw))
                        if amt_num != expected_exact_amt:
                            return False
                    except (ValueError, TypeError):
                        return False
                    if network == "eip155:8453":
                        return (asset.lower() == BASE_USDC and pay_to.lower() in FLEET_EVM_PAYEES)
                    elif network in ("solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp", "solana"):
                        return (asset == SOLANA_USDC and pay_to in FLEET_SOL_PAYEES)
                    return False

                has_valid_payee = bool(accepts_list) and all(is_supported_fleet_alternative(r) for r in accepts_list)

                is_settlement_safe = bool(is_structurally_valid and matches_endpoint and is_verified_provider and has_valid_payee and is_https)

                if is_settlement_safe:
                    verdict = "AUTHENTIC_X402_PROVIDER"
                    probe_notes = "Verified HTTPS HTTP 402 with valid x402 challenge schema, matching resource URL, and trusted fleet identity with supported payee terms."
                elif is_structurally_valid:
                    verdict = "CONFORMANT_X402_CHALLENGE_UNVERIFIED_ISSUER"
                    probe_notes = "Endpoint returned HTTP 402 with valid challenge schema, but issuer trust, payee ownership, scheme security (HTTPS), or resource binding is unverified. Not certified settlement safe."
                elif probe_res.status_code == 402:
                    verdict = "NOT_AN_X402_ENDPOINT"
                    probe_notes = "Endpoint returned HTTP 402, but challenge headers/body lack valid x402 protocol schema."
                else:
                    verdict = "NOT_AN_X402_ENDPOINT"
                    probe_notes = f"Endpoint returned HTTP {probe_res.status_code} (not HTTP 402). Not an active x402 service."
        except Exception as e:
            is_structurally_valid = False
            is_settlement_safe = False
            matches_endpoint = False
            verdict = "ENDPOINT_PROBE_ERROR"
            probe_notes = f"Endpoint unreachable or probe transport error: {str(e)}"

        result = {
            "status": "success",
            "audited_url": ep,
            "verdict": verdict,
            "settlement_safe": is_settlement_safe,
            "is_x402": is_structurally_valid,
            "structural_schema_valid": is_structurally_valid,
            "resource_url_bound": matches_endpoint if 'matches_endpoint' in locals() else False,
            "notes": probe_notes,
            "recommended_actions": get_ecosystem_recommendations("general"),
        }

    else:
        result = await fulfill_microtool(tool_name, merged_args)


    if result.get("error"):
        raise ToolFailure(str(result["error"]))
    if tool_name == "stealth_scrape_and_sanitize" and not 200 <= result.get("status_code", 0) < 300:
        raise ToolFailure("Target page could not be extracted successfully")
    if tool_name == "stealth_scrape_and_sanitize" and not result.get("token_compressed_markdown", "").strip() and not result.get("injection_detected"):
        raise ToolFailure("Target returned no extractable content")
    result["agent_continuation"] = AGENT_CONTINUATION
    return result
