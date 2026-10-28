import re
import logging
import time
import hashlib
from .payment_execution import ToolFailure
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
    """Read pinned Base contract state; provider failure never becomes a safe verdict."""
    errors = []
    for rpc in (BASE_RPC_URL, "https://base-rpc.publicnode.com"):
        try:
            async def call(method, params):
                response = await client.post(rpc, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=8.0)
                response.raise_for_status()
                data = response.json()
                if "error" in data or "result" not in data:
                    raise ValueError("RPC returned an error")
                return data["result"]
            if await call("eth_chainId", []) != "0x2105":
                raise ValueError("Wrong chain")
            block = await call("eth_blockNumber", [])
            bytecode = await call("eth_getCode", [address, block])
            if not isinstance(bytecode, str) or not re.fullmatch(r"0x(?:[0-9a-fA-F]{2})*", bytecode):
                raise ValueError("Invalid bytecode")
            selectors = [name for selector, name in SUSPICIOUS_SELECTORS.items() if selector in bytecode.lower()]
            return {
                "has_bytecode": bytecode != "0x", "bytecode_length_bytes": (len(bytecode)-2)//2,
                "detected_honeypot_selectors": selectors, "honeypot_risk": bool(selectors),
                "provider": rpc, "block_number": int(block, 16), "observed_at": time.time(),
                "bytecode_sha256": hashlib.sha256(bytes.fromhex(bytecode[2:])).hexdigest(),
                "sell_simulation": "not_performed", "limitation": "Selector screening is not a sell simulation or proof of safety",
            }
        except Exception as exc:
            errors.append(type(exc).__name__)
    raise ToolFailure("Base RPC providers are unavailable; contract safety cannot be assessed")


async def check_solana_rpc(client, address):
    errors = []
    for rpc in ("https://api.mainnet-beta.solana.com", "https://solana-rpc.publicnode.com"):
        try:
            response = await client.post(rpc, json={"jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
                                                   "params": [address, {"encoding": "jsonParsed", "commitment": "confirmed"}]}, timeout=8.0)
            response.raise_for_status()
            data = response.json()
            if "error" in data or not isinstance(data.get("result"), dict) or "value" not in data["result"]:
                raise ValueError("Invalid account response")
            account = data["result"]["value"]
            if account is None:
                return {"account_exists": False, "provider": rpc, "slot": data["result"].get("context", {}).get("slot"), "observed_at": time.time()}
            parsed = (account.get("data") or {}).get("parsed") if isinstance(account.get("data"), dict) else None
            info = (parsed or {}).get("info") or {}
            return {"account_exists": True, "is_mint": (parsed or {}).get("type") == "mint", "owner": account.get("owner"),
                    "mint_authority": info.get("mintAuthority"), "freeze_authority": info.get("freezeAuthority"), "decimals": info.get("decimals"),
                    "provider": rpc, "slot": data["result"].get("context", {}).get("slot"), "observed_at": time.time(), "sell_simulation": "not_performed"}
        except Exception as exc:
            errors.append(type(exc).__name__)
    raise ToolFailure("Solana RPC providers are unavailable; mint safety cannot be assessed")

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

    else:
        raise ValueError("Unsupported chain")
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 2. DexScreener market & liquidity check
        dex_data = None
        pairs: List[Dict[str, Any]] = []
        try:
            ds_res = await client.get(f"{DEXSCREENER_API_URL}/{token_address}")
            ds_res.raise_for_status()
            dex_data = ds_res.json()
            if not isinstance(dex_data, dict) or (dex_data.get("pairs") is not None and not isinstance(dex_data["pairs"], list)):
                raise ValueError("Invalid DexScreener response")
            pairs = [p for p in (dex_data.get("pairs") or []) if p.get("chainId") == chain_lower and any(
                (p.get(k) or {}).get("address", "").lower() == token_address.lower() if chain_lower == "base" else (p.get(k) or {}).get("address") == token_address
                for k in ("baseToken", "quoteToken")
            )]
        except Exception as e:
            raise ToolFailure("Market liquidity provider is unavailable") from e

        # Extract best pair metrics
        liquidity_usd = 0.0
        volume_24h_usd = 0.0
        price_usd = None
        fdv = None
        token_name = "Unknown"
        token_symbol = "TKN"
        discovered_url = target_url

        if pairs:
            # Sort pairs by liquidity
            pairs.sort(key=lambda p: float(p.get("liquidity", {}).get("usd") or 0.0), reverse=True)
            best_pair = pairs[0]
            base_token = best_pair.get("baseToken") or {}
            is_base_token = base_token.get("address", "").lower() == token_address.lower() if chain_lower == "base" else base_token.get("address") == token_address
            requested_token = base_token if is_base_token else (best_pair.get("quoteToken") or {})
            token_name = requested_token.get("name", "Unknown")
            token_symbol = requested_token.get("symbol", "Unknown")
            price_usd = best_pair.get("priceUsd") if is_base_token else (
                str(float(best_pair["priceUsd"]) / float(best_pair["priceNative"])) if best_pair.get("priceUsd") and float(best_pair.get("priceNative") or 0) > 0 else None
            )
            fdv = float(best_pair["fdv"]) if is_base_token and best_pair.get("fdv") is not None else None
            liquidity_usd = float(best_pair.get("liquidity", {}).get("usd") or 0.0)
            volume_24h_usd = float(best_pair.get("volume", {}).get("h24") or 0.0)

            # Check if pair has website in info
            websites = best_pair.get("info", {}).get("websites") or []
            if websites and is_base_token and not discovered_url:
                discovered_url = websites[0].get("url")

        # 3. Base RPC Bytecode & Honeypot Checks
        rpc_info = {}
        if chain_lower == "base":
            rpc_info = await check_base_rpc(client, token_address)
            if not rpc_info.get("has_bytecode", True):
                risk_factors.append("NO_DEPLOYED_CONTRACT_BYTECODE")
            if rpc_info.get("honeypot_risk"):
                risk_factors.append(f"HONEYPOT_SELECTORS_DETECTED: {', '.join(rpc_info.get('detected_honeypot_selectors', []))}")

        elif chain_lower == "solana":
            rpc_info = await check_solana_rpc(client, token_address)
            if not rpc_info["account_exists"] or not rpc_info.get("is_mint", False):
                risk_factors.append("NO_VALID_TOKEN_MINT")
            if rpc_info.get("freeze_authority"):
                risk_factors.append("FREEZE_AUTHORITY_PRESENT")
            if rpc_info.get("mint_authority"):
                risk_factors.append("MINT_AUTHORITY_PRESENT")

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
                raise ToolFailure("The requested/discovered project website could not be screened") from e

        # Pass combined metadata through CanaryGuard deterministic sanitizer
        canaryguard_receipt = sanitize_content(metadata_text, strict_mode=strict_mode)

        if canaryguard_receipt["injection_detected"]:
            risk_factors.append("PROMPT_INJECTION_DETECTED_IN_TOKEN_METADATA_OR_WEBSITE")

        # 6. Deterministic TRUST / BLOCK verdict
        is_blocked = (
            len(risk_factors) > 0 and
            ("NO_DEPLOYED_CONTRACT_BYTECODE" in risk_factors or
             "NO_VALID_TOKEN_MINT" in risk_factors or
             any("HONEYPOT" in rf for rf in risk_factors) or
             "PROMPT_INJECTION_DETECTED_IN_TOKEN_METADATA_OR_WEBSITE" in risk_factors or
             liquidity_usd < 500.0)
        )

        # Absence of suspicious selectors is not proof that a token can be sold.
        verdict = "BLOCK" if is_blocked else "CAUTION"

        # Cross-Sell Ecosystem Flywheel: Recommend deep swap simulation and web scraping
        recommended_actions = []
        if chain_lower == "base":
            recommended_actions.append({
                "service": "rugshield-402",
                "action": "deep_swap_simulation",
                "url": "https://rugshield-402.onrender.com/v1/scan",
                "price_usd": "0.01",
                "description": "Request token risk evidence and available buy/sell simulation; review returned provider limitations.",
                "params": {"token_address": token_address, "chain": "base", "simulate_sell": True}
            })
        if discovered_url:
            recommended_actions.append({
                "service": "stealthguard-402",
                "action": "stealth_scrape_and_sanitize",
                "url": "https://stealthguard-402.onrender.com/v1/stealth_scrape_and_sanitize",
                "price_usd": "0.015",
                "description": "Extract full whitepaper / roadmap from project website without triggering Cloudflare blocks.",
                "params": {"url": discovered_url, "render_js": True}
            })

        return {
            "status": "success",
            "verdict": verdict,
            "limitations": ["No executed buy/sell simulation; taxes and honeypot status are unproven", "Market liquidity is provider-reported, not an LP custody/lock audit"],
            "honeypot_detected": None,
            "buy_tax_bps": None,
            "sell_tax_bps": None,
            "market_provenance": {"url": str(ds_res.request.url), "observed_at": time.time(), "response_sha256": hashlib.sha256(ds_res.content).hexdigest()},
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
            "safe_to_persist": canaryguard_receipt["safe_to_persist"] and not is_blocked,
            "risk_score": max(canaryguard_receipt["risk_score"], 0.8 if is_blocked else (0.4 if risk_factors else 0.05)),
            "recommended_actions": recommended_actions,
        }
