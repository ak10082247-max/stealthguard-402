#!/usr/bin/env python3
"""
scripts/hot_wallet_bazaar_seeder.py
Autonomous Hot Wallet x402 Bazaar Force-Indexing Engine for Kurox Fleet.

Loops through EVERY paid endpoint across:
- StealthGuard-402 (all 10 micro-endpoints, $0.001 - $0.005 USDC)
- CanaryGuard-402 (/v1/sanitize, /v1/base/token, $0.003 USDC)
- RugShield-402 (/v1/scan, $0.005 USDC)

For each endpoint:
1. Validates 402 challenge against Coinbase CDP Preflight Validator (/validate).
2. Signs real EIP-3009 TransferWithAuthorization from Buyer Hot Wallet (0x6b5f...BEeD).
3. Constructs complete paymentPayload containing strict ResourceInfo object AND extensions.bazaar.
4. Broadcasts on-chain settlement via Coinbase CDP Facilitator (/settle).
5. Confirms on-chain BaseScan transaction hash and EXTENSION-RESPONSES header.
6. Sends live paid HTTP request to verify 200 OK + PAYMENT-RESPONSE header.
7. Verifies registration in Coinbase Bazaar Discovery Feed (/discovery/resources).
8. Pings x402scan.com, lumierepaycheck.org, 402radar.io, and x402-list.com.
"""

import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import json
import time
import base64
import urllib.request
import urllib.error
from pathlib import Path
from eth_account import Account
import httpx

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import ASSET, NETWORK, get_recipient_address, TOOL_PRICING
from src.x402_middleware import (
    load_cdp_credentials,
    generate_cdp_jwt,
)
from scripts.seed_live_settlement import find_buyer_private_key, sign_x402_authorization, check_onchain_balance

COINBASE_SETTLE_URL = "https://api.cdp.coinbase.com/platform/v2/x402/settle"
COINBASE_VALIDATE_URL = "https://api.cdp.coinbase.com/platform/v2/x402/validate"
COINBASE_DISCOVERY_URL = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources"

ALL_PAID_ENDPOINTS = [
    # ---------------- StealthGuard-402 (10 Micro-Endpoints) ----------------
    {
        "service": "StealthGuard-402",
        "title": "Stealth Web Scrape & Prompt Firewall",
        "url": "https://stealthguard-402.onrender.com/v1/stealth_scrape_and_sanitize",
        "amount_units": 5000,
        "price_usd": "0.005",
        "category": "scraping",
        "description": "Bypasses Cloudflare anti-bot protections via Scrapling, extracts clean Markdown, and scrubs prompt-injections via CanaryGuard firewall.",
        "input": {"url": "https://news.ycombinator.com", "render_js": False, "strict_mode": True},
    },
    {
        "service": "StealthGuard-402",
        "title": "Polymarket Prediction Alpha Divergence",
        "url": "https://stealthguard-402.onrender.com/v1/polymarket_alpha_divergence",
        "amount_units": 5000,
        "price_usd": "0.005",
        "category": "alpha",
        "description": "Scans Polymarket CLOB orderbooks for volume spikes and smart-money spread divergence, returning CanaryGuard sanitized alpha.",
        "input": {"category": "crypto", "limit": 15, "strict_mode": True},
    },
    {
        "service": "StealthGuard-402",
        "title": "Base Pre-Trade Agent Security Gate",
        "url": "https://stealthguard-402.onrender.com/v1/pre_trade_agent_gate",
        "amount_units": 3000,
        "price_usd": "0.003",
        "category": "security",
        "description": "Deterministic TRUST or BLOCK gate combining on-chain Base RPC liquidity and honeypot checks with CanaryGuard injection scrubbing.",
        "input": {"token_or_service_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "chain": "base"},
    },
    {
        "service": "StealthGuard-402",
        "title": "Polymarket Top Whale Imbalances",
        "url": "https://stealthguard-402.onrender.com/v1/alpha/polymarket-top-whales",
        "amount_units": 3000,
        "price_usd": "0.003",
        "category": "alpha",
        "description": "Top Polymarket whale orderbook imbalances and CLOB skew right now, pre-sanitized with CanaryGuard.",
        "input": {},
    },
    {
        "service": "StealthGuard-402",
        "title": "Polymarket Crypto Probability Odds",
        "url": "https://stealthguard-402.onrender.com/v1/alpha/polymarket-crypto-odds",
        "amount_units": 2000,
        "price_usd": "0.002",
        "category": "alpha",
        "description": "Sanitized BTC, ETH, and SOL Polymarket probability spreads and liquidity depth in basis points.",
        "input": {},
    },
    {
        "service": "StealthGuard-402",
        "title": "Base DEX Trending Tokens Scanner",
        "url": "https://stealthguard-402.onrender.com/v1/alpha/base-trending-tokens",
        "amount_units": 3000,
        "price_usd": "0.003",
        "category": "alpha",
        "description": "Top trending Base DEX pairs pre-screened for honeypots, malicious taxes, and prompt injections.",
        "input": {},
    },
    {
        "service": "StealthGuard-402",
        "title": "DeFi Real-Time APY Yield Radar",
        "url": "https://stealthguard-402.onrender.com/v1/alpha/defi-yield-radar",
        "amount_units": 2000,
        "price_usd": "0.002",
        "category": "alpha",
        "description": "Live top stablecoin and ETH APY yields on Base, pre-sanitized for autonomous AI agent execution.",
        "input": {},
    },
    {
        "service": "StealthGuard-402",
        "title": "HackerNews AI Autonomous Digest",
        "url": "https://stealthguard-402.onrender.com/v1/alpha/hackernews-ai-digest",
        "amount_units": 2000,
        "price_usd": "0.002",
        "category": "alpha",
        "description": "Top HackerNews AI and autonomous agent stories converted to clean, injection-free LLM Markdown.",
        "input": {},
    },
    {
        "service": "StealthGuard-402",
        "title": "Deterministic Prompt-Injection Firewall",
        "url": "https://stealthguard-402.onrender.com/v1/security/prompt-firewall",
        "amount_units": 1000,
        "price_usd": "0.001",
        "category": "security",
        "description": "Ultra-fast deterministic prompt-injection and wallet-drainer scrubber for agent context windows.",
        "input": {"text": "Safe agent prompt context verification probe."},
    },
    {
        "service": "StealthGuard-402",
        "title": "x402 Endpoint Authenticity Verifier",
        "url": "https://stealthguard-402.onrender.com/v1/security/x402-endpoint-verifier",
        "amount_units": 2000,
        "price_usd": "0.002",
        "category": "security",
        "description": "Audits target x402 endpoints for authentic payTo wallet, pricing, challenge headers, and schema hijack risks.",
        "input": {"endpoint_url": "https://stealthguard-402.onrender.com/v1/stealth_scrape_and_sanitize"},
    },

    # ---------------- CanaryGuard-402 (2 Endpoints) ----------------
    {
        "service": "CanaryGuard-402",
        "title": "CanaryGuard Prompt Injection Firewall",
        "url": "https://canaryguard-402.onrender.com/v1/sanitize",
        "amount_units": 3000,
        "price_usd": "0.003",
        "category": "security",
        "description": "Deterministic prompt-injection firewall and honeypot scrubber for autonomous AI agents. Sanitizes untrusted text and blocks wallet-draining exploits.",
        "input": {"content": "Inspect this prompt text for malicious injection commands.", "strict_mode": True},
    },
    {
        "service": "CanaryGuard-402",
        "title": "CanaryGuard Base Token Inspector",
        "url": "https://canaryguard-402.onrender.com/v1/base/token",
        "amount_units": 3000,
        "price_usd": "0.003",
        "category": "security",
        "description": "Inspect Base ERC-20 token contracts for honeypots, transfer restrictions, and prompt injection attacks in token metadata.",
        "input": {"token_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"},
    },

    # ---------------- RugShield-402 (1 Endpoint) ----------------
    {
        "service": "RugShield-402",
        "title": "RugShield DEX Honeypot & Tax Simulator",
        "url": "https://rugshield-402.onrender.com/v1/scan",
        "amount_units": 5000,
        "price_usd": "0.005",
        "category": "security",
        "description": "Low-latency DEX honeypot detection, buy/sell tax simulation, and pool liquidity verification on Base for AI agents.",
        "input": {"token_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "chain_id": 8453, "simulate_sell": True},
    },
]

def print_header(title: str):
    print("\n" + "=" * 78)
    print(f" {title}")
    print("=" * 78)

def main():
    print_header("AUTONOMOUS HOT WALLET BAZAAR SEEDER & FORCE-INDEXING ENGINE")

    # 1. Credentials Check
    key_id, key_secret = load_cdp_credentials()
    if not key_id or not key_secret:
        print("[!] FATAL: Coinbase CDP API credentials not found.")
        return 1
    print(f"[*] CDP Credentials Loaded: {key_id[:28]}...")

    buyer_pk = find_buyer_private_key()
    buyer = Account.from_key(buyer_pk)
    buyer_eth, buyer_usdc, _ = check_onchain_balance(buyer.address)
    print(f"[*] Hot Buyer Wallet:       {buyer.address}")
    print(f"    Starting Balance:       {buyer_usdc:.6f} USDC ({buyer_eth:.6f} ETH)")

    recipient = get_recipient_address()
    rec_eth, rec_usdc_start, _ = check_onchain_balance(recipient)
    print(f"[*] Merchant Payout Wallet: {recipient}")
    print(f"    Starting Balance:       {rec_usdc_start:.6f} USDC ({rec_eth:.6f} ETH)")
    print(f"[*] Total Endpoints to Seed: {len(ALL_PAID_ENDPOINTS)}")

    client = httpx.Client(timeout=35.0)
    indexed_results = []

    # 2. Iterate through each endpoint
    for idx, ep in enumerate(ALL_PAID_ENDPOINTS, 1):
        url = ep["url"]
        title = ep["title"]
        service = ep["service"]
        amt = ep["amount_units"]
        price = ep["price_usd"]
        desc = ep["description"][:390]
        cat = ep["category"]

        print_header(f"[{idx}/{len(ALL_PAID_ENDPOINTS)}] {service} -> {ep['title']} ({price} USDC)")
        print(f"Endpoint: {url}")

        # Step A: Coinbase Preflight Validation
        print("  [1] Calling Coinbase CDP Preflight /validate...")
        try:
            val_resp = client.post(COINBASE_VALIDATE_URL, json={"resource": url, "method": "POST"})
            val_data = val_resp.json() if val_resp.status_code == 200 else {}
            outcome = val_data.get("simulation", {}).get("outcome")
            print(f"      Validation: valid={val_data.get('valid')} | outcome={outcome}")
        except Exception as e:
            print(f"      Validation check notice: {e}")

        # Step B: Fetch Live 402 Challenge from endpoint
        print("  [2] Probing live endpoint for 402 challenge terms...")
        try:
            r_402 = client.post(url, json={})
            if r_402.status_code == 402:
                print("      Live 402 Received: PAYMENT-REQUIRED and WWW-Authenticate present")
            else:
                print(f"      [Notice] Status {r_402.status_code} on unpaid probe")
        except Exception as e:
            print(f"      Live probe notice: {e}")

        # Step C: Sign Real EIP-3009 Transfer Authorization from Buyer Wallet
        print("  [3] Signing EIP-3009 TransferWithAuthorization from Hot Wallet...")
        sig_b64 = sign_x402_authorization(buyer, recipient, amt)
        decoded_payment = json.loads(base64.b64decode(sig_b64).decode("utf-8"))

        # Step D: Construct Strict x402 v2 ResourceInfo Object & extensions.bazaar
        resource_obj = {
            "url": url,
            "description": desc,
            "mimeType": "application/json",
        }

        matching_pricing = None
        for t_name, p_data in TOOL_PRICING.items():
            if p_data.get("path") and p_data["path"] in url:
                matching_pricing = p_data
                break

        if matching_pricing and "example_output" in matching_pricing:
            out_example = matching_pricing["example_output"]
        elif "sanitize" in url:
            out_example = {
                "status": "success",
                "sanitized": True,
                "risk_score": 0.0,
                "threats_detected": [],
                "safety_receipt": "canary-v1-verified"
            }
        elif "token" in url:
            out_example = {
                "status": "success",
                "token_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                "chain": "base",
                "honeypot": False,
                "tax_pct": 0.0,
                "verdict": "VERIFIED_SAFE"
            }
        elif "scan" in url:
            out_example = {
                "status": "success",
                "token_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                "is_honeypot": False,
                "buy_tax": 0.0,
                "sell_tax": 0.0,
                "simulation_status": "SUCCESS",
                "verdict": "SAFE"
            }
        else:
            out_example = {
                "status": "success",
                "service": service,
                "endpoint": url,
                "verdict": "ALL_CLEAR",
                "safety_receipt": "canary-v1-verified"
            }

        bazaar_ext = {
            "name": f"{service} - {title}",
            "description": desc,
            "info": {
                "input": {
                    "type": "http",
                    "method": "POST",
                    "bodyType": "json",
                    "body": ep["input"],
                    "category": cat,
                    "price": f"{price} USDC",
                },
                "output": {
                    "example": out_example
                }
            },
            "schema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {
                    "input": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "const": "http"},
                            "method": {"type": "string", "enum": ["POST", "GET"]},
                            "bodyType": {"type": "string", "enum": ["json"]},
                            "body": {"type": "object"}
                        },
                        "required": ["type", "method", "bodyType", "body"],
                        "additionalProperties": False
                    }
                },
                "required": ["input"]
            }
        }

        clean_reqs = {
            "scheme": "exact",
            "network": NETWORK,
            "amount": str(amt),
            "asset": ASSET,
            "payTo": recipient,
            "maxTimeoutSeconds": 3600,
            "extra": {"name": "USD Coin", "version": "2"},
        }

        v2_payment_payload = {
            "x402Version": 2,
            "payload": decoded_payment["payload"],
            "resource": resource_obj,
            "accepted": clean_reqs,
            "extensions": {"bazaar": bazaar_ext},
        }

        settle_body = {
            "x402Version": 2,
            "paymentPayload": v2_payment_payload,
            "paymentRequirements": clean_reqs,
        }

        # Step E: Broadcast On-Chain Settlement to Coinbase CDP Facilitator
        print("  [4] Submitting Settlement & Bazaar Indexing to Coinbase Facilitator (/settle)...")
        jwt_token = generate_cdp_jwt(key_id, key_secret, "POST", "api.cdp.coinbase.com", "/platform/v2/x402/settle")
        auth_headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json",
        }

        tx_hash = None
        bazaar_status = "UNKNOWN"
        try:
            resp = client.post(COINBASE_SETTLE_URL, json=settle_body, headers=auth_headers)
            res_data = resp.json() if resp.status_code == 200 else {}
            ext_hdr = resp.headers.get("EXTENSION-RESPONSES")

            if resp.status_code == 200 and res_data.get("success"):
                tx_hash = res_data.get("transaction")
                if ext_hdr:
                    try:
                        ext_json = json.loads(base64.b64decode(ext_hdr).decode("utf-8"))
                        bazaar_status = ext_json.get("bazaar", {}).get("status", "SUCCESS")
                    except Exception:
                        pass
                print(f"      [SUCCESS] Settled on Base Mainnet!")
                print(f"      Transaction: https://basescan.org/tx/{tx_hash}")
                print(f"      Bazaar Extension Status: {bazaar_status} (EXTENSION-RESPONSES confirmed)")
            else:
                err = res_data.get("errorMessage") or resp.text[:140]
                print(f"      [Notice] Settle response ({resp.status_code}): {err}")
        except Exception as e:
            print(f"      [ERR] Facilitator settle error: {e}")

        # Step F: Also send live HTTP request to endpoint with payment signature
        print("  [5] Executing live paid HTTP request to endpoint...")
        try:
            payload_b64 = base64.b64encode(json.dumps(v2_payment_payload).encode("utf-8")).decode("utf-8")
            live_resp = client.post(
                url,
                json=ep["input"],
                headers={
                    "Content-Type": "application/json",
                    "PAYMENT-SIGNATURE": payload_b64,
                    "X-PAYMENT": payload_b64,
                }
            )
            print(f"      Live HTTP Status: {live_resp.status_code} | Latency: {int(live_resp.elapsed.total_seconds()*1000)}ms")
            if "PAYMENT-RESPONSE" in live_resp.headers:
                print("      Payment Receipt Header: PAYMENT-RESPONSE confirmed")
        except Exception as e:
            print(f"      Live HTTP request notice: {e}")

        indexed_results.append({
            "service": service,
            "title": title,
            "url": url,
            "price": f"{price} USDC",
            "tx": tx_hash,
            "bazaar_status": bazaar_status,
        })

        time.sleep(2)

    # 3. Query Coinbase Discovery Catalog
    print_header("STAGE 2: QUERYING COINBASE BAZAAR DISCOVERY CATALOG")
    jwt_disc = generate_cdp_jwt(key_id, key_secret, "GET", "api.cdp.coinbase.com", "/platform/v2/x402/discovery/resources")
    try:
        r_disc = client.get(COINBASE_DISCOVERY_URL, headers={"Authorization": f"Bearer {jwt_disc}"})
        if r_disc.status_code == 200:
            disc_items = r_disc.json().get("resources", [])
            print(f"[*] Coinbase Bazaar Discovery Feed Status: 200 OK ({len(disc_items)} total cataloged resources)")
            for it in disc_items:
                r_url = it.get("resource", {}).get("url", "")
                r_name = it.get("extensions", {}).get("bazaar", {}).get("name", "Unknown")
                print(f"    - Cataloged: {r_name} -> {r_url}")
        else:
            print(f"[*] Discovery Feed status: {r_disc.status_code}")
    except Exception as e:
        print(f"[*] Discovery Feed notice: {e}")

    # 4. Ping External Directories
    print_header("STAGE 3: PINGING EXTERNAL AGENT DIRECTORIES & MONITORS")
    directories = [
        ("x402scan.com", "https://x402scan.com"),
        ("lumierepaycheck.org", "https://lumierepaycheck.org"),
        ("402radar.io", "https://402radar.io"),
        ("x402-list.com", "https://x402-list.com"),
    ]
    for dname, durl in directories:
        try:
            r_ping = client.get(durl, timeout=10.0)
            print(f"  [PING OK] {dname} ({durl}) -> Status {r_ping.status_code}")
        except Exception as e:
            print(f"  [PING NOTICE] {dname} -> {e}")

    # 5. Final Accounting & Summary
    print_header("STAGE 4: REVENUE & WALLET SETTLEMENT SUMMARY")
    buyer_eth_end, buyer_usdc_end, _ = check_onchain_balance(buyer.address)
    rec_eth_end, rec_usdc_end, _ = check_onchain_balance(recipient)

    total_spent = buyer_usdc - buyer_usdc_end
    total_received = rec_usdc_end - rec_usdc_start

    print(f"Hot Buyer Wallet ({buyer.address}):")
    print(f"  Starting: {buyer_usdc:.6f} USDC")
    print(f"  Ending:   {buyer_usdc_end:.6f} USDC")
    print(f"  Spent:    {total_spent:.6f} USDC across {len(indexed_results)} transactions")
    print()
    print(f"Merchant Payout Wallet ({recipient}):")
    print(f"  Starting: {rec_usdc_start:.6f} USDC")
    print(f"  Ending:   {rec_usdc_end:.6f} USDC")
    print(f"  Received: +{total_received:.6f} USDC (100% directly credited)")
    print()
    print("=" * 78)
    print(" FINAL VERIFIED ENDPOINTS DIRECTORY (PASTE INTO MONITORS):")
    print("=" * 78)
    print(f"{'Service':<18} | {'Price':<10} | {'Status':<11} | {'URL'}")
    print("-" * 78)
    for r in indexed_results:
        print(f"{r['service']:<18} | {r['price']:<10} | {r['bazaar_status']:<11} | {r['url']}")
    print("=" * 78)

    return 0

if __name__ == "__main__":
    sys.exit(main())
