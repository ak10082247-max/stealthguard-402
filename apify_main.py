import asyncio
import logging
from typing import Dict, Any
from apify import Actor

from src.scrapling_engine import stealth_scrape_and_sanitize
from src.polymarket_engine import scan_polymarket_alpha
from src.token_gate_engine import pre_trade_agent_gate
from src.mcp_server import generate_health_and_sample_payload
from src.config import TOOL_PRICING

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("stealthguard.apify")

async def run_actor():
    """
    Apify Pay-Per-Event (PPE) Actor entrypoint.
    Charges the configured PPE events before executing the pipeline and pushes results to default Dataset.
    Enables Apify Fiat, Apify Direct x402 (mcp.apify.com?payment=x402), and Skyfire bridges.
    """
    async with Actor:
        actor_input: Dict[str, Any] = await Actor.get_input() or {}
        tool_name = actor_input.get("tool", "stealth_scrape_and_sanitize")
        logger.info(f"StealthGuard-402 Apify Actor invoked for tool: {tool_name}")

        pricing = TOOL_PRICING.get(tool_name)
        if not pricing and tool_name != "health_and_sample":
            err = f"Unknown tool: '{tool_name}'. Available: {list(TOOL_PRICING.keys())}"
            logger.error(err)
            await Actor.fail(status_message=err)
            return

        result: Dict[str, Any] = {}

        try:
            if tool_name == "stealth_scrape_and_sanitize":
                # Charge 1 event ($0.02)
                logger.info("Charging 1 event: stealth_scrape_and_sanitize ($0.02)")
                await Actor.charge(event_name="stealth_scrape_and_sanitize", count=1)
                result = await stealth_scrape_and_sanitize(
                    url=actor_input.get("url", "https://example.com"),
                    extract_schema=actor_input.get("extract_schema"),
                    render_js=actor_input.get("render_js", False),
                    strict_mode=actor_input.get("strict_mode", True),
                )

            elif tool_name == "polymarket_alpha_divergence":
                # Charge 2 events ($0.025 * 2 = $0.05)
                logger.info("Charging 2 events: polymarket_alpha_divergence ($0.05 total)")
                await Actor.charge(event_name="polymarket_alpha_divergence", count=2)
                result = await scan_polymarket_alpha(
                    category=actor_input.get("category"),
                    limit=actor_input.get("limit", 25),
                    strict_mode=actor_input.get("strict_mode", True),
                )

            elif tool_name == "pre_trade_agent_gate":
                # Charge 1 event ($0.03)
                logger.info("Charging 1 event: pre_trade_agent_gate ($0.03)")
                await Actor.charge(event_name="pre_trade_agent_gate", count=1)
                result = await pre_trade_agent_gate(
                    token_or_service_address=actor_input.get("token_or_service_address", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"),
                    chain=actor_input.get("chain", "base"),
                    target_url=actor_input.get("target_url"),
                    strict_mode=actor_input.get("strict_mode", True),
                )

            elif tool_name == "health_and_sample":
                # Free discovery probe - no event charge
                logger.info("Free discovery probe: health_and_sample (0 charges)")
                result = generate_health_and_sample_payload(
                    include_samples=actor_input.get("include_samples", True)
                )

            # Push sanitized payload to the default Apify Dataset
            await Actor.push_data(result)
            logger.info("Successfully pushed sanitized output to Apify Dataset.")

        except Exception as e:
            logger.error(f"Error during tool execution: {e}", exc_info=True)
            await Actor.fail(status_message=f"Execution error in {tool_name}: {str(e)}")

if __name__ == "__main__":
    asyncio.run(run_actor())
