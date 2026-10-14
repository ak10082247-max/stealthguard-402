/**
 * StealthGuard-402 - Apify Actor TypeScript Entrypoint
 * Provides standard Pay-Per-Event (PPE) execution path for Apify bridges
 * (Apify Fiat, Apify Direct x402, and Skyfire).
 */

import { Actor } from 'apify';

interface ActorInput {
  tool?: 'stealth_scrape_and_sanitize' | 'polymarket_alpha_divergence' | 'pre_trade_agent_gate' | 'health_and_sample';
  url?: string;
  extract_schema?: Record<string, any>;
  render_js?: boolean;
  category?: string;
  limit?: number;
  token_or_service_address?: string;
  chain?: 'base' | 'solana';
  target_url?: string;
  strict_mode?: boolean;
  include_samples?: boolean;
}

const API_SERVER_URL = process.env.API_SERVER_URL || 'http://127.0.0.1:8000';

async function main() {
  await Actor.init();
  const input = (await Actor.getInput<ActorInput>()) || {};
  const tool = input.tool || 'stealth_scrape_and_sanitize';

  try {
    let result: any = null;

    if (tool === 'stealth_scrape_and_sanitize') {
      // 1 PPE event ($0.02)
      await Actor.charge({ eventName: 'stealth_scrape_and_sanitize', count: 1 });
      const resp = await fetch(`${API_SERVER_URL}/v1/stealth_scrape_and_sanitize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-PAYMENT': 'apify_ppe_settled' },
        body: JSON.stringify({
          url: input.url || 'https://example.com',
          extract_schema: input.extract_schema,
          render_js: input.render_js ?? false,
          strict_mode: input.strict_mode ?? true,
        }),
      });
      result = await resp.json();
    } else if (tool === 'polymarket_alpha_divergence') {
      // 2 PPE events ($0.025 * 2 = $0.05)
      await Actor.charge({ eventName: 'polymarket_alpha_divergence', count: 2 });
      const resp = await fetch(`${API_SERVER_URL}/v1/polymarket_alpha_divergence`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-PAYMENT': 'apify_ppe_settled' },
        body: JSON.stringify({
          category: input.category,
          limit: input.limit ?? 25,
          strict_mode: input.strict_mode ?? true,
        }),
      });
      result = await resp.json();
    } else if (tool === 'pre_trade_agent_gate') {
      // 1 PPE event ($0.03)
      await Actor.charge({ eventName: 'pre_trade_agent_gate', count: 1 });
      const resp = await fetch(`${API_SERVER_URL}/v1/pre_trade_agent_gate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-PAYMENT': 'apify_ppe_settled' },
        body: JSON.stringify({
          token_or_service_address: input.token_or_service_address || '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',
          chain: input.chain || 'base',
          target_url: input.target_url,
          strict_mode: input.strict_mode ?? true,
        }),
      });
      result = await resp.json();
    } else if (tool === 'health_and_sample') {
      // Free Discovery Probe (0 events)
      const resp = await fetch(`${API_SERVER_URL}/v1/health_and_sample?include_samples=true`);
      result = await resp.json();
    }

    await Actor.pushData(result);
  } catch (err: any) {
    await Actor.fail(`Error in ${tool}: ${err.message}`);
  } finally {
    await Actor.exit();
  }
}

main().catch(console.error);
