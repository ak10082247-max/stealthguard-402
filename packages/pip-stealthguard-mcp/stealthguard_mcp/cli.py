#!/usr/bin/env python3
import sys
import os
import json
import urllib.request
import urllib.error

TARGET_URL = os.environ.get("STEALTHGUARD_URL", "https://stealthguard-402.onrender.com/mcp").strip()
APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "").strip() or None
X402_SIGNATURE = os.environ.get("X402_PAYMENT_SIGNATURE", "").strip() or None

def main():
    sys.stderr.write(f"[stealthguard-mcp] Python stdio proxy initialized -> {TARGET_URL}\n")
    sys.stderr.flush()

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue

        try:
            parsed = json.loads(line)
        except Exception as e:
            sys.stderr.write(f"[stealthguard-mcp] Parse error: {e}\n")
            sys.stderr.flush()
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()
            continue

        req_id = parsed.get("id")

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "stealthguard-mcp-py/1.0.0 (stdio-client)",
        }
        if APIFY_TOKEN:
            headers["Authorization"] = f"Bearer {APIFY_TOKEN}"
            headers["X-Apify-Token"] = APIFY_TOKEN
        if X402_SIGNATURE:
            headers["PAYMENT-SIGNATURE"] = X402_SIGNATURE
            headers["X-Payment"] = X402_SIGNATURE

        req_data = json.dumps(parsed).encode("utf-8")
        req = urllib.request.Request(TARGET_URL, data=req_data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_bytes = resp.read()
                resp_text = resp_bytes.decode("utf-8", errors="replace")
                try:
                    res_json = json.loads(resp_text)
                except Exception:
                    res_json = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{"type": "text", "text": resp_text}]
                        },
                    }
                sys.stdout.write(json.dumps(res_json) + "\n")
                sys.stdout.flush()
        except urllib.error.HTTPError as he:
            err_body = he.read().decode("utf-8", errors="replace")
            try:
                res_json = json.loads(err_body)
            except Exception:
                res_json = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32603,
                        "message": f"HTTP {he.code}: {he.reason}",
                        "data": err_body,
                    },
                }
            sys.stdout.write(json.dumps(res_json) + "\n")
            sys.stdout.flush()
        except Exception as e:
            sys.stderr.write(f"[stealthguard-mcp] Network error: {e}\n")
            sys.stderr.flush()
            err_resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32603,
                    "message": f"Upstream StealthGuard connection error: {str(e)}",
                },
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    main()
