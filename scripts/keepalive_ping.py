#!/usr/bin/env python3
"""
Keepalive Ping Script for Render Microservices:
- https://canaryguard-402.onrender.com/health
- https://rugshield-402.onrender.com/health
- https://stealthguard-402.onrender.com/health

Prevents Render free/standard tier cold starts so autonomous agents never experience latency timeouts.
"""

import sys
import time
import urllib.request
import json

SERVICES = [
    {"name": "StealthGuard-402", "url": "https://stealthguard-402.onrender.com/health"},
    {"name": "CanaryGuard-402", "url": "https://canaryguard-402.onrender.com/health"},
    {"name": "RugShield-402", "url": "https://rugshield-402.onrender.com/health"},
]

def ping_services():
    results = []
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}] Starting keepalive ping across ecosystem...")

    headers = {"User-Agent": "StealthGuard-KeepAlive/1.0 (Render; Warmup)"}

    for svc in SERVICES:
        start = time.time()
        try:
            req = urllib.request.Request(svc["url"], headers=headers)
            with urllib.request.urlopen(req, timeout=25) as resp:
                elapsed_ms = int((time.time() - start) * 1000)
                body = resp.read().decode("utf-8")
                print(f"[OK] {svc['name']}: {resp.status} ({elapsed_ms}ms) -> {body[:80]}")
                results.append({"name": svc["name"], "status": resp.status, "latency_ms": elapsed_ms, "ok": True})
        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            print(f"[ERR] {svc['name']}: {e} ({elapsed_ms}ms)")
            results.append({"name": svc["name"], "status": 0, "error": str(e), "latency_ms": elapsed_ms, "ok": False})

    all_ok = all(r["ok"] for r in results)
    print(f"Keepalive summary: {sum(1 for r in results if r['ok'])}/{len(SERVICES)} servers active.")
    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(ping_services())
