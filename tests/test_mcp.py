import json
import pytest
from src.mcp_server import handle_mcp_request, MCP_TOOLS

@pytest.mark.asyncio
async def test_mcp_initialize():
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {}
    }
    resp, pay_hdr = await handle_mcp_request(req)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    assert "serverInfo" in resp["result"]
    assert resp["result"]["serverInfo"]["name"] == "StealthGuard-402"
    assert "capabilities" in resp["result"]

@pytest.mark.asyncio
async def test_mcp_tools_list_glama_tdqs():
    req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }
    resp, pay_hdr = await handle_mcp_request(req)
    tools = resp["result"]["tools"]
    assert len(tools) >= 19
    tool_names = [t["name"] for t in tools]
    assert "stealth_scrape_and_sanitize" in tool_names
    assert "polymarket_alpha_divergence" in tool_names
    assert "pre_trade_agent_gate" in tool_names
    assert "health_and_sample" in tool_names

    # Check Glama TDQS requirements
    for tool in tools:
        assert "description" in tool
        assert len(tool["description"]) > 20
        assert "inputSchema" in tool
        assert "annotations" in tool
        assert "readOnlyHint" in tool["annotations"]
        assert tool["annotations"]["readOnlyHint"] is True

@pytest.mark.asyncio
async def test_mcp_tools_call_free_discovery():
    req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "health_and_sample",
            "arguments": {"include_samples": True}
        }
    }
    resp, pay_hdr = await handle_mcp_request(req)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 3
    assert "result" in resp
    assert "structuredContent" in resp["result"]
    assert resp["result"]["structuredContent"]["status"] == "healthy"
    assert resp["result"]["structuredContent"]["discovery_pass"] is True

@pytest.mark.asyncio
async def test_mcp_tools_call_unpaid_returns_402():
    req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "stealth_scrape_and_sanitize",
            "arguments": {"url": "https://example.com"}
        }
    }
    resp, pay_hdr = await handle_mcp_request(req)
    assert resp["isError"] is True
    assert resp["error"]["code"] == 402
    assert resp["error"]["message"] == "payment_required"
    assert "_meta" in resp
    assert "x402/payment-required" in resp["_meta"]
