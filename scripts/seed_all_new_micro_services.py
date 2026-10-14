#!/usr/bin/env python3
"""
scripts/seed_all_new_micro_services.py
Executes REAL ON-CHAIN paid settlements on Base Mainnet (eip155:8453)
via the Coinbase CDP Facilitator v2 (/settle) for the new micro-services:
1. /v1/alpha/polymarket-top-whales ($0.003 USDC)
2. /v1/alpha/polymarket-crypto-odds ($0.002 USDC)
3. /v1/alpha/base-trending-tokens ($0.003 USDC)
4. /v1/security/prompt-firewall ($0.001 USDC)
5. https://rugshield-402.onrender.com/v1/scan ($0.005 USDC)
6. https://canaryguard-402.onrender.com/v1/sanitize ($0.003 USDC)

Deposits real Base native USDC from buyer hot wallet 0x6b5f275F028A214fb2e6d21061db791E3b07BEeD
into recipient payout wallet 0x73279fa4BadA7CAC888c62CDa4f5c8104765f6f1.
"""

import sys
import os
import json
import time
import secrets
import urllib.request
from pathlib import Path
from eth_account import Account
from eth_account.messages import encode_typed_data
import httpx

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import ASSET, CHAIN_ID, NETWORK, get_recipient_address, get_public_url
from src.x402_middleware import load_cdp_credentials, generate_cdp_jwt, build_bazaar_extension

RECIPIENT = get_recipient_address()
USDC_ASSET = ASSET
BASE_CHAIN_ID = CHAIN_ID

SERVICES_TO_SEED = [
    {
        "name": "polymarket_top_whales",
        "resource": f"{get_public_url()}/v1/alpha/polymarket-top-whales",
        "description": "Top 10 Polymarket whale orderbook imbalances and CLOB skew right now",
        "amount_units": 3000,
        "amount_usd": "0.003",
    },
    {
        "name": "polymarket_crypto_odds",
        "resource": f"{get_public_url()}/v1/alpha/polymarket-crypto-odds",
        "description": "Sanitized BTC/ETH/SOL Polymarket odds, probability spreads, and liquidity depth",
        "amount_units": 2000,
        "amount_usd": "0.002",
    },
    {
        "name": "base_trending_tokens",
        "resource": f"{get_public_url()}/v1/alpha/base-trending-tokens",
        "description": "Top trending Base DEX pairs (DexScreener) pre-screened for honeypots and prompt injections",
        "amount_units": 3000,
        "amount_usd": "0.003",
    },
    {
        "name": "security_prompt_firewall",
        "resource": f"{get_public_url()}/v1/security/prompt-firewall",
        "description": "Ultra-fast $0.001 deterministic prompt-injection & wallet-drainer scrubber for raw agent context",
        "amount_units": 1000,
        "amount_usd": "0.001",
    },
    {
        "name": "rugshield_honeypot_scan",
        "resource": "https://rugshield-402.onrender.com/v1/scan",
        "description": "Low-latency token honeypot detection & buy/sell tax simulation on Base for AI trading agents",
        "amount_units": 5000,
        "amount_usd": "0.005",
    },
    {
        "name": "canaryguard_sanitization",
        "resource": "https://canaryguard-402.onrender.com/v1/sanitize",
        "description": "Multi-layer deterministic prompt-injection firewall and token extraction gate",
        "amount_units": 3000,
        "amount_usd": "0.003",
    },
]

def find_buyer_private_key() -> str:
    pk = os.getenv("BUYER_PRIVATE_KEY") or os.getenv("WALLET_B_PRIVATE_KEY")
    if pk:
        return pk.strip()

    candidate_files = [
        Path(__file__).parent.parent.parent / "canaryguard-402" / ".env.local",
        Path(__file__).parent.parent.parent / "rugshield-402" / ".env.local",
        Path(__file__).parent.parent / ".env.local",
        Path(__file__).parent.parent / ".env",
    ]
    for cpath in candidate_files:
        if cpath.exists():
            with open(cpath, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("BUYER_PRIVATE_KEY=") or line.startswith("WALLET_B_PRIVATE_KEY="):
                        val = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            return val
    raise ValueError("BUYER_PRIVATE_KEY not found in environment or local .env files.")

def get_usdc_balance(wallet_address: str) -> int:
    from eth_abi import encode as abi_encode
    selector = bytes.fromhex("70a08231")
    calldata = "0x" + (selector + abi_encode(["address"], [wallet_address])).hex()
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call", "params": [{"to": USDC_ASSET, "data": calldata}, "latest"]}).encode()
    req = urllib.request.Request("https://mainnet.base.org", data=payload, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode())
    return int(res.get("result", "0x0"), 16)

def sign_eip3009_auth(payer: Account, recipient: str, amount_units: int) -> dict:
    now = int(time.time())
    nonce_bytes = secrets.token_bytes(32)
    nonce_hex = "0x" + nonce_bytes.hex()

    types = {
        "EIP712Domain": [
            {"name": "name", "type": "string"},
            {"name": "version", "type": "string"},
            {"name": "chainId", "type": "uint256"},
            {"name": "verifyingContract", "type": "address"},
        ],
        "TransferWithAuthorization": [
            {"name": "from", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
            {"name": "validAfter", "type": "uint256"},
            {"name": "validBefore", "type": "uint256"},
            {"name": "nonce", "type": "bytes32"},
        ],
    }

    domain = {
        "name": "USD Coin",
        "version": "2",
        "chainId": BASE_CHAIN_ID,
        "verifyingContract": USDC_ASSET,
    }

    message = {
        "from": payer.address,
        "to": recipient,
        "value": amount_units,
        "validAfter": 0,
        "validBefore": now + 3600,
        "nonce": nonce_bytes,
    }

    signable = encode_typed_data(full_message={
        "types": types,
        "primaryType": "TransferWithAuthorization",
        "domain": domain,
        "message": message,
    })

    signed = payer.sign_message(signable)
    sig_hex = signed.signature.hex()
    if not sig_hex.startswith("0x"):
        sig_hex = "0x" + sig_hex

    return {
        "signature": sig_hex,
        "authorization": {
            "from": payer.address,
            "to": recipient,
            "value": str(amount_units),
            "validAfter": "0",
            "validBefore": str(now + 3600),
            "nonce": nonce_hex,
        }
    }

def settle_via_cdp(auth_payload: dict, service_meta: dict) -> dict:
    key_id, key_secret = load_cdp_credentials()
    if not key_id or not key_secret:
        raise RuntimeError("CDP credentials not loaded")

    host = "api.cdp.coinbase.com"
    path = "/platform/v2/x402/settle"
    url = f"https://{host}{path}"

    token = generate_cdp_jwt(key_id, key_secret, "POST", host, path)
    headers = {
        "Authorization": f"Bearer {token}",
        "Correlation-Context": "sdk_version=1.29.0,sdk_language=python,source=x402,source_version=2.1.0",
        "Content-Type": "application/json",
    }

    bazaar_ext = build_bazaar_extension(
        tool_name=service_meta["name"],
        description=service_meta["description"],
        mode="http"
    )

    payment_requirements = {
        "scheme": "exact",
        "network": NETWORK,
        "amount": str(service_meta["amount_units"]),
        "asset": USDC_ASSET,
        "payTo": RECIPIENT,
        "maxTimeoutSeconds": 300,
        "extra": {"name": "USD Coin", "version": "2"},
        "resource": service_meta["resource"],
        "description": service_meta["description"],
        "mimeType": "application/json",
        "extensions": bazaar_ext,
    }

    payment_payload = {
        "x402Version": 2,
        "accepted": payment_requirements,
        "payload": auth_payload,
    }

    body = {
        "x402Version": 2,
        "paymentPayload": payment_payload,
        "paymentRequirements": payment_requirements,
    }

    with httpx.Client(timeout=35.0) as client:
        resp = client.post(url, json=body, headers=headers)
        return resp.json()

def main():
    print("=" * 70)
    print("REAL ON-CHAIN SETTLEMENT FOR NEW MICRO-SERVICES ON BASE MAINNET")
    print("=" * 70)

    pk = find_buyer_private_key()
    payer = Account.from_key(pk)
    print(f"Buyer Hot Wallet: {payer.address}")
    print(f"Payout Recipient Wallet: {RECIPIENT}")

    initial_balance = get_usdc_balance(payer.address)
    print(f"Initial Hot Wallet Balance: {initial_balance / 1e6:.6f} USDC ({initial_balance} micro-units)")

    total_cost = sum(s["amount_units"] for s in SERVICES_TO_SEED)
    print(f"Total USDC to settle across {len(SERVICES_TO_SEED)} services: {total_cost / 1e6:.6f} USDC")

    settlements = []
    for s in SERVICES_TO_SEED:
        print(f"\n---> Settling {s['name']} (${s['amount_usd']} USDC) -> {s['resource']}")
        auth = sign_eip3009_auth(payer, RECIPIENT, s["amount_units"])
        
        try:
            res = settle_via_cdp(auth, s)
            success = res.get("success", False)
            tx = res.get("transaction")
            
            if success and tx:
                basescan = f"https://basescan.org/tx/{tx}"
                print(f"  [SUCCESS] On-chain tx: {tx}")
                print(f"  BaseScan: {basescan}")
                settlements.append({
                    "service": s["name"],
                    "resource": s["resource"],
                    "amount_usdc": s["amount_usd"],
                    "amount_units": s["amount_units"],
                    "status": "SUCCESS",
                    "transaction_hash": tx,
                    "basescan_url": basescan,
                    "settled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                })
            else:
                err = res.get("errorMessage") or res.get("error") or str(res)
                print(f"  [FAILED] {err}")
                settlements.append({
                    "service": s["name"],
                    "resource": s["resource"],
                    "status": "FAILED",
                    "error": str(err),
                })
        except Exception as e:
            print(f"  [EXCEPTION] {e}")
            settlements.append({
                "service": s["name"],
                "resource": s["resource"],
                "status": "EXCEPTION",
                "error": str(e),
            })
        time.sleep(2)

    final_balance = get_usdc_balance(payer.address)
    payout_balance = get_usdc_balance(RECIPIENT)
    print("\n" + "=" * 70)
    print(f"FINAL HOT WALLET BALANCE: {final_balance / 1e6:.6f} USDC")
    print(f"FINAL PAYOUT WALLET BALANCE: {payout_balance / 1e6:.6f} USDC")
    print(f"TOTAL SETTLED: {len([s for s in settlements if s.get('status') == 'SUCCESS'])}/{len(SERVICES_TO_SEED)}")
    print("=" * 70)

    # Save to state
    out_path = Path(__file__).parent.parent / "state" / "micro_services_settlement_receipts.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "buyer_hot_wallet": payer.address,
            "payout_recipient": RECIPIENT,
            "network": "eip155:8453",
            "settlements": settlements,
        }, f, indent=2)
    print(f"Receipts saved to: {out_path}")

if __name__ == "__main__":
    main()
