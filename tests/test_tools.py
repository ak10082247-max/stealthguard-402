import pytest
from src.scrapling_engine import stealth_scrape_and_sanitize
from src.polymarket_engine import scan_polymarket_alpha
from src.token_gate_engine import pre_trade_agent_gate
from src.mcp_server import generate_health_and_sample_payload

@pytest.mark.asyncio
async def test_health_and_sample_tool():
    res = generate_health_and_sample_payload(include_samples=True)
    assert res["status"] == "healthy"
    assert res["service"] == "StealthGuard-402"
    assert res["discovery_pass"] is True
    assert "samples" in res
    assert "stealth_scrape_and_sanitize" in res["samples"]
    assert "polymarket_alpha_divergence" in res["samples"]
    assert "pre_trade_agent_gate" in res["samples"]

@pytest.mark.asyncio
async def test_stealth_scrape_and_sanitize_tool():
    # Test scraping httpbin or public html
    res = await stealth_scrape_and_sanitize(
        url="https://example.com",
        render_js=False,
        strict_mode=True
    )
    assert res["status_code"] in (200, 301, 302)
    assert "token_compressed_markdown" in res
    assert "canaryguard_receipt" in res
    assert res["canaryguard_receipt"]["safety_receipt"] == "canary-v1-verified"
    assert res["canaryguard_receipt"]["safe_to_persist"] is True
    assert res["injection_detected"] is False

@pytest.mark.asyncio
async def test_polymarket_alpha_divergence_tool():
    res = await scan_polymarket_alpha(limit=3, strict_mode=True)
    assert "markets_scanned" in res
    assert res["markets_scanned"] >= 1
    assert "opportunities" in res
    opp = res["opportunities"][0]
    assert "question" in opp
    assert "spread_bps" in opp
    assert "whale_divergence_flag" in opp
    assert "canaryguard_receipt" in res
    assert res["canaryguard_receipt"]["safety_receipt"] == "canary-v1-verified"

@pytest.mark.asyncio
async def test_pre_trade_agent_gate_usdc_trust():
    # Base USDC token address
    base_usdc = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    res = await pre_trade_agent_gate(
        token_or_service_address=base_usdc,
        chain="base",
        strict_mode=True
    )
    assert res["chain"] == "base"
    assert res["token_address"] == base_usdc
    assert "verdict" in res
    # USDC has deep liquidity and valid bytecode
    assert res["liquidity_usd"] > 1000.0
    assert "canaryguard_receipt" in res

@pytest.mark.asyncio
async def test_pre_trade_agent_gate_invalid_address_block():
    res = await pre_trade_agent_gate(
        token_or_service_address="0xInvalidAddress",
        chain="base"
    )
    assert res["verdict"] == "BLOCK"
    assert res["risk_score"] == 1.0
