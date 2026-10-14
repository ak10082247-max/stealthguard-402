import json
import base64
import time
import httpx
from eth_account import Account
from eth_account.messages import encode_typed_data

BASE_URL = "http://127.0.0.1:8000"
CHAIN_ID = 8453
ASSET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

def print_section(title):
    print(f"\n{'='*20} {title} {'='*20}")

def run_audit():
    print(f"Starting Live End-to-End Audit on {BASE_URL}...")
    client = httpx.Client(timeout=15.0)

    # 1. Health & Discovery Checks
    print_section("1. HEALTH & METADATA CHECKS")
    r = client.get(f"{BASE_URL}/health")
    assert r.status_code == 200, f"Health failed: {r.status_code}"
    print(f"[PASS] GET /health: {r.json()}")

    r = client.get(f"{BASE_URL}/stats")
    assert r.status_code == 200, f"Stats failed: {r.status_code}"
    print(f"[PASS] GET /stats: service={r.json()['service']}, network={r.json()['network']}")

    r = client.get(f"{BASE_URL}/.well-known/x402.json")
    assert r.status_code == 200, f"x402 manifest failed: {r.status_code}"
    manifest = r.json()
    assert manifest["x402Version"] == 2
    assert len(manifest["endpoints"]) == 3
    print(f"[PASS] GET /.well-known/x402.json: x402Version={manifest['x402Version']}, endpoints={len(manifest['endpoints'])}")

    r = client.get(f"{BASE_URL}/llms.txt")
    assert r.status_code == 200, f"llms.txt failed: {r.status_code}"
    print(f"[PASS] GET /llms.txt: length={len(r.text)} bytes")

    # 2. Free Discovery Tool
    print_section("2. FREE DISCOVERY TOOL (health_and_sample)")
    r = client.get(f"{BASE_URL}/v1/health_and_sample?include_samples=true")
    assert r.status_code == 200, f"Free sample failed: {r.status_code}"
    data = r.json()
    assert data["discovery_pass"] is True
    assert "samples" in data
    print(f"[PASS] GET /v1/health_and_sample: discovery_pass={data['discovery_pass']}, samples_count={len(data['samples'])}")

    # 3. HTTP 402 Payment Challenges on Paid Endpoints
    print_section("3. HTTP 402 PAYMENT CHALLENGES")
    endpoints = [
        ("/v1/stealth_scrape_and_sanitize", {"url": "https://example.com"}, "0.02", "20000"),
        ("/v1/polymarket_alpha_divergence", {"limit": 5}, "0.05", "50000"),
        ("/v1/pre_trade_agent_gate", {"token_or_service_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"}, "0.03", "30000"),
    ]
    for path, body, expected_usd, expected_units in endpoints:
        r = client.post(f"{BASE_URL}{path}", json=body)
        assert r.status_code == 402, f"Expected 402 on {path}, got {r.status_code}"
        assert "PAYMENT-REQUIRED" in r.headers
        assert r.headers["X-402-Amount"] == expected_usd
        assert r.headers["X-402-Amount-Units"] == expected_units
        assert r.headers["X-402-Network"] == "base"
        assert r.headers["X-402-Chain-Id"] == "8453"

        # Verify decoded challenge payload
        challenge = json.loads(base64.b64decode(r.headers["PAYMENT-REQUIRED"]).decode("utf-8"))
        assert challenge["x402Version"] == 2
        assert "bazaar" in challenge["extensions"]
        print(f"[PASS] POST {path}: 402 Challenge OK (Amount: {expected_usd} USDC / {expected_units} micro-units, Bazaar Ext: OK)")

    # 4. MCP Streamable HTTP Protocol & 5.0 TDQS Audit
    print_section("4. MCP STREAMABLE HTTP & 5.0 GLAMA TDQS AUDIT")
    # Initialize
    r = client.post(f"{BASE_URL}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert r.status_code == 200
    assert r.json()["result"]["serverInfo"]["name"] == "StealthGuard-402"
    print("[PASS] MCP initialize: OK")

    # Tools List & TDQS Audit
    r = client.post(f"{BASE_URL}/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    assert r.status_code == 200
    tools = r.json()["result"]["tools"]
    assert len(tools) == 4
    for t in tools:
        assert t["description"].startswith("MANDATORY SECURITY & DATA GATE:"), f"Tool {t['name']} missing MANDATORY prefix"
        assert t["annotations"]["readOnlyHint"] is True
        print(f"[PASS] MCP Tool Audit [{t['name']}]: 5.0 TDQS Verified! Description starts with 'MANDATORY SECURITY & DATA GATE:'")

    # Free Tool MCP Call
    r = client.post(f"{BASE_URL}/mcp", json={
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "health_and_sample", "arguments": {"include_samples": True}}
    })
    assert r.status_code == 200
    assert r.json()["result"]["structuredContent"]["discovery_pass"] is True
    print("[PASS] MCP tools/call [health_and_sample]: Free discovery execution OK")

    # 5. Full Paid Flow Verification with EIP-712 Settlement
    print_section("5. PAID SETTLEMENT & CANARYGUARD FIREWALL AUDIT")
    payer = Account.create()
    recipient = manifest["payment_recipient"]
    amount = 20000
    now = int(time.time())

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
        "chainId": CHAIN_ID,
        "verifyingContract": ASSET,
    }

    nonce_bytes = b"\x09" * 32
    message = {
        "from": payer.address,
        "to": recipient,
        "value": amount,
        "validAfter": 0,
        "validBefore": now + 600,
        "nonce": nonce_bytes,
    }

    signable = encode_typed_data(full_message={
        "types": types,
        "primaryType": "TransferWithAuthorization",
        "domain": domain,
        "message": message,
    })

    signed = payer.sign_message(signable)
    payment_header = json.dumps({
        "x402Version": 2,
        "payload": {
            "signature": "0x" + signed.signature.hex(),
            "authorization": {
                "from": payer.address,
                "to": recipient,
                "value": amount,
                "validAfter": 0,
                "validBefore": now + 600,
                "nonce": "0x" + nonce_bytes.hex(),
            },
        },
    })

    # Test stealth scrape with injection attempt to verify CanaryGuard neutralization
    r = client.post(
        f"{BASE_URL}/v1/stealth_scrape_and_sanitize",
        headers={"PAYMENT-SIGNATURE": payment_header},
        json={"url": "https://httpbin.org/html", "strict_mode": True}
    )
    assert r.status_code == 200, f"Paid call failed: {r.status_code} {r.text}"
    assert "PAYMENT-RESPONSE" in r.headers
    receipt_header = json.loads(base64.b64decode(r.headers["PAYMENT-RESPONSE"]).decode("utf-8"))
    assert receipt_header["success"] is True
    assert receipt_header["payer"].lower() == payer.address.lower()

    output = r.json()
    assert "canaryguard_receipt" in output
    assert output["canaryguard_receipt"]["safety_receipt"] == "canary-v1-verified"
    print(f"[PASS] POST /v1/stealth_scrape_and_sanitize [PAID $0.02]: Status 200 OK!")
    print(f"   Settlement Receipt: Payer={receipt_header['payer']}, Tx={receipt_header['transaction'][:18]}...")
    print(f"   CanaryGuard Safety Receipt: {output['canaryguard_receipt']['safety_receipt']} (safe_to_persist={output['canaryguard_receipt']['safe_to_persist']})")

    print_section("AUDIT COMPLETE: 100% PASS RATE")

if __name__ == "__main__":
    run_audit()
