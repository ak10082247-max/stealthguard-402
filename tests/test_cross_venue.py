"""Captured public books + adverse criteria; never funded wallet or order calls."""
import copy
import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from src import cross_venue as cross
from src import microtools


@pytest.fixture
def capture():
    return json.loads((Path(__file__).parent / "fixtures/cross_venue_public_hourly_20261028.json").read_text(encoding="utf-8"))


def identity(capture):
    return cross.identical_payoff(capture["limitless"], capture["polymarket"], now=capture["observed_at"])


def test_actual_public_mapped_market_quotes_two_outcomes_and_serializes(capture):
    ident = identity(capture)
    assert ident["oracle"]["opening_price_agrees"] is True
    assert ident["mapping"] == "provider_explicit_mirror_plus_independent_rules"
    routes = cross.compare_books(capture["limitless"], capture["polymarket"], capture["limitless_book"], capture["polymarket_up_book"], capture["polymarket_down_book"], ident, now=capture["observed_at"])
    assert len(routes) == 2
    assert all(row["status"] == "depth_quoted" for row in routes)
    assert all(row["is_profitable"] is False for row in routes)
    assert {(row["limitless_outcome"], row["polymarket_outcome"]) for row in routes} == {("Up", "Down"), ("Down", "Up")}
    json.dumps({"identity": ident, "routes": routes}, allow_nan=False)


@pytest.mark.parametrize("alteration", ["oracle", "strike", "start", "end", "mapping", "outcome", "equality", "missing_strike", "expired"])
def test_similar_titles_cannot_override_payoff_mismatches(capture, alteration):
    l, p = capture["limitless"], capture["polymarket"]
    if alteration == "oracle":
        p["resolutionSource"] = "https://other.example/oracle"
    elif alteration == "strike":
        l["metadata"]["openPrice"] = str(Decimal(l["metadata"]["openPrice"]) + 1)
    elif alteration == "start":
        l["startAt"] = "2026-10-28T13:01:00Z"
    elif alteration == "end":
        l["expirationTimestamp"] += 60000
    elif alteration == "mapping":
        l["metadata"]["externalSlug"] += "-substitution"
    elif alteration == "outcome":
        p["outcomes"] = '["Yes", "No"]'
    elif alteration == "equality":
        p["description"] = p["description"].replace("greater than or equal", "strictly greater")
    elif alteration == "missing_strike":
        for event in p["events"]:
            event.pop("eventMetadata", None)
    elif alteration == "expired":
        capture["observed_at"] = l["expirationTimestamp"] / 1000
    with pytest.raises(cross.ComparisonRejected):
        identity(capture)


@pytest.mark.parametrize("alteration", ["limitless_token", "polymarket_token", "polymarket_condition", "stale", "future"])
def test_substituted_or_stale_books_never_produce_spreads(capture, alteration):
    ident = identity(capture)
    if alteration == "limitless_token":
        capture["limitless_book"]["tokenId"] = "1"
    elif alteration == "polymarket_token":
        capture["polymarket_up_book"]["asset_id"] = "1"
    elif alteration == "polymarket_condition":
        capture["polymarket_down_book"]["market"] = "0x" + "ab" * 32
    elif alteration == "stale":
        capture["polymarket_up_book"]["timestamp"] = str(int((capture["observed_at"] - 31) * 1000))
    elif alteration == "future":
        capture["polymarket_up_book"]["timestamp"] = str(int((capture["observed_at"] + 6) * 1000))
    with pytest.raises(cross.ComparisonRejected):
        cross.compare_books(capture["limitless"], capture["polymarket"], capture["limitless_book"], capture["polymarket_up_book"], capture["polymarket_down_book"], ident, now=capture["observed_at"])


def test_raw_limitless_sizes_and_mirrored_no_prices_use_exact_units():
    book = {"bids": [{"price": "0.6", "size": "2000000"}], "asks": [{"price": "0.7", "size": "3000000"}]}
    yes = cross.levels(book, "asks", raw_scale=1_000_000)
    no = cross.levels(book, "bids", raw_scale=1_000_000, invert=True)
    assert yes == [(Decimal("0.7"), Decimal(3))]
    assert no == [(Decimal("0.4"), Decimal(2))]
    assert cross.buy_quote(no, Decimal(100))["full_displayed_depth"] is False
    assert cross.buy_quote(no, Decimal(100))["available_shares"] == "2"


def test_walks_sorted_actual_depth_and_computes_amount_dependent_vwap():
    book = {"asks": [{"price": "0.5", "size": "40"}, {"price": "0.4", "size": "60"}]}
    quote = cross.buy_quote(cross.levels(book, "asks"), Decimal(100))
    assert quote["notional"] == "44.0"
    assert quote["vwap"] == "0.44"
    assert quote["fills"] == [{"price": "0.4", "shares": "60"}, {"price": "0.5", "shares": "40"}]


def test_official_fee_formulas_use_share_notional_and_per_level_prices(capture):
    quote = cross.buy_quote([(Decimal("0.4"), Decimal(100))], Decimal(100))
    l_fee = cross.fee_for_quote("limitless", capture["limitless"], quote)
    p_fee = cross.fee_for_quote("polymarket", capture["polymarket"], quote)
    assert Decimal(l_fee["amount"]) == Decimal("1.2")
    assert Decimal(p_fee["amount"]) == Decimal("1.68")


def fixture_transport(capture):
    l, p = capture["limitless"], capture["polymarket"]
    ids = json.loads(p["clobTokenIds"])
    outcomes = json.loads(p["outcomes"])
    mapping = dict(zip(ids, outcomes))
    seen = []
    def reply(request):
        seen.append(str(request.url))
        assert request.method == "GET", "No order or payment write is permitted"
        if request.url.path == "/markets/active":
            assert request.url.params["limit"] == "25"
            return httpx.Response(200, json={"data": [l]})
        if request.url.host == "gamma-api.polymarket.com":
            assert request.url.params["slug"] == p["slug"]
            return httpx.Response(200, json=[p])
        if request.url.host == "api.limitless.exchange":
            assert request.url.path == "/markets/" + l["slug"] + "/orderbook"
            return httpx.Response(200, json=capture["limitless_book"])
        if request.url.host == "clob.polymarket.com":
            outcome = mapping[request.url.params["token_id"]]
            return httpx.Response(200, json=capture["polymarket_" + outcome.lower() + "_book"])
        if request.url.host == "data-api.polymarket.com":
            return httpx.Response(200, json=[{"title": "Owner public market", "size": "20000", "price": "0.5", "side": "BUY", "proxyWallet": "0x" + "11" * 20}])
        pytest.fail("Unexpected provider URL " + str(request.url))
    return httpx.MockTransport(reply), seen


@pytest.mark.asyncio
async def test_full_catalogue_and_three_books_use_only_five_public_reads(capture, monkeypatch):
    transport, seen = fixture_transport(capture)
    monkeypatch.setattr(cross.time, "time", lambda: capture["observed_at"])
    async with httpx.AsyncClient(transport=transport) as client:
        result = await cross.scan_limitless_polymarket(client, microtools._get)
    assert result["cross_venue_status"] == "measured"
    assert result["cross_venue_pairs_measured"] == 1
    assert result["cross_venue_routes_depth_quoted"] == 2
    assert len(seen) == 5
    assert len(result["cross_venue_matrix"][0]["provenance"]) == 4
    json.dumps(result, allow_nan=False)


@pytest.mark.asyncio
async def test_whale_tool_include_cross_venue_returns_measured_matrix(capture, monkeypatch):
    transport, seen = fixture_transport(capture)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(cross.time, "time", lambda: capture["observed_at"])
    monkeypatch.setattr(microtools.httpx, "AsyncClient", lambda **kwargs: real_client(transport=transport, **kwargs))
    result = await microtools.fulfill_microtool("alpha_polymarket_whale_orderflow", {"min_order_usd": 1000, "include_cross_venue": True})
    assert result["status"] == "success"
    assert result["cross_venue_status"] == "measured"
    assert result["cross_venue_pairs_measured"] == 1
    assert result["wallet_activity"][0]["observed_trade_count"] == 1
    assert len(seen) == 6
    json.dumps(result, allow_nan=False)
