# stealthguard-agentkit

Official [Coinbase AgentKit](https://github.com/coinbase/agentkit) Action Provider for **StealthGuard-402**, **CanaryGuard**, and **RugShield** on Base Mainnet (`eip155:8453`).

Gives autonomous Python AI agents using Coinbase CDP AgentKit native tool actions:
1. `stealth_scrape_and_sanitize`: Scrapes Cloudflare-protected web pages into clean LLM markdown with CanaryGuard prompt-injection firewall verification.
2. `polymarket_alpha_divergence`: Pulls real-time Polymarket prediction market volume spikes and smart-money divergence.
3. `pre_trade_agent_gate`: Audits Base DEX liquidity and honeypot risk before broadcasting swap transactions.

## Installation

```bash
pip install stealthguard-agentkit
```

## Usage with Coinbase AgentKit

```python
from cdp_agentkit_core import AgentKit, AgentKitConfig
from stealthguard_agentkit.action_provider import StealthGuardActionProvider

stealth_provider = StealthGuardActionProvider(base_url="https://stealthguard-402.onrender.com")

agent_kit = AgentKit(
    AgentKitConfig(
        action_providers=[stealth_provider]
    )
)

tools = agent_kit.get_actions()
print(f"Loaded {len(tools)} StealthGuard actions into agent toolkit.")
```

Settlement: Base USDC (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`).
License: MIT
