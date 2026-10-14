import re
import logging
from typing import Dict, Any, Optional, List
import httpx

from .sanitizer import sanitize_content
from .scrapling_engine import stealth_scrape_and_sanitize

logger = logging.getLogger("stealthguard.token_gate")

BASE_RPC_URL = "https://mainnet.base.org"
DEXSCREENER_API_URL = "https://api.dexscreener.com/latest/dex/tokens"

# Suspicious honeypot / blacklist function selectors in EVM bytecode
SUSPICIOUS_SELECTORS = {
    "44337666": "blacklist(address)",
    "815f949a": "setBots(address[])",
    "c9567bf9": "openTrading()",
    "d65377bf": "setTrading(bool)",
    "851bf54e": "setMaxTxPercent(uint256)",
}

async def check_base_rpc(client: httpx.AsyncClient, address: str) -> Dict[str, Any]:
    """
    Direct Base JSON-RPC checks: deployed bytecode, honeypot selectors.
    """
    try:
        # Check bytecode
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_getCode",
            "params": [address, "latest"]
        }
        res = await client.post(BASE_RPC_URL, json=payload, timeout=6.0)
        data = res.json()
        bytecode = data.get("result", "0x")
        
        has_bytecode = bool(bytecode and bytecode != "0x")
        bytecode_lower = bytecode.lower()

        detected_selectors = []
        for selector, name in SUSPICIOUS_SELECTORS.items():
            if selector in bytecode_lower:
                detected_selectors.append(name)

        return {
            "has_bytecode": has_bytecode,
            "bytecode_length_bytes": len(bytecode) // 2 if has_bytecode else 0,
            "detected_honeypot_selectors": detected_selectors,
            "honeypot_risk": len(detected_selectors) > 0,
        }
    except Exception as e:
        logger.warning(f"Base RPC check error: {e}")
        return {
            "has_bytecode": True,  # Fallback to avoid false positives on RPC hiccup
            "bytecode_length_bytes": 0,
            "detected_honeypot_selectors": [],
            "honeypot_risk": False,
        }

async def pre_trade_agent_gate(
    token_or_service_address: str,
    chain: str = "base",
    target_url: Optional[str] = None,
    strict_mode: bool = True
) -> Dict[str, Any]:
    """
    Deterministic TRUST / BLOCK gate combining on-chain DexScreener + Base/Solana RPC
    liquidity and honeypot inspection with CanaryGuard metadata injection scrubbing.
    """
    token_address = token_or_service_address.strip()
    chain_lower = chain.lower().strip()
    risk_factors: List[str] = []

    # 1. Format validation
    if chain_lower == "base":
        if not re.match(r"^0x[0-9a-fA-F]{40}$", token_address):
            return {
                "verdict": "BLOCK",
                "risk_score": 1.0,
                "reason": "Invalid Base EVM address format",
                "canaryguard_receipt": sanitize_content("Invalid Base EVM address", strict_mode=strict_mode)
            }
    elif chain_lower == "solana":
        if not re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", token_address):
            return {
                "verdict": "BLOCK",
                "risk_score": 1.0,
                "reason": "Invalid Solana public key format",
                "canaryguard_receipt": sanitize_content("Invalid Solana address", strict_mode=strict_mode)
            }

    async with httpx.AsyncClient(timeout=10.0) as client:
        # 2. DexScreener market & liquidity check
        dex_data = None
        pairs: List[Dict[str, Any]] = []
        try:
            ds_res = await client.get(f"{DEXSCREENER_API_URL}/{token_address}")
            if ds_res.status_code == 200:
                dex_data = ds_res.json()
                pairs = dex_data.get("pairs") or []
        except Exception as e:
            logger.warning(f"DexScreener check error: {e}")

        # Extract best pair metrics
        liquidity_usd = 0.0
        volume_24h_usd = 0.0
        price_usd = "0"
        fdv = 0.0
        token_name = "Unknown"
        token_symbol = "TKN"
        discovered_url = target_url

        if pairs:
            # Sort pairs by liquidity
            pairs.sort(key=lambda p: float(p.get("liquidity", {}).get("usd") or 0.0), reverse=True)
            best_pair = pairs[0]
            token_name = best_pair.get("baseToken", {}).get("name", "Unknown")
            token_symbol = best_pair.get("baseToken", {}).get("symbol", "TKN")
            price_usd = best_pair.get("priceUsd", "0")
            fdv = float(best_pair.get("fdv") or 0.0)
            liquidity_usd = float(best_pair.get("liquidity", {}).get("usd") or 0.0)
            volume_24h_usd = float(best_pair.get("volume", {}).get("h24") or 0.0)

            # Check if pair has website in info
            websites = best_pair.get("info", {}).get("websites") or []
            if websites and not discovered_url:
                discovered_url = websites[0].get("url")

        # 3. Base RPC Bytecode & Honeypot Checks
        rpc_info = {}
        if chain_lower == "base":
            rpc_info = await check_base_rpc(client, token_address)
            if not rpc_info.get("has_bytecode", True):
                risk_factors.append("NO_DEPLOYED_CONTRACT_BYTECODE")
            if rpc_info.get("honeypot_risk"):
                risk_factors.append(f"HONEYPOT_SELECTORS_DETECTED: {', '.join(rpc_info.get('detected_honeypot_selectors', []))}")

        # 4. Liquidity risk assessment
        if liquidity_usd < 1000.0:
            risk_factors.append(f"LOW_LIQUIDITY_DEPTH (${liquidity_usd:.2f} USD)")

        # 5. Metadata & website inspection for prompt injection
        metadata_text = f"Token Name: {token_name}\nToken Symbol: {token_symbol}\nAddress: {token_address}"
        if discovered_url:
            try:
                scraped = await stealth_scrape_and_sanitize(discovered_url, render_js=False, strict_mode=strict_mode)
                metadata_text += f"\n\nWebsite Content:\n{scraped['token_compressed_markdown']}"
            except Exception as e:
                logger.warning(f"Could not scrape token website {discovered_url}: {e}")

        # Pass combined metadata through CanaryGuard deterministic sanitizer
        canaryguard_receipt = sanitize_content(metadata_text, strict_mode=strict_mode)

        if canaryguard_receipt["injection_detected"]:
            risk_factors.append("PROMPT_INJECTION_DETECTED_IN_TOKEN_METADATA_OR_WEBSITE")

        # 6. Deterministic TRUST / BLOCK verdict
        is_blocked = (
            len(risk_factors) > 0 and
            ("NO_DEPLOYED_CONTRACT_BYTECODE" in risk_factors or
             any("HONEYPOT" in rf for rf in risk_factors) or
             "PROMPT_INJECTION_DETECTED_IN_TOKEN_METADATA_OR_WEBSITE" in risk_factors or
             liquidity_usd < 500.0)
        )

        verdict = "BLOCK" if is_blocked else ("CAUTION" if risk_factors else "TRUST")

        # Cross-Sell Ecosystem Flywheel: Recommend deep swap simulation and web scraping
        recommended_actions = []
        if chain_lower == "base":
            recommended_actions.append({
                "service": "rugshield-402",
                "action": "deep_swap_simulation",
                "url": "https://rugshield-402.onrender.com/v1/scan",
                "price_usd": "0.005",
                "description": "Forked-mempool swap simulation to verify exact sell tax and liquidity lock duration before committing capital.",
                "params": {"token_address": token_address, "chain_id": 8453}
            })
        if discovered_url:
            recommended_actions.append({
                "service": "stealthguard-402",
                "action": "stealth_scrape_and_sanitize",
                "url": "https://stealthguard-402.onrender.com/v1/stealth_scrape_and_sanitize",
                "price_usd": "0.02",
                "description": "Extract full whitepaper / roadmap from project website without triggering Cloudflare blocks.",
                "params": {"url": discovered_url, "render_js": True}
            })

        return {
            "verdict": verdict,
            "chain": chain_lower,
            "token_address": token_address,
            "token_name": token_name,
            "token_symbol": token_symbol,
            "price_usd": price_usd,
            "liquidity_usd": liquidity_usd,
            "volume_24h_usd": volume_24h_usd,
            "fdv_usd": fdv,
            "rpc_verification": rpc_info,
            "risk_factors": risk_factors,
            "canaryguard_receipt": canaryguard_receipt,
            "safe_to_persist": canaryguard_receipt["safe_to_persist"] and verdict == "TRUST",
            "risk_score": max(canaryguard_receipt["risk_score"], 0.8 if is_blocked else (0.4 if risk_factors else 0.05)),
            "recommended_actions": recommended_actions,
        }
