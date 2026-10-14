#!/usr/bin/env python3
"""
scripts/revenue_watcher_daemon.py
Autonomous Revenue Watcher & Render Keep-Alive Daemon.

1. Keeps Render instances warm (StealthGuard, CanaryGuard, RugShield) every cycle.
2. Monitors on-chain Base USDC balance of the merchant payout wallet:
   0x73279fa4BadA7CAC888c62CDa4f5c8104765f6f1
3. Detects any incoming micropayments from autonomous agents, logs new earnings,
   and persists transaction history to state/revenue_history.json.
"""

import sys
import os
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import urllib.request
import urllib.error

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

MERCHANT_ADDRESS = "0x73279fa4BadA7CAC888c62CDa4f5c8104765f6f1"
USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
BASE_RPC = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")

SERVICES = [
    {"name": "StealthGuard", "url": "https://stealthguard-402.onrender.com/health"},
    {"name": "CanaryGuard",  "url": "https://canaryguard-402.onrender.com/health"},
    {"name": "RugShield",    "url": "https://rugshield-402.onrender.com/health"},
]

STATE_DIR = Path(__file__).parent.parent / "state"
HISTORY_FILE = STATE_DIR / "revenue_history.json"

def get_onchain_usdc_balance(address: str) -> float:
    """Queries USDC.balanceOf(address) on Base Mainnet via eth_call."""
    clean_addr = address.lower().replace("0x", "").zfill(64)
    data = f"0x70a08231{clean_addr}"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [{"to": USDC_CONTRACT, "data": data}, "latest"]
    }
    req = urllib.request.Request(
        BASE_RPC,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "StealthGuard-RevenueWatcher/1.0"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        raw_hex = res.get("result", "0x0")
        return int(raw_hex, 16) / 1e6

def ping_fleet() -> dict:
    """Pings health endpoints of all 3 services to prevent Render sleep."""
    results = {}
    for svc in SERVICES:
        start = time.time()
        try:
            req = urllib.request.Request(svc["url"], headers={"User-Agent": "KeepAlive/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                elapsed_ms = int((time.time() - start) * 1000)
                results[svc["name"]] = {"status": resp.status, "ms": elapsed_ms, "ok": True}
        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            results[svc["name"]] = {"status": 0, "ms": elapsed_ms, "ok": False, "error": str(e)}
    return results

def load_history() -> dict:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_balance": 0.0, "total_events": 0, "events": []}

def save_history(data: dict):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def main():
    print("=" * 75)
    print("AUTONOMOUS REVENUE WATCHER & RENDER KEEPALIVE DAEMON")
    print(f"Merchant Recipient Wallet: {MERCHANT_ADDRESS}")
    print(f"Base USDC Contract:        {USDC_CONTRACT}")
    print("=" * 75)

    history = load_history()
    initial_balance = get_onchain_usdc_balance(MERCHANT_ADDRESS)
    last_balance = history.get("last_balance") or initial_balance
    history["last_balance"] = last_balance
    save_history(history)

    print(f"[*] Starting Baseline Balance: {last_balance:.6f} USDC")
    print(f"[*] Total Recorded Revenue Events: {len(history.get('events', []))}\n")

    iteration = 0
    poll_interval = 60  # seconds

    while True:
        iteration += 1
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # 1. Warm fleet
        fleet_status = ping_fleet()
        warm_str = " | ".join(f"{k}:{v['ms']}ms" for k, v in fleet_status.items() if v["ok"])

        # 2. Check on-chain balance
        try:
            curr_balance = get_onchain_usdc_balance(MERCHANT_ADDRESS)
            if curr_balance > last_balance:
                diff = curr_balance - last_balance
                event = {
                    "timestamp": now_str,
                    "previous_balance": last_balance,
                    "new_balance": curr_balance,
                    "inflow_usdc": diff,
                }
                history["events"].append(event)
                history["total_events"] = len(history["events"])
                history["last_balance"] = curr_balance
                last_balance = curr_balance
                save_history(history)

                print(f"\n+++ [REVENUE INFLOW DETECTED!] +{diff:.6f} USDC at {now_str}! +++")
                print(f"[REVENUE] New Merchant Balance: {curr_balance:.6f} USDC | Total Inflows: {history['total_events']}\n")
            else:
                last_balance = curr_balance
                history["last_balance"] = curr_balance

            print(f"[{now_str}] #{iteration:04d} [WARM] ({warm_str}) | Merchant USDC: {curr_balance:.6f} | Inflows: {len(history.get('events', []))}")
        except Exception as e:
            print(f"[{now_str}] #{iteration:04d} [WARN] Balance check error: {e}")

        # Flush stdout
        sys.stdout.flush()

        # If run with --once argument, exit after one iteration
        if "--once" in sys.argv:
            break

        time.sleep(poll_interval)

if __name__ == "__main__":
    main()
