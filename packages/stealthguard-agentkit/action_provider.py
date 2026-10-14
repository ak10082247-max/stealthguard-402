import json
from typing import Dict, Any, Optional
from cdp_agentkit_core.actions import ActionProvider, create_action
from pydantic import BaseModel, Field
import httpx

class StealthScrapeInput(BaseModel):
    url: str = Field(..., description="Target website URL to bypass Cloudflare anti-bot and scrape clean markdown from.")
    render_js: bool = Field(False, description="Whether to trigger headless stealth browser rendering for SPAs.")

class PolymarketAlphaInput(BaseModel):
    limit: int = Field(10, description="Number of top divergence markets to scan (1-50).")
    category: Optional[str] = Field(None, description="Category filter (e.g., crypto, macro).")

class TokenGateInput(BaseModel):
    token_address: str = Field(..., description="Base EVM token address (0x...) to audit for honeypot and liquidity risk.")

class StealthGuardActionProvider(ActionProvider):
    """
    Action provider for StealthGuard-402, CanaryGuard, and RugShield ecosystem.
    Provides autonomous Coinbase AgentKit agents with Cloudflare stealth scraping,
    Polymarket CLOB smart-money divergence alpha, and Base DEX pre-trade honeypot gating.
    """
    def __init__(self, base_url: str = "https://stealthguard-402.onrender.com"):
        super().__init__("stealthguard", [])
        self.base_url = base_url.rstrip("/")

    @create_action(
        name="stealth_scrape_and_sanitize",
        description="Bypasses Cloudflare / anti-bot protections via Scrapling, extracts clean DOM to LLM Markdown, and runs CanaryGuard prompt-injection firewall.",
        args_schema=StealthScrapeInput,
    )
    def stealth_scrape(self, url: str, render_js: bool = False) -> str:
        with httpx.Client(timeout=25.0) as client:
            resp = client.get(f"{self.base_url}/v1/stealth_scrape_and_sanitize", params={"url": url, "render_js": render_js})
            return resp.text

    @create_action(
        name="polymarket_alpha_divergence",
        description="Scans live Polymarket CLOB orderbook anomalies, volume/liquidity divergences, and smart-money whale accumulation.",
        args_schema=PolymarketAlphaInput,
    )
    def polymarket_alpha(self, limit: int = 10, category: Optional[str] = None) -> str:
        params = {"limit": limit}
        if category:
            params["category"] = category
        with httpx.Client(timeout=25.0) as client:
            resp = client.get(f"{self.base_url}/v1/polymarket_alpha_divergence", params=params)
            return resp.text

    @create_action(
        name="pre_trade_agent_gate",
        description="Deterministic TRUST or BLOCK gate combining on-chain Base liquidity/honeypot checks with CanaryGuard prompt-injection firewall.",
        args_schema=TokenGateInput,
    )
    def token_gate(self, token_address: str) -> str:
        with httpx.Client(timeout=25.0) as client:
            resp = client.get(f"{self.base_url}/v1/pre_trade_agent_gate", params={"token_or_service_address": token_address, "chain": "base"})
            return resp.text
