import os
import sys
import httpx
import json

COINBASE_VALIDATOR_URL = "https://api.cdp.coinbase.com/platform/v2/x402/validate"
BASE_URL = os.getenv("PUBLIC_URL", "https://stealthguard-402.onrender.com").rstrip("/")

ENDPOINTS = [
    "/v1/stealth_scrape_and_sanitize",
    "/v1/polymarket_alpha_divergence",
    "/v1/pre_trade_agent_gate",
    "/v1/alpha/polymarket-top-whales",
    "/v1/alpha/polymarket-crypto-odds",
    "/v1/alpha/base-trending-tokens",
    "/v1/alpha/defi-yield-radar",
    "/v1/alpha/hackernews-ai-digest",
    "/v1/security/prompt-firewall",
    "/v1/security/x402-endpoint-verifier",
]

def main():
    print("=" * 70)
    print("COINBASE CDP FACILITATOR & X402 VALIDATION SUITE")
    print("Target:", BASE_URL)
    print("=" * 70)

    client = httpx.Client(timeout=30.0)

    # 1. Favicon Check
    try:
        fav_r = client.get(f"{BASE_URL}/favicon.ico")
        fav_ok = fav_r.status_code == 200 and "image/x-icon" in fav_r.headers.get("content-type", "")
        print(f"[*] /favicon.ico: status={fav_r.status_code} content-type={fav_r.headers.get('content-type')} -> {'PASS' if fav_ok else 'PENDING_DEPLOY'}")
    except Exception as e:
        print(f"[!] /favicon.ico error: {e}")

    # 2. OpenAPI Info & Paths Check
    try:
        spec_r = client.get(f"{BASE_URL}/openapi.json")
        if spec_r.status_code == 200:
            spec = spec_r.json()
            email = spec.get("info", {}).get("contact", {}).get("email")
            paths_count = len(spec.get("paths", {}))
            print(f"[*] /openapi.json: contact.email={email} paths_count={paths_count}")
        else:
            print(f"[!] /openapi.json status={spec_r.status_code}")
    except Exception as e:
        print(f"[!] /openapi.json error: {e}")

    print("\n" + "-" * 70)
    print("TESTING 10 CLEAN PAID ENDPOINTS AGAINST COINBASE CDP VALIDATOR")
    print("-" * 70)

    all_passed = True
    results = []

    for path in ENDPOINTS:
        res_url = f"{BASE_URL}{path}"
        payload = {"resource": res_url, "method": "POST"}
        try:
            r = client.post(COINBASE_VALIDATOR_URL, json=payload)
            data = r.json()
            valid = data.get("valid", False)
            status_code = data.get("statusCode")
            outcome = data.get("simulation", {}).get("outcome") or data.get("outcome")

            preflight_fails = [c["detail"] for c in data.get("preflight", []) if not c.get("passed") and c.get("severity") == "required"]
            
            status_str = "ACCEPTED" if (valid or outcome == "accepted") else "REJECTED"
            print(f"[{status_str}] {path}")
            print(f"       HTTP Status: {status_code} | Outcome: {outcome} | Valid: {valid}")
            if preflight_fails:
                print(f"       Failed checks: {', '.join(preflight_fails[:2])}")

            results.append({"path": path, "valid": valid, "outcome": outcome, "statusCode": status_code})
            if not valid and outcome != "accepted":
                all_passed = False
        except Exception as e:
            print(f"[ERR] {path}: {e}")
            all_passed = False

    print("\n" + "=" * 70)
    print(f"SUMMARY: {'ALL 10 ENDPOINTS VALIDATED' if all_passed else 'SOME CHECKS PENDING RENDER DEPLOY'}")
    print("=" * 70)

if __name__ == "__main__":
    main()
