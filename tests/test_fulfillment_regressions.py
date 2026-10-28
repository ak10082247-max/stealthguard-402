import base64
import json
import pytest
import httpx

from src import api, mcp_server, tool_executor, scrapling_engine, microtools
from src import x402_middleware as payment
from src.config import TOOL_PRICING
from src.payment_execution import ToolFailure
from src.tool_validation import validate_arguments
from tests.test_payment_contract_regressions import sol_payment, valid_receipt, mock_settler, TOOL, URL


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path):
    monkeypatch.setenv("X402_STATE_DB", str(tmp_path / "payments.sqlite3"))
    monkeypatch.delenv("RAPIDAPI_PROXY_SECRET", raising=False)
    monkeypatch.delenv("X402_FREE_TRIAL_ENABLED", raising=False)
    payment.REPLAY_CACHE.clear()
    api.FREE_TRIAL_IP_MAP.clear()
    monkeypatch.setattr(api, "record_delivery", lambda **kw: None)
    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: pytest.fail("Unexpected live settlement"))


@pytest.mark.asyncio
async def test_http_receipt_and_same_authorization_recovery(monkeypatch):
    calls = mock_settler(monkeypatch, valid_receipt())
    seen = []
    async def fulfill(tool, args):
        seen.append(args)
        return {"url": args["url"], "status_code": 200, "unique": "purchased-result"}
    monkeypatch.setattr(tool_executor, "fulfill_tool", fulfill)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="https://stealthguard-402.onrender.com") as client:
        header = {"PAYMENT-SIGNATURE": json.dumps(sol_payment())}
        first = await client.post("/v1/stealth_scrape_and_sanitize", json={"url": "https://example.org", "render_js": False}, headers=header)
        second = await client.post("/v1/stealth_scrape_and_sanitize", json={"url": "https://example.org", "render_js": False}, headers=header)
    assert first.status_code == second.status_code == 200 and first.json() == second.json()
    receipt = json.loads(base64.b64decode(first.headers["PAYMENT-RESPONSE"]))
    assert receipt["success"] is True and receipt["transaction"] == valid_receipt()["transaction"]
    assert len(calls) == len(seen) == 1


@pytest.mark.asyncio
async def test_http_failed_fulfillment_and_bad_types_never_settle(monkeypatch):
    calls = mock_settler(monkeypatch, valid_receipt())
    async def broken(*a):
        raise ToolFailure("Provider failed")
    monkeypatch.setattr(tool_executor, "fulfill_tool", broken)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="https://stealthguard-402.onrender.com") as client:
        header = {"PAYMENT-SIGNATURE": json.dumps(sol_payment())}
        bad = await client.post("/v1/stealth_scrape_and_sanitize", json={"url": "https://example.org", "render_js": "false"}, headers=header)
        failed = await client.post("/v1/stealth_scrape_and_sanitize", json={"url": "https://example.org"}, headers=header)
    assert bad.status_code == 400 and failed.status_code == 503
    assert bad.json()["charged"] is failed.json()["charged"] is False and calls == []


@pytest.mark.asyncio
async def test_get_boolean_query_is_parsed_before_execution(monkeypatch):
    mock_settler(monkeypatch, valid_receipt())
    async def fulfill(tool, args):
        assert args["render_js"] is False and args["strict_mode"] is True
        return {"status": "success"}
    monkeypatch.setattr(tool_executor, "fulfill_tool", fulfill)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="https://stealthguard-402.onrender.com") as client:
        response = await client.get("/v1/stealth_scrape_and_sanitize?url=https://example.org&render_js=false&strict_mode=true", headers={"PAYMENT-SIGNATURE": json.dumps(sol_payment())})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_untrusted_rapidapi_headers_cannot_unlock_or_change_resource(monkeypatch):
    async def must_not_fulfill(*a):
        pytest.fail("Caller-supplied billing metadata is not authentication")
    monkeypatch.setattr(tool_executor, "fulfill_tool", must_not_fulfill)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="https://attacker.invalid") as client:
        response = await client.get("/v1/stealth_scrape_and_sanitize", headers={"x-rapidapi-user": "subscriber", "x-rapidapi-key": "pretend", "x-rapidapi-proxy-secret": "pretend"})
    assert response.status_code == 402 and response.json()["resource"]["url"] == URL


@pytest.mark.asyncio
async def test_mcp_uses_real_common_executor_and_failure_stops_charge(monkeypatch):
    calls = mock_settler(monkeypatch, valid_receipt())
    async def broken(*a):
        raise ToolFailure("Browser failed")
    monkeypatch.setattr(tool_executor, "fulfill_tool", broken)
    payload = sol_payment()
    payload["resource"]["url"] = "https://stealthguard-402.onrender.com/mcp"
    request = {"jsonrpc": "2.0", "id": 23, "method": "tools/call", "params": {
        "name": TOOL, "arguments": {"url": "https://example.org"}, "_meta": {"x402/payment": payload}}}
    result, receipt = await mcp_server.handle_mcp_request(request)
    assert result["id"] == 23 and result["result"]["isError"] is True
    assert result["result"]["_meta"]["http_status"] == 503 and receipt is None and calls == []


@pytest.mark.parametrize("tool,args", [(TOOL, {"url": "https://example.org", "strict_mode": "true"}),
    ("polymarket_alpha_divergence", {"limit": True}), ("polymarket_alpha_divergence", {"limit": -1}),
    ("pre_trade_agent_gate", {"token_or_service_address": "test", "chain": "ethereum"}),
    ("oracle_perp_funding_and_basis", {"assets": [12]}), ("alpha_polymarket_whale_orderflow", {"min_order_usd": float("nan")})])
def test_shared_argument_validation(tool, args):
    with pytest.raises(ValueError):
        validate_arguments(tool, args)


@pytest.mark.asyncio
async def test_requested_url_never_substitutes_cached_hackernews(monkeypatch):
    async def fetch(**kw):
        return {"url": kw["url"], "status_code": 200, "token_compressed_markdown": "requested content"}
    monkeypatch.setattr(tool_executor, "stealth_scrape_and_sanitize", fetch)
    tool_executor.CACHE_STORE["stealth_scrape_default"] = {"url": "https://news.ycombinator.com", "status_code": 200}
    result = await tool_executor.fulfill_tool(TOOL, {"url": "https://example.com"})
    assert result["url"] == "https://example.com" and result["token_compressed_markdown"] == "requested content"


@pytest.mark.asyncio
async def test_requested_js_cannot_silently_fall_back_to_static(monkeypatch):
    from scrapling.fetchers import Fetcher, StealthyFetcher
    monkeypatch.setattr(scrapling_engine, "require_public_url", lambda url: url)
    def browser_unavailable(*a, **kw):
        raise RuntimeError("Browser executable missing")
    monkeypatch.setattr(StealthyFetcher, "fetch", browser_unavailable)
    monkeypatch.setattr(Fetcher, "get", lambda *a, **kw: pytest.fail("JS requests must not downgrade to static HTTP"))
    with pytest.raises(RuntimeError, match="Browser executable"):
        await scrapling_engine.stealth_scrape_and_sanitize("https://example.org", render_js=True)


@pytest.mark.asyncio
async def test_provider_backed_hackernews_binds_requested_limit(monkeypatch):
    seen = []
    async def get(client, url, **kwargs):
        seen.append((url, kwargs))
        return httpx.Response(200, json={"hits": [{"title": "Live fixture story", "objectID": "100", "points": 7}]}, request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    result = await microtools.fulfill_microtool("hackernews_ai_digest", {"limit": 3})
    assert seen[0][1]["params"]["hitsPerPage"] == 3
    assert result["stories_count"] == 1 and result["stories"][0]["title"] == "Live fixture story"
    assert len(result["provenance"][0]["response_sha256"]) == 64


@pytest.mark.asyncio
async def test_provider_failure_does_not_fall_back_to_sample_feed(monkeypatch):
    async def get(*a, **kw):
        raise httpx.ReadTimeout("simulated")
    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    with pytest.raises(httpx.ReadTimeout):
        await microtools.fulfill_microtool("defi_yield_radar", {"asset": "USDC"})


def test_attestation_signature_covers_exact_document(monkeypatch, tmp_path):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    monkeypatch.setenv("STEALTH_ATTESTATION_KEY_FILE", str(tmp_path / "signing.key"))
    evidence = microtools._signed_evidence({"unique": "measured evidence", "time": 123})
    key = Ed25519PublicKey.from_public_bytes(base64.b64decode(evidence["public_key"]))
    canonical = json.dumps(evidence["document"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    key.verify(base64.b64decode(evidence["signature"]), canonical)
    from cryptography.exceptions import InvalidSignature
    with pytest.raises(InvalidSignature):
        key.verify(base64.b64decode(evidence["signature"]), canonical + b"tampered")


@pytest.mark.asyncio
async def test_cross_venue_provider_failure_is_explicit_not_fake_success(monkeypatch):
    async def fetch(client, url, **kwargs):
        if "data-api.polymarket.com/trades" in url:
            response = httpx.Response(200, json=[], request=httpx.Request("GET", url))
            return response, {"url": url, "response_sha256": "fixture"}
        raise httpx.ReadTimeout("Public cross-venue provider fixture unavailable")
    monkeypatch.setattr(microtools, "_get", fetch)
    with pytest.raises(ToolFailure, match="Cross-venue"):
        await microtools.fulfill_microtool("alpha_polymarket_whale_orderflow", {"include_cross_venue": True})


@pytest.mark.asyncio
async def test_topic_market_discovery_and_unsorted_book_math(monkeypatch):
    from src.polymarket_engine import scan_polymarket_alpha
    urls = []
    async def get(client, url, **kwargs):
        urls.append((url, kwargs))
        if "public-search" in url:
            assert kwargs["params"]["q"] == "bitcoin"
            data = {"events": [{"markets": [{"id": "123", "active": True, "closed": False, "question": "Bitcoin fixture market",
                    "volume24hr": 1000, "liquidity": 10000, "clobTokenIds": '["456"]'}]}]}
        else:
            data = {"bids": [{"price": "0.40", "size": "100"}, {"price": "0.49", "size": "50"}],
                    "asks": [{"price": "0.70", "size": "10"}, {"price": "0.51", "size": "20"}]}
        return httpx.Response(200, json=data, request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    result = await scan_polymarket_alpha(category="bitcoin", limit=1)
    opportunity = result["opportunities"][0]
    assert opportunity["best_bid"] == 0.49 and opportunity["best_ask"] == 0.51
    assert opportunity["spread_bps"] == 200 and opportunity["bid_depth_top10_usdc"] == 64.5
    assert len(urls) == 2 and opportunity["orderbook_provenance"]["response_sha256"]


@pytest.mark.asyncio
async def test_funding_rates_use_measured_binance_interval(monkeypatch):
    async def post(client, url, **kwargs):
        data = [{"universe": [{"name": "BTC"}]}, [{"funding": "0.0002", "markPx": "101", "oraclePx": "100"}]]
        return httpx.Response(200, json=data, request=httpx.Request("POST", url))
    async def get(client, url, **kwargs):
        data = [{"fundingTime": 0}, {"fundingTime": 21600000}] if "fundingRate" in url else {"indexPrice": "100", "markPrice": "102", "lastFundingRate": "0.0006"}
        return httpx.Response(200, json=data, request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    result = await microtools.fulfill_microtool("oracle_perp_funding_and_basis", {"assets": ["BTC"]})
    row = result["rates"][0]
    assert row["binance"]["measured_interval_hours"] == 6
    assert row["binance"]["funding_rate_per_hour"] == pytest.approx(0.0001)
    assert row["binance"]["basis_bps"] == pytest.approx(200)
    assert row["executable_profit"] is None


@pytest.mark.asyncio
async def test_base_rpc_failures_are_unavailable_never_safe(monkeypatch):
    from src.token_gate_engine import check_base_rpc
    async def post(*args, **kwargs):
        return httpx.Response(200, json={"jsonrpc": "2.0", "error": {"message": "provider outage"}}, request=httpx.Request("POST", "https://example.org"))
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    async with httpx.AsyncClient() as client:
        with pytest.raises(ToolFailure, match="Base RPC"):
            await check_base_rpc(client, "0x"+"12"*20)


@pytest.mark.asyncio
async def test_version_endpoint_and_default_whale_orderflow_cross_venue(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "a" * 40)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="https://stealthguard-402.onrender.com") as client:
        res = await client.get("/version")
    assert res.status_code == 200
    body = res.json()
    assert body["service"] == "stealthguard-402" and body["revision"] == "a" * 40
