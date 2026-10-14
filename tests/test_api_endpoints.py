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

        r_stats = await client.get("/stats")
        assert r_stats.status_code == 200
        assert "pricing" in r_stats.json()

@pytest.mark.asyncio
async def test_api_x402_manifest_and_discovery():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        r_manifest = await client.get("/.well-known/x402.json")
        assert r_manifest.status_code == 200
        data = r_manifest.json()
        assert data["x402Version"] == 2
        assert len(data["endpoints"]) == 3
        assert "bazaar" in data["endpoints"][0]["extensions"]

@pytest.mark.asyncio
async def test_api_unpaid_endpoints_return_402():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Scrape
        r_scrape = await client.post("/v1/stealth_scrape_and_sanitize", json={"url": "https://example.com"})
        assert r_scrape.status_code == 402
        assert "PAYMENT-REQUIRED" in r_scrape.headers
        assert r_scrape.headers["X-402-Amount"] == "0.02"

        # Polymarket
        r_poly = await client.post("/v1/polymarket_alpha_divergence", json={"limit": 5})
        assert r_poly.status_code == 402
        assert "PAYMENT-REQUIRED" in r_poly.headers
        assert r_poly.headers["X-402-Amount"] == "0.05"

        # Pre-trade gate
        r_gate = await client.post("/v1/pre_trade_agent_gate", json={"token_or_service_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"})
        assert r_gate.status_code == 402
        assert "PAYMENT-REQUIRED" in r_gate.headers
        assert r_gate.headers["X-402-Amount"] == "0.03"

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
        assert len(tools) == 4
