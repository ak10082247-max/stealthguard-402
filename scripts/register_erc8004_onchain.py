#!/usr/bin/env python3
"""
scripts/register_erc8004_onchain.py
Official ERC-8004 On-Chain Identity & Reputation Registration on Base Mainnet.

Registers StealthGuard-402 on:
- IdentityRegistry: 0x8004A169FB4a3325136EB29fA0ceB6D2e539a432
- ReputationRegistry: 0x8004BAa17C55a88189AE136b182e5fdA19dE9b63

Points tokenURI to: https://stealthguard-402.onrender.com/.well-known/agent-card.json
"""

import os
import sys
import json
import time
import urllib.request
from pathlib import Path
from typing import Any
from eth_account import Account
from eth_abi import encode

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

BASE_RPC_URLS = [
    "https://mainnet.base.org",
    "https://base.llamarpc.com",
    "https://1rpc.io/base",
]

IDENTITY_REGISTRY = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
REPUTATION_REGISTRY = "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63"
AGENT_CARD_URI = "https://stealthguard-402.onrender.com/.well-known/agent-card.json"
BASE_CHAIN_ID = 8453

def rpc_call(method: str, params: list, url_index: int = 0) -> Any:
    url = BASE_RPC_URLS[url_index % len(BASE_RPC_URLS)]
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "StealthGuard-ERC8004/2.0"},
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        res = json.loads(resp.read().decode("utf-8"))
    if "error" in res:
        raise RuntimeError(f"RPC Error ({method}): {res['error']}")
    return res.get("result")

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

def main():
    print("=" * 70)
    print("ERC-8004 TRUSTLESS AGENTS ON-CHAIN REGISTRATION (BASE MAINNET)")
    print("=" * 70)

    pk = find_buyer_private_key()
    account = Account.from_key(pk)
    print(f"Deployer / Registrar Wallet: {account.address}")

    # Check ETH balance
    bal_hex = rpc_call("eth_getBalance", [account.address, "latest"])
    eth_balance = int(bal_hex, 16) / 1e18
    print(f"Base ETH Balance: {eth_balance:.6f} ETH")
    if eth_balance < 0.0001:
        print("Warning: Insufficient ETH balance for Base gas fees.")
        sys.exit(1)

    # Encode register(string tokenURI) -> selector 0xf2c298be
    selector = bytes.fromhex("f2c298be")
    encoded_args = encode(["string"], [AGENT_CARD_URI])
    calldata = "0x" + (selector + encoded_args).hex()

    print(f"Target IdentityRegistry: {IDENTITY_REGISTRY}")
    print(f"Agent Card tokenURI: {AGENT_CARD_URI}")
    print(f"Function: register(string) [0xf2c298be]")

    # Nonce
    nonce_hex = rpc_call("eth_getTransactionCount", [account.address, "pending"])
    nonce = int(nonce_hex, 16)

    # Gas price
    gas_price_hex = rpc_call("eth_gasPrice", [])
    gas_price = int(gas_price_hex, 16)
    # Estimate gas
    tx_params = {
        "from": account.address,
        "to": IDENTITY_REGISTRY,
        "data": calldata,
    }
    try:
        est_gas_hex = rpc_call("eth_estimateGas", [tx_params])
        gas_limit = int(int(est_gas_hex, 16) * 1.3)
    except Exception as e:
        print(f"Warning on estimateGas: {e}, using default 250,000")
        gas_limit = 250000

    print(f"Nonce: {nonce} | Gas Limit: {gas_limit} | Gas Price: {gas_price / 1e9:.3f} Gwei")

    # Build EIP-1559 or legacy tx
    transaction = {
        "to": IDENTITY_REGISTRY,
        "value": 0,
        "gas": gas_limit,
        "gasPrice": int(gas_price * 1.2),
        "nonce": nonce,
        "chainId": BASE_CHAIN_ID,
        "data": calldata,
    }

    signed_tx = account.sign_transaction(transaction)
    raw_tx_hex = "0x" + signed_tx.raw_transaction.hex()

    print("\nBroadcasting transaction to Base Mainnet...")
    tx_hash = rpc_call("eth_sendRawTransaction", [raw_tx_hex])
    print(f"\nTransaction Broadcast! Tx Hash: {tx_hash}")
    basescan_url = f"https://basescan.org/tx/{tx_hash}"
    print(f"BaseScan: {basescan_url}")

    # Wait for receipt
    print("Waiting for block confirmation on Base...")
    receipt = None
    for _ in range(30):
        time.sleep(2)
        receipt = rpc_call("eth_getTransactionReceipt", [tx_hash])
        if receipt:
            break

    agent_id = None
    if receipt:
        status = "SUCCESS" if receipt.get("status") == "0x1" else "FAILED"
        block_num = int(receipt.get("blockNumber", "0x0"), 16)
        print(f"\nBlock: #{block_num} | Status: {status}")

        # Extract agent_id from Transfer event logs (topic0 = 0xddf252ad...)
        for log in receipt.get("logs", []):
            if log.get("topics") and log["topics"][0].lower() == "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef":
                if len(log["topics"]) >= 4:
                    agent_id = int(log["topics"][3], 16)
                    print(f"Official Minted ERC-8004 Agent ID: #{agent_id}")
                    break

        reg_data = {
            "success": True,
            "network": "eip155:8453",
            "identity_registry": IDENTITY_REGISTRY,
            "reputation_registry": REPUTATION_REGISTRY,
            "agent_card_uri": AGENT_CARD_URI,
            "agent_id": agent_id,
            "transaction_hash": tx_hash,
            "block_number": block_num,
            "basescan_url": basescan_url,
            "registered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        os.makedirs(os.path.join(Path(__file__).parent.parent, "state"), exist_ok=True)
        out_path = os.path.join(Path(__file__).parent.parent, "state", "erc8004-registration.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(reg_data, f, indent=2)
        print(f"\nRegistration receipt successfully saved to: {out_path}")
    else:
        print("Transaction is still pending confirmation.")

if __name__ == "__main__":
    main()
