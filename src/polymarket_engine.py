import asyncio
import json
import logging
import time
import hashlib
from typing import Dict, List, Any, Optional
import httpx

from .sanitizer import sanitize_content
from .scrapling_engine import stealth_scrape_and_sanitize

logger = logging.getLogger("stealthguard.polymarket")

GAMMA_API_URL = "https://gamma-api.polymarket.com/markets"
CLOB_BOOK_URL = "https://clob.polymarket.com/book"

async def fetch_clob_orderbook(client: httpx.AsyncClient, token_id: str) -> Optional[Dict[str, Any]]:
    try:
        resp = await client.get(f"{CLOB_BOOK_URL}?token_id={token_id}", timeout=6.0)
        if resp.status_code == 200:
                book = resp.json()
                if not isinstance(book, dict) or not isinstance(book.get("bids"), list) or not isinstance(book.get("asks"), list):
                    return None
                book["provenance"] = {"url": str(resp.request.url), "observed_at": time.time(), "response_sha256": hashlib.sha256(resp.content).hexdigest()}
                return book
    except Exception as e:
        logger.debug(f"CLOB orderbook fetch failed for {token_id}: {e}")
    return None

async def scan_polymarket_alpha(
    category: Optional[str] = None,
    limit: int = 25,
    strict_mode: bool = True
) -> Dict[str, Any]:
    """
    Scans Polymarket Gamma + CLOB orderbooks for volume spikes and smart-money spread divergence,
    scrapes resolution sources via Scrapling, and sanitizes resolution text via CanaryGuard.
    """
    limit = max(1, min(limit, 50))
    async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": "StealthGuard-Alpha/1.0"}) as client:
        # Fetch active markets
        params: Dict[str, Any] = {
            "active": "true",
            "closed": "false",
            "limit": limit,
            "order": "volume24hr",
            "ascending": "false",
        }
        gamma_provenance = []
        if category:
            # Search the requested topic instead of filtering an unrelated top-N sample.
            terms = ["bitcoin", "ethereum", "solana"] if category.lower().strip() == "crypto" else [category]
            responses = await asyncio.gather(*(client.get("https://gamma-api.polymarket.com/public-search", params={
                "q": term, "events_status": "active", "limit_per_type": 10, "keep_closed_markets": 0,
            }) for term in terms))
            raw_markets = []
            for gamma_resp in responses:
                if gamma_resp.status_code != 200 or not isinstance(gamma_resp.json(), dict):
                    return {"error": "Polymarket topic search is unavailable", "markets_scanned": 0, "opportunities": []}
                for event in gamma_resp.json().get("events") or []:
                    raw_markets.extend(event.get("markets") or [])
                gamma_provenance.append({"url": str(gamma_resp.request.url), "observed_at": time.time(), "response_sha256": hashlib.sha256(gamma_resp.content).hexdigest()})
            raw_markets = list({str(m["id"]): m for m in raw_markets if isinstance(m, dict) and "id" in m
                                and m.get("closed") is not True and m.get("active") is not False and m.get("enableOrderBook") is not False}.values())
            raw_markets.sort(key=lambda m: float(m.get("volume24hr") or m.get("volumeNum") or 0), reverse=True)
        else:
            gamma_resp = await client.get(GAMMA_API_URL, params=params)
            if gamma_resp.status_code != 200:
                return {"error": f"Polymarket Gamma API error: {gamma_resp.status_code}", "markets_scanned": 0, "opportunities": []}
            raw_markets = gamma_resp.json()
            if not isinstance(raw_markets, list):
                return {"error": "Invalid Polymarket markets response", "markets_scanned": 0, "opportunities": []}
            gamma_provenance.append({"url": str(gamma_resp.request.url), "observed_at": time.time(), "response_sha256": hashlib.sha256(gamma_resp.content).hexdigest()})

        scanned_opportunities = []
        resolution_texts_to_sanitize = []

        # Process top markets
        for m in raw_markets[:limit]:
            market_id = m.get("id")
            question = m.get("question", "Unknown Market")
            volume_24hr = float(m.get("volume24hr") or m.get("volumeNum") or 0.0)
            liquidity = float(m.get("liquidity") or m.get("liquidityNum") or 0.0)
            resolution_source = (m.get("resolutionSource") or "").strip()
            description = (m.get("description") or "").strip()

            # Extract CLOB token IDs
            clob_token_ids_raw = m.get("clobTokenIds") or []
            if isinstance(clob_token_ids_raw, str):
                try:
                    clob_token_ids = json.loads(clob_token_ids_raw)
                except Exception:
                    clob_token_ids = []
            elif isinstance(clob_token_ids_raw, list):
                clob_token_ids = clob_token_ids_raw
            else:
                clob_token_ids = []

            primary_token_id = clob_token_ids[0] if clob_token_ids else None

            # Fetch live CLOB orderbook metrics
            best_bid = None
            best_ask = None
            spread_bps = None
            bid_depth = 0.0
            ask_depth = 0.0
            orderbook_imbalance = 0.0

            book_provenance = None
            if primary_token_id:
                book = await fetch_clob_orderbook(client, primary_token_id)
                if book:
                    bids = book.get("bids", [])
                    asks = book.get("asks", [])
                    if bids:
                        try:
                            ordered_bids = sorted(bids, key=lambda b: float(b["price"]), reverse=True)
                            best_bid = float(ordered_bids[0]["price"])
                            bid_depth = sum(float(b["size"]) * float(b["price"]) for b in ordered_bids[:10])
                        except Exception:
                            pass
                    if asks:
                        try:
                            ordered_asks = sorted(asks, key=lambda a: float(a["price"]))
                            best_ask = float(ordered_asks[0]["price"])
                            ask_depth = sum(float(a["size"]) * float(a["price"]) for a in ordered_asks[:10])
                        except Exception:
                            pass
                    if bid_depth + ask_depth > 0:
                        orderbook_imbalance = round((bid_depth - ask_depth) / (bid_depth + ask_depth), 4)
                    spread_bps = round((best_ask - best_bid) * 10000, 1) if best_ask is not None and best_bid is not None else None
                    book_provenance = book["provenance"]
            if book_provenance is None:
                return {"error": "A requested live CLOB orderbook could not be acquired", "markets_scanned": 0, "opportunities": []}

            vol_to_liq = round(volume_24hr / max(liquidity, 1.0), 3)
            whale_divergence = vol_to_liq > 1.2 or abs(orderbook_imbalance) > 0.65

            alpha_rating = "NEUTRAL"
            if whale_divergence and spread_bps is not None and spread_bps > 50:
                alpha_rating = "HIGH_WHALE_DIVERGENCE"
            elif whale_divergence:
                alpha_rating = "VOLUME_ACCUMULATION"
            elif spread_bps is not None and spread_bps > 150:
                alpha_rating = "WIDE_SPREAD_OPPORTUNITY"

            # Resolution text / rules verification
            resolution_text = f"{description}\nResolution Source: {resolution_source}"
            resolution_texts_to_sanitize.append(f"Market: {question}\n{resolution_text}")

            scanned_opportunities.append({
                "market_id": market_id,
                "question": question,
                "slug": m.get("slug"),
                "volume_24hr_usd": volume_24hr,
                "liquidity_usd": liquidity,
                "volume_to_liquidity_ratio": vol_to_liq,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread_bps": spread_bps,
                "orderbook_imbalance": orderbook_imbalance,
                "bid_depth_top10_usdc": bid_depth,
                "ask_depth_top10_usdc": ask_depth,
                "orderbook_provenance": book_provenance,
                "whale_divergence_flag": whale_divergence,
                "alpha_rating": alpha_rating,
                "resolution_source": resolution_source or "Decentralized UMA Oracle / Community Resolution",
            })

        # Sanitize combined market texts and resolution rules through CanaryGuard
        combined_text = "\n\n---\n\n".join(resolution_texts_to_sanitize)
        overall_receipt = sanitize_content(combined_text, strict_mode=strict_mode)
        if overall_receipt["injection_detected"]:
            return {"error": "Market text failed the prompt-injection screen", "markets_scanned": 0, "opportunities": []}

        # Flag any suspicious resolution manipulation
        resolution_manipulation_flagged = overall_receipt["injection_detected"] or overall_receipt["risk_score"] > 0.3

        # Cross-Sell Ecosystem Flywheel: Recommend actions based on market divergence and resolution verification
        recommended_actions = []
        whale_alerts = [o for o in scanned_opportunities if o["whale_divergence_flag"]]
        target_res_url = None
        if whale_alerts:
            top_whale = whale_alerts[0]
            res_cand = top_whale.get("resolution_source", "")
            if res_cand and (res_cand.startswith("http://") or res_cand.startswith("https://")):
                target_res_url = res_cand

        recommended_actions.append({
            "service": "stealthguard-402",
            "action": "stealth_scrape_and_sanitize",
            "url": "https://stealthguard-402.onrender.com/v1/stealth_scrape_and_sanitize",
            "price_usd": "0.02",
            "description": "Bypass anti-bot protection on breaking news or market oracle resolution sources to verify truth ground.",
            "params": {"url": target_res_url or "https://news.google.com", "render_js": True}
        })
        recommended_actions.append({
            "service": "canaryguard-402",
            "action": "sanitize_content",
            "url": "https://canaryguard-402.onrender.com/v1/sanitize",
            "price_usd": "0.003",
            "description": "Deterministic prompt-injection sanitization for external trading news articles and discord posts.",
            "params": {"content": f"Verify market: {whale_alerts[0]['question'] if whale_alerts else 'Top Alpha Market'}", "strict_mode": True}
        })

        return {
            "status": "success",
            "provenance": gamma_provenance,
            "limitations": ["Volume and orderbook imbalance are signals, not proof of whale identities or future profit", "Only the provider's requested top-market sample was searched"],
            "markets_scanned": len(scanned_opportunities),
            "whale_divergence_alerts": whale_alerts,
            "opportunities": scanned_opportunities,
            "resolution_manipulation_flagged": resolution_manipulation_flagged,
            "canaryguard_receipt": overall_receipt,
            "safe_to_persist": overall_receipt["safe_to_persist"] and not resolution_manipulation_flagged,
            "risk_score": overall_receipt["risk_score"],
            "recommended_actions": recommended_actions,
        }
