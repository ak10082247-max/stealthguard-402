"""Measured Limitless/Polymarket books, never spot prices masquerading as odds.

Only explicit provider mappings with matching payoff criteria enter the matrix.
All requests are public reads. No order, signature, approval or trade is created.
"""
import asyncio
import json
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from bs4 import BeautifulSoup
from .payment_execution import ToolFailure

LIMITLESS = "https://api.limitless.exchange"
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
FEE_PRECISION = Decimal("0.00001")


class ComparisonRejected(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ComparisonRejected(message)


def number(value):
    try:
        require(not isinstance(value, bool), "Boolean numeric data")
        result = Decimal(str(value))
        require(result.is_finite() and abs(result) <= Decimal("1e30"), "Invalid numeric data")
        return result
    except (InvalidOperation, TypeError):
        raise ComparisonRejected("Invalid numeric data")


def timestamp(value):
    require(isinstance(value, str), "Missing UTC timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "Timestamp has no timezone")
    return Decimal(str(parsed.timestamp()))


def text(value):
    require(isinstance(value, str), "Missing resolution rules")
    return " ".join(BeautifulSoup(value, "html.parser").get_text(" ", strip=True).lower().split())


def identical_payoff(limitless, poly, *, now=None):
    """Explicit mirror link plus independent rules, window and threshold checks."""
    now = Decimal(str(time.time() if now is None else now))
    metadata = limitless.get("metadata") or {}
    require(metadata.get("externalProvider") == "polymarket" and metadata.get("externalSlug") == poly.get("slug"), "No exact provider mapping")
    require(poly.get("active") is True and poly.get("closed") is False and poly.get("enableOrderBook") is True and poly.get("acceptingOrders") is True, "Polymarket is not accepting orders")
    require(limitless.get("tradeType") == "clob" and limitless.get("status") in ("CREATED", "FUNDED") and limitless.get("expired") is False, "Limitless market is not active CLOB")
    start, end = timestamp(limitless.get("startAt")), number(limitless.get("expirationTimestamp")) / 1000
    require(start <= now < end - 30, "Market is not open or expires within 30 seconds")
    require(start == timestamp(poly.get("eventStartTime")) and end == timestamp(poly.get("endDate")), "Resolution windows differ")
    l_rules, p_rules = text(limitless.get("description")), text(poly.get("description"))
    for rules in (l_rules, p_rules):
        require('"up"' in rules and '"down"' in rules and "greater than or equal" in rules, "Outcome or equality rule is unrecognized")
    outcomes = poly.get("outcomes")
    outcomes = json.loads(outcomes) if isinstance(outcomes, str) else outcomes
    ids = poly.get("clobTokenIds")
    ids = json.loads(ids) if isinstance(ids, str) else ids
    require(isinstance(outcomes, list) and len(outcomes) == 2 and set(outcomes) == {"Up", "Down"}, "Non-binary or unrecognized outcome mapping")
    require(isinstance(ids, list) and len(ids) == 2 and all(isinstance(token, str) and re.fullmatch(r"[0-9]{1,100}", token) for token in ids), "Invalid outcome token identifiers")
    tokens = limitless.get("tokens") or {}
    require(all(isinstance(tokens.get(side), str) and re.fullmatch(r"[0-9]{1,100}", tokens[side]) for side in ("yes", "no")), "Invalid Limitless outcome tokens")
    source = poly.get("resolutionSource")
    require(isinstance(source, str) and source, "Missing resolution source")
    # Hourly Binance mirrors expose both captured thresholds. Comparing them is
    # stronger than inferring equivalence from a shared title or externalSlug.
    pair = re.fullmatch(r"https://www\.binance\.com/en/trade/([A-Z0-9]+)_USDT", source)
    if pair:
        require(end - start == 3600, "Unsupported Binance observation interval")
        require(source.lower() in l_rules and source.lower() in p_rules, "Resolution oracle differs")
        require(all("1 hour candle" in rules and "close price" in rules and "open price" in rules for rules in (l_rules, p_rules)), "Candle resolution criteria differ")
        prices = [event.get("eventMetadata", {}).get("priceToBeat") for event in poly.get("events", []) if isinstance(event, dict) and isinstance(event.get("eventMetadata"), dict) and event["eventMetadata"].get("priceToBeat") is not None]
        require(prices, "Polymarket captured threshold unavailable")
        open_price = number(metadata.get("openPrice"))
        require(open_price > 0 and all(number(price) == open_price for price in prices), "Captured opening prices differ")
        oracle = {"provider": "Binance", "pair": pair[1] + "/USDT", "candle_interval_seconds": 3600, "resolution_source": source, "opening_price": str(open_price), "opening_price_agrees": True}
    else:
        # Chainlink mirrors need an independently published Polymarket opening
        # threshold too. A link and shared feed alone are insufficient.
        chainlink = metadata.get("chainlinkDataStream") or {}
        require(chainlink.get("enabled") is True and chainlink.get("streamUrl") == source and source.lower() in l_rules and source.lower() in p_rules, "Resolution oracle differs or is unsupported")
        require(chainlink.get("streamType") == "twap" and chainlink.get("twapWindowSeconds") == 60 and "twap" in l_rules and "twap" in p_rules, "TWAP criteria differ")
        prices = [event.get("eventMetadata", {}).get("priceToBeat") for event in poly.get("events", []) if isinstance(event, dict) and isinstance(event.get("eventMetadata"), dict) and event["eventMetadata"].get("priceToBeat") is not None]
        require(prices, "Polymarket captured threshold unavailable")
        open_price = number(metadata.get("openPrice"))
        require(open_price > 0 and all(number(price) == open_price for price in prices), "Captured opening prices differ")
        require(timestamp(metadata.get("openPriceSelectedAt")) == start, "Opening observation time differs")
        oracle = {"provider": "Chainlink", "pair": chainlink.get("pair"), "twap_window_seconds": 60, "resolution_source": source, "opening_price": str(open_price), "opening_price_agrees": True}
    return {"mapping": "provider_explicit_mirror_plus_independent_rules", "start_utc": datetime.fromtimestamp(float(start), timezone.utc).isoformat(), "end_utc": datetime.fromtimestamp(float(end), timezone.utc).isoformat(), "oracle": oracle, "up_rule": "closing observation >= opening observation", "down_rule": "closing observation < opening observation", "poly_tokens": dict(zip(outcomes, ids)), "limitless_tokens": {"Up": tokens["yes"], "Down": tokens["no"]}}


def levels(book, side, *, raw_scale=1, invert=False):
    rows = book.get(side)
    require(isinstance(rows, list) and len(rows) <= 1000, "Malformed or oversized order book")
    result = []
    for row in rows:
        require(isinstance(row, dict), "Malformed order-book level")
        price, size = number(row.get("price")), number(row.get("size")) / raw_scale
        require(0 < price < 1 and size > 0, "Invalid order-book price or size")
        result.append((1 - price if invert else price, size))
    return sorted(result)


def buy_quote(offers, shares):
    require(0 < shares <= 1_000_000, "Invalid quoted share amount")
    remaining, value, fills = shares, Decimal(0), []
    for price, size in offers:
        take = min(size, remaining)
        if take:
            value += take * price
            remaining -= take
            fills.append({"price": str(price), "shares": str(take)})
        if remaining == 0:
            return {"shares": str(shares), "notional": str(value), "vwap": str(value / shares), "fills": fills, "full_displayed_depth": True}
    return {"shares": str(shares), "available_shares": str(shares - remaining), "full_displayed_depth": False}


def fee_for_quote(venue, market, quote):
    require(quote.get("full_displayed_depth") is True, "Insufficient displayed depth")
    shares, notional = number(quote["shares"]), number(quote["notional"])
    if venue == "limitless":
        require((market.get("venue") or {}).get("feeModuleType") == "COLLATERAL", "Legacy Limitless fee curve is not measured")
        require(number((market.get("settings") or {}).get("creatorFeePct", 0)) == 0, "Creator-fee schedule is unsupported")
        enabled = (market.get("metadata") or {}).get("fee")
        require(type(enabled) is bool, "Limitless fee policy unavailable")
        rate = Decimal("0.05") if enabled else Decimal(0)
        fee = (rate * notional * (shares - notional) / shares).quantize(FEE_PRECISION, rounding=ROUND_HALF_UP)
        return {"amount": str(fee), "rate": str(rate), "method": "published_standard_collateral_fee_upper_estimate", "source": "https://docs.limitless.exchange/developers/migrate-to-new-trading-venues", "profile_discount_assumed": False}
    enabled, schedule = market.get("feesEnabled"), market.get("feeSchedule") or {}
    require(type(enabled) is bool, "Polymarket fee policy unavailable")
    require(not enabled or schedule.get("exponent") == 1, "Unsupported Polymarket fee exponent")
    rate = number(schedule.get("rate")) if enabled else Decimal(0)
    require(0 <= rate <= 1, "Invalid Polymarket fee rate")
    fee = sum(number(fill["shares"]) * rate * number(fill["price"]) * (1 - number(fill["price"])) for fill in quote["fills"])
    return {"amount": str(fee.quantize(FEE_PRECISION, rounding=ROUND_HALF_UP)), "rate": str(rate), "method": "acquired_fee_schedule_per_displayed_level", "source": "https://docs.polymarket.com/trading/fees"}


def compare_books(limitless, poly, l_book, up_book, down_book, identity, *, shares=Decimal(100), now=None):
    now = time.time() if now is None else now
    require(timestamp(identity["end_utc"]) > Decimal(str(now)) + 5, "Market expired during acquisition")
    require(l_book.get("tokenId") == identity["limitless_tokens"]["Up"], "Limitless order book token was substituted")
    for outcome, book in (("Up", up_book), ("Down", down_book)):
        require(book.get("asset_id") == identity["poly_tokens"][outcome] and book.get("market") == poly.get("conditionId"), "Polymarket book identity mismatch")
        age = Decimal(str(now)) - number(book.get("timestamp")) / 1000
        require(-5 <= age <= 30, "Polymarket order book is stale or future-dated")
        require(0 <= number(book.get("min_order_size")) <= shares, "Quote size is below Polymarket order minimum")
    l_up = buy_quote(levels(l_book, "asks", raw_scale=Decimal(1_000_000)), shares)
    l_down = buy_quote(levels(l_book, "bids", raw_scale=Decimal(1_000_000), invert=True), shares)
    p_up = buy_quote(levels(up_book, "asks"), shares)
    p_down = buy_quote(levels(down_book, "asks"), shares)
    routes = []
    for l_outcome, l_quote, p_outcome, p_quote in (("Up", l_up, "Down", p_down), ("Down", l_down, "Up", p_up)):
        route = {"limitless_outcome": l_outcome, "polymarket_outcome": p_outcome, "shares_per_leg": str(shares), "limitless_quote": l_quote, "polymarket_quote": p_quote, "is_profitable": False}
        if l_quote["full_displayed_depth"] and p_quote["full_displayed_depth"]:
            l_fee, p_fee = fee_for_quote("limitless", limitless, l_quote), fee_for_quote("polymarket", poly, p_quote)
            gross = shares - number(l_quote["notional"]) - number(p_quote["notional"])
            after_fees = gross - number(l_fee["amount"]) - number(p_fee["amount"])
            route.update({"status": "depth_quoted", "gross_spread_bps": str(gross * 10000 / shares), "after_venue_fees_spread_bps": str(after_fees * 10000 / shares), "gross_payoff_less_cost": str(gross), "payoff_less_cost_after_venue_fees_estimate": str(after_fees), "fees": {"limitless": l_fee, "polymarket": p_fee}, "positive_after_venue_fees_candidate": after_fees > 0, "profit_status": "execution_bridge_collateral_and_settlement_costs_unproven"})
        else:
            route.update({"status": "insufficient_displayed_depth", "positive_after_venue_fees_candidate": False})
        routes.append(route)
    return routes


async def scan_limitless_polymarket(client, fetch, *, maximum_pairs=6, quote_shares=100):
    """Bounded catalogue + exact mirrored markets + independent outcome books."""
    async def acquire(url, params=None):
        response, proof = await fetch(client, url, params=params)
        require(len(response.content) <= 2_000_000, "Provider response too large")
        return response.json(), proof

    async def scan():
        catalogue, catalogue_proof = await acquire(LIMITLESS + "/markets/active", {"limit": 25, "page": 1, "sortBy": "ending_soon", "tradeType": "clob"})
        rows = catalogue.get("data") if isinstance(catalogue, dict) else None
        require(isinstance(rows, list), "Invalid Limitless catalogue")
        now = time.time()
        candidates = [row for row in rows if isinstance(row, dict) and (row.get("metadata") or {}).get("externalProvider") == "polymarket" and isinstance((row.get("metadata") or {}).get("externalSlug"), str) and re.fullmatch(r"[a-z0-9-]{1,180}", row["metadata"]["externalSlug"]) and isinstance(row.get("slug"), str) and re.fullmatch(r"[a-z0-9-]{1,180}", row["slug"]) and (row.get("expirationTimestamp") or 0) > (now + 30) * 1000]
        # Hourly mirrors expose an independently captured opening price on both
        # venues. Prefer those over unverified short-window threshold guesses.
        candidates.sort(key=lambda row: ("hourly" not in row["slug"], row["expirationTimestamp"]))
        semaphore = asyncio.Semaphore(3)
        async def pair(row):
            async with semaphore:
                proofs = []
                try:
                    markets, proof = await acquire(GAMMA + "/markets", {"slug": row["metadata"]["externalSlug"]})
                    proofs.append(proof)
                    require(isinstance(markets, list) and len(markets) == 1, "Exact Polymarket counterpart unavailable")
                    poly = markets[0]
                    identity = identical_payoff(row, poly)
                    books = await asyncio.gather(acquire(LIMITLESS + "/markets/" + row["slug"] + "/orderbook"), acquire(CLOB + "/book", {"token_id": identity["poly_tokens"]["Up"]}), acquire(CLOB + "/book", {"token_id": identity["poly_tokens"]["Down"]}))
                    proofs.extend(proof for _, proof in books)
                    routes = compare_books(row, poly, *(book for book, _ in books), identity, shares=number(quote_shares))
                    imbalance = {}
                    for venue, book, scale in (("limitless_yes", books[0][0], 1_000_000), ("polymarket_up", books[1][0], 1)):
                        bids = sum((size for _, size in levels(book, "bids", raw_scale=scale)), Decimal(0))
                        asks = sum((size for _, size in levels(book, "asks", raw_scale=scale)), Decimal(0))
                        imbalance[venue] = {"displayed_bid_shares": str(bids), "displayed_ask_shares": str(asks), "imbalance": str((bids - asks) / (bids + asks)) if bids + asks else None, "scope": "all returned snapshot levels; not historical order flow"}
                    return {"limitless_slug": row["slug"], "polymarket_slug": poly["slug"], "status": "measured", "identity": identity, "routes": routes, "displayed_book_imbalance": imbalance, "provenance": proofs, "limitless_book_freshness": "response_observed_now_but_provider_does_not_guarantee_snapshot_age", "last_checked_at": time.time()}
                except ComparisonRejected as exc:
                    return {"limitless_slug": row["slug"], "status": "excluded", "reason": str(exc), "provenance": proofs}
                except Exception as exc:
                    return {"limitless_slug": row["slug"], "status": "provider_error", "error_type": type(exc).__name__, "provenance": proofs}
        matrix = await asyncio.gather(*(pair(row) for row in candidates[:maximum_pairs]))
        measured = sum(row["status"] == "measured" for row in matrix)
        if matrix and not measured and all(row["status"] == "provider_error" for row in matrix):
            raise ToolFailure("Cross-venue providers failed to supply usable evidence", code="cross_venue_provider_unavailable")
        routes = [route for row in matrix if row["status"] == "measured" for route in row["routes"]]
        return {"cross_venue_status": "measured" if measured else "no_equivalent_markets_in_sample", "cross_venue_matrix": matrix, "cross_venue_pairs_measured": measured, "cross_venue_routes_depth_quoted": sum(route["status"] == "depth_quoted" for route in routes), "cross_venue_positive_after_fee_candidates": sum(route["positive_after_venue_fees_candidate"] for route in routes), "cross_venue_candidates_checked": len(matrix), "cross_venue_catalogue_sample_size": len(rows), "cross_venue_quote_shares_per_leg": str(quote_shares), "cross_venue_provenance": [catalogue_proof], "cross_venue_limits": ["Catalogue sample, not every market or global optimum", "Only explicit mirrors with independently equal opening thresholds and matching oracle/window/inequality are compared", "Limitless snapshot age is not guaranteed by its provider; both venues can move before execution", "Fee estimates use the acquired Polymarket schedule and published standard Limitless collateral rate, without profile discounts", "No orders, fills, bridge cost, collateral conversion, gas, atomicity or settlement outcome are proven; positive fee-adjusted spreads are candidates only", "USD-notional comparison assumes USDC and Polymarket collateral redeem at par"]}
    try:
        async with asyncio.timeout(40):
            return await scan()
    except ToolFailure:
        raise
    except Exception as exc:
        raise ToolFailure("Cross-venue catalogue acquisition failed before settlement", code="cross_venue_provider_unavailable") from exc
