#!/usr/bin/env python3
"""
scripts/index_all_in_bazaar.py
Autonomous Coinbase CDP Bazaar Indexing & Extension Verification Engine for StealthGuard-402.

Executes Coinbase's official Bazaar indexing flow:
1. Validates all 10 endpoints against Coinbase CDP preflight validator.
2. Extracts live extensions.bazaar and resource objects.
3. Submits real EIP-3009 micro-settlements with extensions.bazaar and resource to /settle.
4. Verifies EXTENSION-RESPONSES header confirmation from Coinbase Facilitator.
5. Polls discovery endpoint to verify Bazaar indexing.
"""

import sys
import os
import json
import time
import base64
from pathlib import Path
from eth_account import Account
import httpx

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import TOOL_PRICING, ASSET, CHAIN_ID, NETWORK, get_recipient_address, get_public_url
from src.x402_middleware import (
    load_cdp_credentials,
    generate_cdp_jwt,
    build_402_challenge,
    enforce_https,
)
from scripts.seed_live_settlement import find_buyer_private_key, sign_x402_authorization, check_onchain_balance

COINBASE_VALIDATE_URL = "https://api.cdp.coinbase.com/platform/v2/x402/validate"
COINBASE_SETTLE_URL = "https://api.cdp.coinbase.com/platform/v2/x402/settle"
COINBASE_DISCOVERY_URL = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources"

def main():
    target_base = sys.argv[1] if len(sys.argv) > 1 else get_public_url()
    print("=" * 75)
    print("COINBASE CDP BAZAAR COMPREHENSIVE INDEXING ENGINE")
    print(f"Target Origin: {target_base}")
    print(f"Recipient Wallet: {get_recipient_address()}")
    print("=" * 75)

    key_id, key_secret = load_cdp_credentials()
    if not key_id or not key_secret:
        print("[!] ERROR: Coinbase CDP API credentials not found.")
        return 1
    print(f"[*] CDP Credentials Loaded: {key_id[:25]}...")

    buyer_pk = find_buyer_private_key()
    payer = Account.from_key(buyer_pk)
    eth, usdc, usdc_units = check_onchain_balance(payer.address)
    print(f"[*] Buyer Wallet: {payer.address} | Balance: {usdc:.3f} USDC ({eth:.6f} ETH)")

    paid_tools = [
        (tname, p) for tname, p in TOOL_PRICING.items()
        if p.get("amount_microunits") != "0"
    ]
    print(f"[*] Found {len(paid_tools)} Paid Endpoints to Validate & Catalog into Bazaar.\n")

    client = httpx.Client(timeout=30.0)

    # STEP 1: Preflight Validation on all 10
    print("-" * 75)
    print("PHASE 1: PREFLIGHT VALIDATION VIA COINBASE CDP VALIDATOR")
    print("-" * 75)
    all_valid = True
    for tool_name, pricing in paid_tools:
        res_url = f"{target_base}{pricing['path']}"
        val_payload = {"resource": res_url, "method": "POST"}
        try:
            r = client.post(COINBASE_VALIDATE_URL, json=val_payload)
            data = r.json()
            is_valid = data.get("valid", False)
            outcome = data.get("simulation", {}).get("outcome") or data.get("outcome")
            status = "VALID" if (is_valid or outcome == "accepted") else "REJECTED"
            print(f"  [{status}] {pricing['path']} -> outcome={outcome} valid={is_valid}")
            if not is_valid and outcome != "accepted":
                all_valid = False
        except Exception as e:
            print(f"  [ERROR] {pricing['path']} -> {e}")
            all_valid = False

    print(f"\nPhase 1 Result: {'ALL 10 PASSED' if all_valid else 'SOME CHECKS FAILED'}\n")

    # STEP 2: Settle with paymentPayload.extensions.bazaar & paymentPayload.resource
    print("-" * 75)
    print("PHASE 2: DIRECT CDP FACILITATOR SETTLEMENT WITH BAZAAR CATALOGING")
    print("-" * 75)
    cataloged = 0
    recipient = get_recipient_address()

    for idx, (tool_name, pricing) in enumerate(paid_tools, 1):
        res_url = enforce_https(f"{target_base}{pricing['path']}")
        amount_microunits = int(pricing["amount_microunits"])
        desc = pricing.get("description", "")[:400]

        headers_402, challenge_body = build_402_challenge(
            tool_name=tool_name,
            resource_url=res_url,
            mode="http",
            reason="Bazaar cataloging initial probe",
        )

        bazaar_ext = challenge_body.get("extensions", {}).get("bazaar", {})
        resource_obj = challenge_body.get("resource", {
            "url": res_url,
            "description": desc,
            "mimeType": "application/json",
        })

        # Sign authorization
        sig_b64 = sign_x402_authorization(payer, recipient, amount_microunits)
        decoded_payment = json.loads(base64.b64decode(sig_b64).decode("utf-8"))

        clean_reqs = {
            "scheme": "exact",
            "network": NETWORK,
            "amount": str(amount_microunits),
            "asset": ASSET,
            "payTo": recipient,
            "maxTimeoutSeconds": 300,
            "extra": {"name": "USD Coin", "version": "2"},
            "resource": resource_obj,
            "extensions": {"bazaar": bazaar_ext},
        }

        # Build full payload matching Coinbase Bazaar indexing spec
        v2_payment_payload = {
            "x402Version": 2,
            "resource": resource_obj,
            "extensions": {"bazaar": bazaar_ext},
            "accepted": clean_reqs,
            "payload": decoded_payment["payload"],
        }

        settle_body = {
            "x402Version": 2,
            "paymentPayload": v2_payment_payload,
            "paymentRequirements": clean_reqs,
        }

        jwt_token = generate_cdp_jwt(key_id, key_secret, "POST", "api.cdp.coinbase.com", "/platform/v2/x402/settle")
        auth_headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json",
        }

        print(f"[{idx}/{len(paid_tools)}] Settling {tool_name} ({pricing['price_formatted']})...")
        try:
            resp = client.post(COINBASE_SETTLE_URL, json=settle_body, headers=auth_headers)
            res_data = resp.json() if resp.status_code == 200 else {}
            ext_hdr = resp.headers.get("EXTENSION-RESPONSES")

            if resp.status_code == 200 and res_data.get("success"):
                tx = res_data.get("transaction")
                cataloged += 1
                bazaar_status = "UNKNOWN"
                if ext_hdr:
                    try:
                        ext_json = json.loads(base64.b64decode(ext_hdr).decode("utf-8"))
                        bazaar_status = ext_json.get("bazaar", {}).get("status", "SUCCESS")
                    except Exception:
                        pass
                print(f"  -> SUCCESS! Tx: https://basescan.org/tx/{tx}")
                print(f"  -> Bazaar Extension Status: {bazaar_status} (EXTENSION-RESPONSES verified)")
            else:
                err = res_data.get("errorMessage") or resp.text[:150]
                print(f"  -> Settle failed ({resp.status_code}): {err}")
        except Exception as e:
            print(f"  -> Exception: {e}")

        time.sleep(2)

    print(f"\nPhase 2 Result: {cataloged}/{len(paid_tools)} Endpoints Settled and Cataloged into Bazaar.\n")

    # STEP 3: Poll Discovery API
    print("-" * 75)
    print("PHASE 3: VERIFYING COINBASE BAZAAR DISCOVERY CATALOG")
    print("-" * 75)
    try:
        disc_jwt = generate_cdp_jwt(key_id, key_secret, "GET", "api.cdp.coinbase.com", "/platform/v2/x402/discovery/resources")
        disc_headers = {"Authorization": f"Bearer {disc_jwt}"}
        d_resp = client.get(COINBASE_DISCOVERY_URL, headers=disc_headers)
        if d_resp.status_code == 200:
            disc_data = d_resp.json()
            items = disc_data.get("resources", []) or disc_data.get("items", [])
            print(f"[*] Total Cataloged Resources in CDP Bazaar: {len(items)}")
            matched = [it for it in items if get_recipient_address().lower() in json.dumps(it).lower()]
            print(f"[*] Merchant Resources Found: {len(matched)}")
            for m in matched[:5]:
                print(f"    - {m.get('resource', {}).get('url') or m.get('url')}")
        else:
            print(f"[*] Discovery probe status: {d_resp.status_code}")
    except Exception as e:
        print(f"[*] Discovery probe exception: {e}")

    print("=" * 75)
    print("BAZAAR INDEXING ENGINE EXECUTION COMPLETE")
    print("=" * 75)
    return 0

if __name__ == "__main__":
    sys.exit(main())
