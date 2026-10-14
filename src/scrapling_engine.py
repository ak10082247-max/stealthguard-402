import asyncio
import logging
import json
import re
from typing import Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup
from .sanitizer import sanitize_content

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
        try:
            from scrapling.fetchers import Fetcher, StealthyFetcher

            if render_js:
                try:
                    # StealthyFetcher with Patchright / Playwright
                    res = StealthyFetcher.fetch(url, headless=True, timeout=20000)
                    m = res.markdown() if callable(getattr(res, 'markdown', None)) else res.text
                    return res.html_content, m, res.status, "scrapling_stealthy_patchright"
                except Exception as e:
                    logger.warning(f"StealthyFetcher failed or browser not ready, falling back to Fetcher: {e}")

            # Standard fast Scrapling fetcher (curl-cffi impersonation)
            res = Fetcher.get(url, headers=STEALTH_HEADERS, timeout=15)
            # Check for Cloudflare challenge markers
            is_cf_challenge = (
                res.status in (403, 503) or
                "Just a moment..." in res.html_content or
                "cf-browser-verification" in res.html_content
            )
            if is_cf_challenge and not render_js:
                try:
                    from scrapling.fetchers import StealthyFetcher
                    res_stealth = StealthyFetcher.fetch(url, headless=True, timeout=20000)
                    m = res_stealth.markdown() if callable(getattr(res_stealth, 'markdown', None)) else res_stealth.text
                    return res_stealth.html_content, m, res_stealth.status, "scrapling_stealthy_challenge_bypassed"
                except Exception as stealth_err:
                    logger.warning(f"Stealthy challenge bypass fallback failed: {stealth_err}")

            m = res.markdown() if callable(getattr(res, 'markdown', None)) else res.text
            return res.html_content, m, res.status, "scrapling_fetcher"
        except Exception as err:
            logger.warning(f"Scrapling fetch error: {err}, falling back to direct httpx")
            import httpx
            with httpx.Client(follow_redirects=True, headers=STEALTH_HEADERS, timeout=15.0) as client:
                resp = client.get(url)
                from markdownify import markdownify
                md = markdownify(resp.text)
                return resp.text, md, resp.status_code, "httpx_stealth_fallback"

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

    # Cross-Sell Ecosystem Flywheel: Recommend actions based on discovered assets and links
    recommended_actions = []
    token_matches = re.findall(r'\b0x[a-fA-F0-9]{40}\b', combined_raw_text)
    dex_markers = ["dexscreener.com", "aerodrome.finance", "app.uniswap.org", "basescan.org/token", "basescan.org/address", "clanker.world"]
    has_dex = any(d in combined_raw_text.lower() for d in dex_markers)

    if token_matches or has_dex:
        detected_token = token_matches[0] if token_matches else "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
        recommended_actions.append({
            "service": "stealthguard-402",
            "action": "pre_trade_agent_gate",
            "url": "https://stealthguard-402.onrender.com/v1/pre_trade_agent_gate",
            "price_usd": "0.03",
            "description": "Verify token bytecode, DexScreener LP depth, and sanitize metadata via CanaryGuard firewall before trading.",
            "params": {"token_or_service_address": detected_token, "chain": "base"}
        })
        recommended_actions.append({
            "service": "rugshield-402",
            "action": "deep_swap_simulation",
            "url": "https://rugshield-402.onrender.com/v1/scan",
            "price_usd": "0.005",
            "description": "Execute forked-mempool buy/sell tax simulation, honeypot detection, and liquidity lock analysis.",
            "params": {"token_address": detected_token, "chain_id": 8453}
        })
    elif "polymarket" in combined_raw_text.lower() or "prediction market" in combined_raw_text.lower() or "odds" in combined_raw_text.lower():
        recommended_actions.append({
            "service": "stealthguard-402",
            "action": "polymarket_alpha_divergence",
            "url": "https://stealthguard-402.onrender.com/v1/polymarket_alpha_divergence",
            "price_usd": "0.05",
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
