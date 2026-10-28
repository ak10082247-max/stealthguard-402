import asyncio
import logging
import json
import re
import time
from typing import Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup
from .sanitizer import sanitize_content
from .public_url import require_public_url, fetch_pinned
from urllib.parse import urljoin

logger = logging.getLogger("stealthguard.scrapling")

# Default realistic browser headers for fast stealth fetching
STEALTH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

def extract_structured_json(html: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts structured fields from HTML based on provided schema hints.
    """
    soup = BeautifulSoup(html, 'html.parser')
    extracted: Dict[str, Any] = {}
    
    properties = schema.get("properties", schema) if isinstance(schema, dict) else {}
    for key, spec in properties.items():
        # Check by id, class, or tag name
        el = soup.find(id=key) or soup.find(class_=re.compile(rf'\b{re.escape(key)}\b', re.IGNORECASE))
        if not el:
            el = soup.find(re.compile(rf'^{re.escape(key)}$', re.IGNORECASE))
        if el:
            extracted[key] = el.get_text(strip=True)
        else:
            # Fallback search in meta tags
            meta = soup.find('meta', attrs={'name': key}) or soup.find('meta', attrs={'property': key})
            if meta and meta.get('content'):
                extracted[key] = meta['content'].strip()
            else:
                extracted[key] = None
    return extracted


def _require_extracted_page(html, status):
    if not isinstance(html, str) or not html.strip():
        raise RuntimeError("Target returned no extractable content")
    if len(html.encode("utf-8")) > 2_000_000:
        raise RuntimeError("Target content exceeds extraction size limit")
    if not isinstance(status, int) or not 200 <= status < 300:
        raise RuntimeError("Target returned an unsuccessful HTTP response; no content extracted")
    if re.search(r"cf-browser-verification|just a moment\.\.\.|<title[^>]*>\s*(?:attention required|access denied)", html, re.IGNORECASE):
        raise RuntimeError("Target denied access or returned an anti-bot challenge; no content extracted")

async def stealth_scrape_and_sanitize(
    url: str,
    extract_schema: Optional[Dict[str, Any]] = None,
    render_js: bool = False,
    strict_mode: bool = True
) -> Dict[str, Any]:
    """
    Bypasses Cloudflare / anti-bot protections via Scrapling Fetcher / StealthyFetcher,
    extracts token-compressed Markdown and optional structured JSON,
    and runs CanaryGuard deterministic sanitization before returning.
    """
    url = url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url

    html_content = ""
    markdown_content = ""
    status_code = 200
    fetch_method = "scrapling_fetcher"

    # Attempt fetch using Scrapling
    loop = asyncio.get_event_loop()

    def _sync_fetch() -> Tuple[str, str, int, str]:
        from scrapling.fetchers import StealthyFetcher
        from markdownify import markdownify
        require_public_url(url)
        budget_exceeded = []

        def setup_page(page):
            # The browser gets content through the same pinned transport as HTTP.
            # It never resolves the hostname again after the public-address check.
            started, requests, received = time.monotonic(), 0, 0
            def guard(route):
                nonlocal requests, received
                try:
                    requests += 1
                    if requests > 64 or received >= 5_000_000 or time.monotonic() - started > 25:
                        budget_exceeded.append(True)
                        raise RuntimeError("Browser network budget exceeded")
                    request = route.request
                    response = fetch_pinned(request.url, method=request.method,
                                            headers=request.all_headers(), body=request.post_data_buffer,
                                            limit=min(2_000_000, 5_000_000 - received))
                    received += len(response["body"])
                    route.fulfill(status=response["status"], headers=response["headers"], body=response["body"])
                except Exception:
                    route.abort()
            page.context.route("**/*", guard)
            page.context.route_web_socket("**/*", lambda socket: socket.close())
            page.context.add_init_script("Object.defineProperty(window, 'RTCPeerConnection', {value: undefined}); Object.defineProperty(window, 'webkitRTCPeerConnection', {value: undefined}); Object.defineProperty(window, 'WebTransport', {value: undefined});")

        if render_js:
            # A requested browser run must really use a browser; no silent static fallback.
            res = StealthyFetcher.fetch(url, headless=True, timeout=20000,
                                        page_setup=setup_page, google_search=False,
                                        extra_flags=["--disable-quic", "--disable-background-networking"],
                                        additional_args={"service_workers": "block", "ignore_https_errors": False})
            if budget_exceeded:
                raise RuntimeError("Browser network budget exceeded; incomplete rendering was not sold")
            html = res.html_content
            _require_extracted_page(html, res.status)
            return html, markdownify(html), res.status, "scrapling_stealthy_browser"

        current_url = url
        for _ in range(6):
            require_public_url(current_url)
            res = fetch_pinned(current_url, headers=STEALTH_HEADERS)
            if res["status"] in (301, 302, 303, 307, 308):
                location = res["headers"].get("location") or res["headers"].get("Location")
                if not location:
                    raise RuntimeError("Target returned a redirect without a location")
                current_url = urljoin(current_url, location)
                continue
            html = res["body"].decode("utf-8", errors="replace")
            _require_extracted_page(html, res["status"])
            return html, markdownify(html), res["status"], "curl_cffi_pinned"
        raise RuntimeError("Target exceeded the redirect limit")

    html_content, markdown_content, status_code, fetch_method = await loop.run_in_executor(None, _sync_fetch)

    # Convert DOM to structured JSON if schema provided
    structured_data = None
    if extract_schema:
        try:
            structured_data = extract_structured_json(html_content, extract_schema)
        except Exception as e:
            structured_data = {"error": f"Schema extraction failed: {str(e)}"}

    # Pass entire markdown & text through CanaryGuard deterministic sanitizer
    combined_raw_text = f"{markdown_content}\n\n{json.dumps(structured_data) if structured_data else ''}"
    canaryguard_receipt = sanitize_content(combined_raw_text, strict_mode=strict_mode)
    # Structured fields are another output channel. Never return their raw
    # instruction content beside a blocked or cleaned Markdown result.
    if structured_data is not None:
        structured_data = (None if canaryguard_receipt["status"] == "blocked" else {
            key: sanitize_content(value, strict_mode=strict_mode)["sanitized_content"] if isinstance(value, str) else value
            for key, value in structured_data.items()
        })

    # Cross-Sell Ecosystem Flywheel: Recommend actions based on discovered assets and links
    recommended_actions = []
    recommendation_text = canaryguard_receipt["sanitized_content"]
    token_matches = re.findall(r'\b0x[a-fA-F0-9]{40}\b', recommendation_text)
    dex_markers = ["dexscreener.com", "aerodrome.finance", "app.uniswap.org", "basescan.org/token", "basescan.org/address", "clanker.world"]
    has_dex = any(d in recommendation_text.lower() for d in dex_markers)

    if token_matches or has_dex:
        detected_token = token_matches[0] if token_matches else "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
        recommended_actions.append({
            "service": "stealthguard-402",
            "action": "pre_trade_agent_gate",
            "url": "https://stealthguard-402.onrender.com/v1/pre_trade_agent_gate",
            "price_usd": "0.01",
            "description": "Verify token bytecode, DexScreener LP depth, and sanitize metadata via CanaryGuard firewall before trading.",
            "params": {"token_or_service_address": detected_token, "chain": "base"}
        })
        recommended_actions.append({
            "service": "rugshield-402",
            "action": "deep_swap_simulation",
            "url": "https://rugshield-402.onrender.com/v1/scan",
            "price_usd": "0.01",
            "description": "Request token risk evidence and available buy/sell simulation; review returned provider limitations.",
            "params": {"token_address": detected_token, "chain": "base", "simulate_sell": True}
        })
    elif "polymarket" in recommendation_text.lower() or "prediction market" in recommendation_text.lower() or "odds" in recommendation_text.lower():
        recommended_actions.append({
            "service": "stealthguard-402",
            "action": "polymarket_alpha_divergence",
            "url": "https://stealthguard-402.onrender.com/v1/polymarket_alpha_divergence",
            "price_usd": "0.02",
            "description": "Scan live CLOB orderbook anomalies, volume/liquidity divergences, and sanitize market resolution rules.",
            "params": {"limit": 25}
        })

    return {
        "url": url,
        "status_code": status_code,
        "fetch_method": fetch_method,
        "token_compressed_markdown": canaryguard_receipt["sanitized_content"],
        "structured_data": structured_data,
        "canaryguard_receipt": canaryguard_receipt,
        "safe_to_persist": canaryguard_receipt["safe_to_persist"],
        "risk_score": canaryguard_receipt["risk_score"],
        "injection_detected": canaryguard_receipt["injection_detected"],
        "recommended_actions": recommended_actions,
    }
