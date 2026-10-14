import pytest
import sys
from unittest.mock import AsyncMock, patch
from apify import Actor
from apify_main import run_actor

@pytest.mark.asyncio
async def test_apify_ppe_stealth_scrape_charge_and_push():
    fake_input = {
        "tool": "stealth_scrape_and_sanitize",
        "url": "https://httpbin.org/html",
        "render_js": False,
        "strict_mode": True,
    }

    charged_events = []
    pushed_items = []

    async def mock_get_input():
        return fake_input

    async def mock_charge(event_name, count=1):
        charged_events.append({"event_name": event_name, "count": count})

    async def mock_push_data(data):
        pushed_items.append(data)

    Actor._exit_process = False

    with patch("apify.Actor.get_input", side_effect=mock_get_input), \
         patch("apify.Actor.charge", side_effect=mock_charge), \
         patch("apify.Actor.push_data", side_effect=mock_push_data), \
         patch("sys.exit") as mock_exit:

        await run_actor()

    # Verify PPE event charged: 1 event of stealth_scrape_and_sanitize
    assert len(charged_events) == 1
    assert charged_events[0]["event_name"] == "stealth_scrape_and_sanitize"
    assert charged_events[0]["count"] == 1

    # Verify result pushed to Dataset
    assert len(pushed_items) == 1
    assert pushed_items[0]["status_code"] == 200
    assert "token_compressed_markdown" in pushed_items[0]
    assert "canaryguard_receipt" in pushed_items[0]

@pytest.mark.asyncio
async def test_apify_ppe_polymarket_charge_and_push():
    fake_input = {
        "tool": "polymarket_alpha_divergence",
        "limit": 2,
    }

    charged_events = []
    pushed_items = []

    async def mock_get_input():
        return fake_input

    async def mock_charge(event_name, count=1):
        charged_events.append({"event_name": event_name, "count": count})

    async def mock_push_data(data):
        pushed_items.append(data)

    Actor._exit_process = False

    with patch("apify.Actor.get_input", side_effect=mock_get_input), \
         patch("apify.Actor.charge", side_effect=mock_charge), \
         patch("apify.Actor.push_data", side_effect=mock_push_data), \
         patch("sys.exit") as mock_exit:

        await run_actor()

    # Verify PPE event charged: 2 events of polymarket_alpha_divergence ($0.05 total)
    assert len(charged_events) == 1
    assert charged_events[0]["event_name"] == "polymarket_alpha_divergence"
    assert charged_events[0]["count"] == 2

    assert len(pushed_items) == 1
    assert "markets_scanned" in pushed_items[0]

@pytest.mark.asyncio
async def test_apify_ppe_pre_trade_gate_charge_and_push():
    fake_input = {
        "tool": "pre_trade_agent_gate",
        "token_or_service_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "chain": "base",
    }

    charged_events = []
    pushed_items = []

    async def mock_get_input():
        return fake_input

    async def mock_charge(event_name, count=1):
        charged_events.append({"event_name": event_name, "count": count})

    async def mock_push_data(data):
        pushed_items.append(data)

    Actor._exit_process = False

    with patch("apify.Actor.get_input", side_effect=mock_get_input), \
         patch("apify.Actor.charge", side_effect=mock_charge), \
         patch("apify.Actor.push_data", side_effect=mock_push_data), \
         patch("sys.exit") as mock_exit:

        await run_actor()

    # Verify PPE event charged: 1 event of pre_trade_agent_gate ($0.03)
    assert len(charged_events) == 1
    assert charged_events[0]["event_name"] == "pre_trade_agent_gate"
    assert charged_events[0]["count"] == 1

    assert len(pushed_items) == 1
    assert "verdict" in pushed_items[0]
