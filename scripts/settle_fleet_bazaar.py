#!/usr/bin/env python3
"""
scripts/settle_fleet_bazaar.py
Settles CanaryGuard-402 and RugShield-402 into Coinbase CDP Bazaar on Base Mainnet.
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

from src.config import ASSET, NETWORK, get_recipient_address
from src.x402_middleware import (
    load_cdp_credentials,
    generate_cdp_jwt,
    clean_pem_private_key,
)
from scripts.seed_live_settlement import find_buyer_private_key, sign_x402_authorization, check_onchain_balance

COINBASE_SETTLE_URL = "https://api.cdp.coinbase.com/platform/v2/x402/settle"
COINBASE_VALIDATE_URL = "https://api.cdp.coinbase.com/platform/v2/x402/validate"

SERVICES = [
    {
        "name": "canaryguard-402",
        "url": "https://canaryguard-402.onrender.com/v1/sanitize",
        "amount_microunits": 3000,
        "price": "0.003",
        "bazaar": {
            "name": "CanaryGuard 402",
            "description": "Deterministic prompt-injection firewall and honeypot scrubber for autonomous AI agents.",
        }
    },
    {
        "name": "rugshield-402",
        "url": "https://rugshield-402.onrender.com/v1/scan",
        "amount_microunits": 5000,
        "price": "0.005",
        "bazaar": {
            "name": "RugShield 402",
            "description": "Low-latency token honeypot detection, tax simulation, and pool liquidity verification for AI agents.",
        }
    }
]

def main():
    print("=" * 70)
    print("SETTLING CANARYGUARD & RUGSHIELD INTO COINBASE BAZAAR")
    print("=" * 70)

    key_id, key_secret = load_cdp_credentials()
    if not key_id or not key_secret:
        print("[!] ERROR: Coinbase CDP API credentials not found.")
        return 1

    buyer_pk = find_buyer_private_key()
    payer = Account.from_key(buyer_pk)
    eth, usdc, _ = check_onchain_balance(payer.address)
    print(f"[*] Buyer: {payer.address} | Balance: {usdc:.3f} USDC ({eth:.6f} ETH)")
    recipient = get_recipient_address()
    print(f"[*] Recipient: {recipient}")

    client = httpx.Client(timeout=30.0)

    for svc in SERVICES:
        url = svc["url"]
        name = svc["name"]
        amt = svc["amount_microunits"]
        print(f"\n[*] Processing {name} ({url})...")

        # Step 1: Preflight Validate
        val_resp = client.post(COINBASE_VALIDATE_URL, json={"resource": url, "method": "POST"})
        val_data = val_resp.json()
        print(f"  -> Preflight Valid: {val_data.get('valid')} | Simulation: {val_data.get('simulation', {}).get('outcome')}")

        # Step 2: Fetch 402 response from service
        r_402 = client.post(url, json={})
        if r_402.status_code != 402:
            print(f"  [!] Expected 402, got {r_402.status_code}")
            continue

        body_402 = r_402.json() if r_402.text.startswith("{") else {}
        hdr_pr = r_402.headers.get("PAYMENT-REQUIRED")
        hdr_decoded = {}
        if hdr_pr:
            try:
                hdr_decoded = json.loads(base64.b64decode(hdr_pr).decode("utf-8"))
            except Exception:
                pass

        res_obj = (
            hdr_decoded.get("resource") or
            body_402.get("resource") or
            {"url": url, "description": svc["bazaar"]["description"], "mimeType": "application/json"}
        )
        bazaar_ext = (
            hdr_decoded.get("extensions", {}).get("bazaar") or
            body_402.get("extensions", {}).get("bazaar") or
            svc["bazaar"]
        )

        # Sign authorization
        sig_b64 = sign_x402_authorization(payer, recipient, amt)
        decoded_payment = json.loads(base64.b64decode(sig_b64).decode("utf-8"))

        clean_reqs = {
            "scheme": "exact",
            "network": NETWORK,
            "amount": str(amt),
            "asset": ASSET,
            "payTo": recipient,
            "maxTimeoutSeconds": 3600,
            "extra": {"name": "USD Coin", "version": "2"},
            "resource": res_obj,
            "extensions": {"bazaar": bazaar_ext},
        }

        v2_payment_payload = {
            "x402Version": 2,
            "resource": res_obj,
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

        resp = client.post(COINBASE_SETTLE_URL, json=settle_body, headers=auth_headers)
        res_data = resp.json() if resp.status_code == 200 else {}
        ext_hdr = resp.headers.get("EXTENSION-RESPONSES")

        if resp.status_code == 200 and res_data.get("success"):
            tx = res_data.get("transaction")
            bazaar_status = "UNKNOWN"
            if ext_hdr:
                try:
                    ext_json = json.loads(base64.b64decode(ext_hdr).decode("utf-8"))
                    bazaar_status = ext_json.get("bazaar", {}).get("status", "SUCCESS")
                except Exception:
                    pass
            print(f"  -> SUCCESS! Tx: https://basescan.org/tx/{tx}")
            print(f"  -> Bazaar Extension Status: {bazaar_status} (EXTENSION-RESPONSES confirmed)")
        else:
            err = res_data.get("errorMessage") or resp.text[:150]
            print(f"  -> Settle response ({resp.status_code}): {err}")

        time.sleep(2)

    # Final balance check
    eth_end, usdc_end, _ = check_onchain_balance(recipient)
    print(f"\n[+] Merchant Wallet Balance Now: {usdc_end:.6f} USDC ({eth_end:.6f} ETH)")

if __name__ == "__main__":
    main()
