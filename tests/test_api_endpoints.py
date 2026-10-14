import json
import pytest
import httpx
from src.api import app

@pytest.mark.asyncio
async def test_api_health_and_stats():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        r_health = await client.get("/health")
        assert r_health.status_code == 200
        assert r_health.json()["status"] == "ok"
        assert r_health.json()["cache_warmer"] == "ACTIVE_SUB_50MS"

        r_stats = await client.get("/stats")
        assert r_stats.status_code == 200
        assert "pricing" in r_stats.json()
        assert r_stats.json()["total_endpoints"] >= 19

@pytest.mark.asyncio
async def test_api_x402_manifest_and_discovery():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        r_manifest = await client.get("/.well-known/x402.json")
        assert r_manifest.status_code == 200
        data = r_manifest.json()
        assert data["x402Version"] == 2
        assert len(data["endpoints"]) >= 18
        assert "bazaar" in data["endpoints"][0]["extensions"]

        # Check agent-card endpoint
        r_card = await client.get("/.well-known/agent-card.json")
        assert r_card.status_code == 200
        assert r_card.json()["registries"]["identity"] == "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"

@pytest.mark.asyncio
async def test_api_unpaid_endpoints_return_402_both_get_and_post():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # POST Scrape
        r_scrape_post = await client.post("/v1/stealth_scrape_and_sanitize", json={"url": "https://example.com"})
        assert r_scrape_post.status_code == 402
        assert "PAYMENT-REQUIRED" in r_scrape_post.headers
        assert r_scrape_post.headers["X-402-Amount"] == "0.005"

        # GET Scrape
        r_scrape_get = await client.get("/v1/stealth_scrape_and_sanitize?url=https://example.com")
        assert r_scrape_get.status_code == 402
        assert "PAYMENT-REQUIRED" in r_scrape_get.headers
        assert r_scrape_get.headers["X-402-Amount"] == "0.005"

        # POST Polymarket
        r_poly = await client.post("/v1/polymarket_alpha_divergence", json={"limit": 5})
        assert r_poly.status_code == 402
        assert "PAYMENT-REQUIRED" in r_poly.headers
        assert r_poly.headers["X-402-Amount"] == "0.008"

        # GET Pre-trade gate
        r_gate = await client.get("/v1/pre_trade_agent_gate")
        assert r_gate.status_code == 402
        assert "PAYMENT-REQUIRED" in r_gate.headers
        assert r_gate.headers["X-402-Amount"] == "0.005"

        # GET Micro-endpoints
        r_whales = await client.get("/v1/alpha/polymarket-top-whales")
        assert r_whales.status_code == 402
        assert r_whales.headers["X-402-Amount"] == "0.003"

        r_firewall = await client.get("/v1/security/prompt-firewall")
        assert r_firewall.status_code == 402
        assert r_firewall.headers["X-402-Amount"] == "0.001"

@pytest.mark.asyncio
async def test_api_mcp_streamable_http():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # initialize
        r_init = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert r_init.status_code == 200
        assert r_init.json()["result"]["serverInfo"]["name"] == "StealthGuard-402"

        # tools/list
        r_tools = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        assert r_tools.status_code == 200
        tools = r_tools.json()["result"]["tools"]
        assert len(tools) >= 19

@pytest.mark.asyncio
async def test_sub_50ms_cache_warmer_latency():
    import time
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        mock_auth = {
            "x402Version": 2,
            "payload": {
                "signature": "0x1111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111",
                "authorization": {
                    "from": "0x1111111111111111111111111111111111111111",
                    "to": "0x73279fa4BadA7CAC888c62CDa4f5c8104765f6f1",
                    "value": "10000",
                    "validAfter": "0",
                    "validBefore": "2000000000",
                    "nonce": "0x" + "1" * 64
                }
            }
        }
        headers = {"PAYMENT-SIGNATURE": json.dumps(mock_auth)}
        # Warm up ASGI transport
        await client.get("/health")
        start = time.time()
        r = await client.get("/v1/alpha/polymarket-top-whales", headers=headers)
        duration_ms = (time.time() - start) * 1000
        assert r.status_code == 200
        assert duration_ms < 50.0  # Guarantees sub-50ms response for Lumière PayCheck A+
        assert "PAYMENT-RESPONSE" in r.headers
        assert r.json()["status"] == "success"
        assert len(r.json()["recommended_actions"]) >= 2
