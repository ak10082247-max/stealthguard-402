"""Provider-backed paid feeds. No sample records are used as fallback fulfillment."""
import asyncio
import base64
import hashlib
import json
import math
import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .payment_execution import ToolFailure
from .sanitizer import sanitize_content
from .polymarket_engine import scan_polymarket_alpha
from .scrapling_engine import stealth_scrape_and_sanitize
from .token_gate_engine import pre_trade_agent_gate


async def _get(client, url, *, params=None, json_body=None):
    started = time.time()
    response = await (client.post(url, json=json_body) if json_body is not None else client.get(url, params=params))
    response.raise_for_status()
    body = response.content
    if len(body) > 20_000_000:
        raise ToolFailure("Provider response exceeds processing limit")
    proof = {"url": str(response.request.url), "http_status": response.status_code,
             "observed_at": time.time(), "elapsed_ms": round((time.time()-started)*1000, 2),
             "response_sha256": hashlib.sha256(body).hexdigest()}
    if json_body is not None:
        proof["request"] = json_body
    return response, proof


def _number(value):
    number = float(value)
    if not math.isfinite(number):
        raise ToolFailure("Provider returned a non-finite number")
    return number


def _sanitize(data):
    receipt = sanitize_content(json.dumps(data, ensure_ascii=False))
    if receipt["injection_detected"]:
        raise ToolFailure("Untrusted provider content failed the prompt-injection screen", code="unsafe_provider_content")
    return receipt


async def _news(client, query, limit=10):
    items, evidence, errors = [], [], []
    requests = [
        ("HackerNews", "https://hn.algolia.com/api/v1/search_by_date", {"query": query, "tags": "story", "hitsPerPage": limit}),
        ("Google News RSS", "https://news.google.com/rss/search", {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}),
        ("arXiv", "https://export.arxiv.org/api/query", {"search_query": f"all:{query}", "start": 0, "max_results": min(limit, 10), "sortBy": "submittedDate", "sortOrder": "descending"}),
    ]
    results = await asyncio.gather(*[_get(client, url, params=params) for _, url, params in requests], return_exceptions=True)
    for (name, _, _), result in zip(requests, results):
        if isinstance(result, Exception):
            errors.append({"source": name, "error": type(result).__name__})
            continue
        response, proof = result
        try:
            if name == "HackerNews":
                hits = response.json()["hits"]
                if not isinstance(hits, list):
                    raise ValueError("Invalid search results")
                records = [{"title": hit.get("title"), "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}",
                            "published_at": hit.get("created_at"), "score": hit.get("points"), "comments": hit.get("num_comments"), "source": name}
                           for hit in hits if isinstance(hit, dict) and hit.get("title")]
            elif name == "Google News RSS":
                root = ET.fromstring(response.content)
                records = [{"title": item.findtext("title"), "url": item.findtext("link"),
                            "published_at": item.findtext("pubDate"), "source": name}
                           for item in root.findall("./channel/item")[:limit]]
            else:
                root = ET.fromstring(response.content)
                ns = {"a": "http://www.w3.org/2005/Atom"}
                records = [{"title": entry.findtext("a:title", namespaces=ns), "url": entry.findtext("a:id", namespaces=ns),
                            "published_at": entry.findtext("a:published", namespaces=ns), "summary": entry.findtext("a:summary", namespaces=ns), "source": name}
                           for entry in root.findall("a:entry", ns)]
            _sanitize(records)
            items.extend(records)
            evidence.append(proof)
        except Exception as exc:
            errors.append({"source": name, "error": type(exc).__name__})
    if not evidence:
        raise ToolFailure("All news providers are unavailable")
    return items, evidence, errors


def _signed_evidence(document):
    """Persist a service identity, and sign exactly the returned evidence document."""
    path = Path(os.getenv("STEALTH_ATTESTATION_KEY_FILE", str(Path(__file__).resolve().parent.parent / "state" / "attestation.key")))
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, "wb") as stream:
            stream.write(Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()))
            stream.flush()
            os.fsync(stream.fileno())
    key = Ed25519PrivateKey.from_private_bytes(path.read_bytes())
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    return {"algorithm": "Ed25519", "canonicalization": "UTF-8 JSON; sorted keys; compact separators; ensure_ascii=false",
            "document": document, "sha256": hashlib.sha256(canonical).hexdigest(),
            "public_key": base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode(),
            "signature": base64.b64encode(key.sign(canonical)).decode(),
            "scope": "Service processing evidence. Signature does not prove token safety or future execution."}


async def fulfill_microtool(tool, args):
    async with httpx.AsyncClient(timeout=15, follow_redirects=False, headers={"User-Agent": "StealthGuard/1.3.1"}) as client:
        if tool in ("polymarket_top_whales", "alpha_polymarket_whale_orderflow"):
            minimum = args.get("min_order_usd", 10000)
            response, proof = await _get(client, "https://data-api.polymarket.com/trades", params={"limit": 500, "filterType": "CASH", "filterAmount": minimum})
            trades = response.json()
            if not isinstance(trades, list):
                raise ToolFailure("Invalid Polymarket trades response")
            large = []
            for trade in trades:
                if not isinstance(trade, dict):
                    continue
                size, price = _number(trade["size"]), _number(trade["price"])
                if size * price >= minimum:
                    large.append({"market": trade.get("title"), "condition_id": trade.get("conditionId"), "side": trade.get("side"),
                                  "size_shares": size, "price": price, "size_usdc": size*price, "wallet": trade.get("proxyWallet"),
                                  "transaction": trade.get("transactionHash"), "timestamp": trade.get("timestamp"), "outcome": trade.get("outcome")})
            large.sort(key=lambda item: item["size_usdc"], reverse=True)
            large = large[:args.get("limit", 50)]
            wallets = {}
            for trade in large:
                wallet = trade.get("wallet")
                if not isinstance(wallet, str) or not wallet:
                    continue
                activity = wallets.setdefault(wallet, {"wallet": wallet, "observed_trade_count": 0, "buy_notional": 0.0, "sell_notional": 0.0})
                activity["observed_trade_count"] += 1
                field = "buy_notional" if trade["side"] == "BUY" else "sell_notional" if trade["side"] == "SELL" else None
                if field:
                    activity[field] += trade["size_usdc"]
            cross_venue = {"cross_venue_status": "not_requested"}
            if tool == "alpha_polymarket_whale_orderflow" and args.get("include_cross_venue", False):
                from .cross_venue import scan_limitless_polymarket
                cross_venue = await scan_limitless_polymarket(client, _get)
                _sanitize(cross_venue)
            return {"status": "success", "feed": tool, "large_orders": large, "top_whales": large,
                    "order_filter_usd": minimum, "sampled_trades": len(trades), "provenance": [proof],
                    **cross_venue, "wallet_activity": list(wallets.values()), "wallet_activity_scope": "visible filtered trade sample only; addresses are not inferred independent actors or proven profitable traders",
                    "wallet_clustering": "not_inferred", "canaryguard_receipt": _sanitize(large)}

        if tool == "polymarket_crypto_odds":
            asset = args.get("asset", "BTC").upper()
            category = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}.get(asset, asset)
            result = await scan_polymarket_alpha(category=category, limit=50)
            if result.get("error"):
                raise ToolFailure(str(result["error"]))
            result.update({"status": "success", "asset": asset, "pairs": result["opportunities"]})
            return result

        if tool == "base_trending_tokens":
            if args.get("chain", "base") != "base":
                raise ToolFailure("This endpoint requires chain:base", 400, "invalid_request")
            response, proof = await _get(client, "https://api.dexscreener.com/latest/dex/search", params={"q": "Base"})
            data = response.json()
            if not isinstance(data.get("pairs"), list):
                raise ToolFailure("Invalid DexScreener response")
            pairs = [p for p in data["pairs"] if p.get("chainId") == "base"]
            pairs.sort(key=lambda p: _number((p.get("volume") or {}).get("h24") or 0), reverse=True)
            tokens = []
            for pair in pairs[:5]:
                token = pair.get("baseToken") or {}
                screen = await pre_trade_agent_gate(token["address"], chain="base")
                if screen.get("error"):
                    raise ToolFailure("Token screening provider is unavailable")
                tokens.append({"pair": pair.get("pairAddress"), "token": token, "price_usd": pair.get("priceUsd"),
                               "liquidity_usd": (pair.get("liquidity") or {}).get("usd"), "volume_24h_usd": (pair.get("volume") or {}).get("h24"), "screen": screen})
            return {"status": "success", "network": "base", "trending_tokens": tokens, "trending_basis": "24h volume among provider search results; not the entire market",
                    "provenance": [proof], "canaryguard_receipt": _sanitize(tokens)}

        if tool == "defi_yield_radar":
            response, proof = await _get(client, "https://yields.llama.fi/pools")
            pools = response.json().get("data")
            if not isinstance(pools, list):
                raise ToolFailure("Invalid DefiLlama yield response")
            asset = args.get("asset", "USDC").upper()
            selected = [p for p in pools if p.get("chain", "").lower() == "base" and asset in p.get("symbol", "").upper().split("-") and p.get("apy") is not None]
            selected.sort(key=lambda p: _number(p.get("tvlUsd") or 0), reverse=True)
            yields = [{k: p.get(k) for k in ("pool", "project", "symbol", "chain", "apy", "apyBase", "apyReward", "tvlUsd", "stablecoin", "ilRisk", "exposure")} for p in selected[:20]]
            return {"status": "success", "asset": asset, "yields": yields, "apy_units": "percent per year as reported by provider", "risk_grade": None,
                    "provenance": [proof], "canaryguard_receipt": _sanitize(yields)}

        if tool == "hackernews_ai_digest":
            response, proof = await _get(client, "https://hn.algolia.com/api/v1/search_by_date", params={"query": "AI", "tags": "story", "hitsPerPage": args.get("limit", 10)})
            hits = response.json().get("hits")
            if not isinstance(hits, list):
                raise ToolFailure("Invalid HackerNews search response")
            stories = [{"title": h.get("title"), "url": h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
                        "score": h.get("points"), "comments": h.get("num_comments"), "published_at": h.get("created_at")} for h in hits]
            return {"status": "success", "source": "HackerNews via Algolia", "stories": stories, "stories_count": len(stories), "provenance": [proof], "canaryguard_receipt": _sanitize(stories)}

        if tool in ("research_topic_news_scanner", "research_deep_web_dossier"):
            query = args.get("query") or args.get("topic")
            items, proof, errors = await _news(client, query, 10)
            result = {"status": "success", "query": query, "items": items, "news_count": len(items), "provenance": proof, "provider_errors": errors, "canaryguard_receipt": _sanitize(items)}
            if tool == "research_deep_web_dossier":
                if len(proof) < 2:
                    raise ToolFailure("At least two independent source feeds are required for a dossier")
                articles = []
                urls = list(dict.fromkeys(item["url"].replace("http://arxiv.org/", "https://arxiv.org/") for item in items if item.get("url")))
                desired = 2 if args.get("depth") == "summary" else 4
                async def extract(url):
                    try:
                        article = await stealth_scrape_and_sanitize(url, strict_mode=True)
                        if 200 <= article["status_code"] < 300 and len(article["token_compressed_markdown"].strip()) >= 50:
                            return {"url": url, "text": article["token_compressed_markdown"][:16000], "fetch_method": article["fetch_method"]}
                    except Exception:
                        pass
                    return None
                for offset in range(0, min(len(urls), 12), 3):
                    documents = await asyncio.gather(*(extract(url) for url in urls[offset:offset+3]))
                    articles.extend(document for document in documents if document is not None)
                    if len(articles) >= desired:
                        articles = articles[:desired]
                        break
                if len(articles) < 2:
                    raise ToolFailure("Could not extract two source documents for the requested dossier")
                result.update({"topic": query, "depth": args.get("depth", "comprehensive"), "sources_audited": len(articles), "source_documents": articles,
                               "dossier_markdown": "# Source dossier: " + query + "\n\n" + "\n\n".join(f"## {a['url']}\n\n{a['text']}" for a in articles),
                               "synthesis_method": "Extracted source documents with citations; no invented summary or investment conclusion"})
            return result

        if tool == "oracle_perp_funding_and_basis":
            response, hyper_proof = await _get(client, "https://api.hyperliquid.xyz/info", json_body={"type": "metaAndAssetCtxs"})
            hyper = response.json()
            if not isinstance(hyper, list) or len(hyper) != 2:
                raise ToolFailure("Invalid Hyperliquid market response")
            contexts = {asset["name"]: context for asset, context in zip(hyper[0]["universe"], hyper[1])}
            rows, proof = [], [hyper_proof]
            for asset in args.get("assets", ["BTC", "ETH", "SOL"]):
                if asset not in contexts:
                    raise ToolFailure(f"Hyperliquid has no market for {asset}", 400, "unsupported_asset")
                response, evidence = await _get(client, "https://fapi.binance.com/fapi/v1/premiumIndex", params={"symbol": asset+"USDT"})
                binance = response.json()
                response, interval_proof = await _get(client, "https://fapi.binance.com/fapi/v1/fundingRate", params={"symbol": asset+"USDT", "limit": 2})
                history = response.json()
                if not isinstance(history, list) or len(history) != 2:
                    raise ToolFailure("Could not measure Binance funding interval")
                interval = (_number(history[-1]["fundingTime"])-_number(history[0]["fundingTime"])) / 3600000
                if interval <= 0:
                    raise ToolFailure("Invalid funding interval")
                context = contexts[asset]
                index, mark = _number(binance["indexPrice"]), _number(binance["markPrice"])
                oracle, hyper_mark = _number(context["oraclePx"]), _number(context["markPx"])
                if min(index, oracle) <= 0:
                    raise ToolFailure("Invalid oracle prices")
                rows.append({"asset": asset, "binance": {"symbol": asset+"USDT", "funding_rate_per_interval": _number(binance["lastFundingRate"]),
                             "measured_interval_hours": interval, "funding_rate_per_hour": _number(binance["lastFundingRate"])/interval,
                             "mark_price": mark, "index_price": index, "basis_bps": (mark/index-1)*10000, "provider_time": binance.get("time")},
                             "hyperliquid": {"funding_rate_per_hour": _number(context["funding"]), "mark_price": hyper_mark, "oracle_price": oracle, "basis_bps": (hyper_mark/oracle-1)*10000},
                             "cross_venue_mark_spread_bps": (hyper_mark/mark-1)*10000, "executable_profit": None})
                proof.extend([evidence, interval_proof])
            return {"status": "success", "rates": rows, "provenance": proof, "limitations": ["USDT and USDC quote assets differ", "Funding is variable; fees, slippage, margin and transfer costs are not execution profit"]}

        if tool == "security_attestation_bundle":
            prompt = sanitize_content(args["prompt_text"])
            url_evidence = await stealth_scrape_and_sanitize(args["target_url"], strict_mode=True) if args.get("target_url") else None
            if url_evidence and not 200 <= url_evidence["status_code"] < 300:
                raise ToolFailure("Target URL could not be inspected")
            token_evidence = await pre_trade_agent_gate(args["token_address"], chain="solana" if not args["token_address"].startswith("0x") else "base") if args.get("token_address") else None
            if token_evidence and token_evidence.get("error"):
                raise ToolFailure("Token evidence could not be acquired")
            document = {"observed_at": time.time(), "prompt_safety": prompt, "url_evidence": url_evidence, "token_evidence": token_evidence,
                        "verdict": "BLOCK" if prompt["injection_detected"] or (token_evidence and token_evidence.get("verdict") == "BLOCK") or (url_evidence and url_evidence["injection_detected"]) else "REVIEW_REQUIRED"}
            return {"status": "success", "attestation": _signed_evidence(document), "composite_verdict": document["verdict"]}

    raise ToolFailure(f"No executor is implemented for {tool}", code="capability_unavailable")
