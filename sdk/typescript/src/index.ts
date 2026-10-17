/**
 * StealthGuard 402 - Official TypeScript / Node SDK
 *
 * Anti-bot stealth web scraper (Scrapling), Polymarket smart-money alpha divergence,
 * and pre-trade autonomous security gate on Base (eip155:8453) via x402.
 */

import { x402Client } from "@x402/core/client";
import { ExactEvmScheme } from "@x402/evm/exact/client";
import { wrapFetchWithPayment } from "@x402/fetch";
import { privateKeyToAccount } from "viem/accounts";

export interface PreTradeGateResult {
  status: "TRUST" | "BLOCK" | "CAUTION";
  token_or_service_address: string;
  chain: string;
  is_honeypot: boolean;
  liquidity_usd?: number;
  injection_detected: boolean;
  verdict: string;
  safety_receipt?: string;
  timestamp: number;
}

export interface StealthScrapeResult {
  status: string;
  url: string;
  markdown_content: string;
  sanitization_status: string;
  threats_neutralized: string[];
  safety_receipt: string;
  timestamp: number;
}

export interface PolymarketAlphaResult {
  status: string;
  category: string;
  divergences_detected: Array<{
    market_id: string;
    question: string;
    whale_bias: string;
    implied_probability: number;
    spread_bps: number;
    alpha_score: number;
  }>;
  safety_receipt: string;
  timestamp: number;
}

export class StealthGuardClient {
  private baseUrl: string;
  private payingFetch: typeof fetch;

  constructor(options?: {
    baseUrl?: string;
    privateKey?: `0x${string}`;
    customFetch?: typeof fetch;
  }) {
    this.baseUrl = (options?.baseUrl ?? "https://stealthguard-402.onrender.com").replace(/\/$/, "");

    if (options?.privateKey) {
      const account = privateKeyToAccount(options.privateKey);
      const client = new x402Client();
      client.register("eip155:8453", new ExactEvmScheme(account));

      const expectedMerchant = "0x73279fa4bada7cac888c62cda4f5c8104765f6f1";
      const baseUsdc = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913";
      const maxPerCallMicroUsdc = 250000n; // 0.250 USDC max for deep dossiers

      client.onBeforePaymentCreation(async (context) => {
        const req = context.selectedRequirements;
        if (req.network !== "eip155:8453") {
          throw new Error(`Rejected network ${req.network}: Base mainnet required`);
        }
        if (req.asset.toLowerCase() !== baseUsdc) {
          throw new Error(`Rejected asset ${req.asset}: Base USDC required`);
        }
        if (req.payTo.toLowerCase() !== expectedMerchant) {
          throw new Error(`Rejected payTo ${req.payTo}: Unauthorized merchant recipient`);
        }
        if (BigInt(req.amount) > maxPerCallMicroUsdc) {
          throw new Error(`Amount ${req.amount} exceeds max per-call cap of ${maxPerCallMicroUsdc}`);
        }
      });

      this.payingFetch = wrapFetchWithPayment(options.customFetch ?? fetch, client);
    } else {
      this.payingFetch = options?.customFetch ?? fetch;
    }
  }

  /**
   * Free evaluation preview without wallet or x402 payment header.
   */
  async preTradeGatePreview(tokenOrAddress: string, chain: string = "base"): Promise<PreTradeGateResult> {
    const res = await fetch(`${this.baseUrl}/v1/pre_trade_agent_gate/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token_or_service_address: tokenOrAddress, chain, strict_mode: true }),
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`StealthGuard Preview HTTP ${res.status}: ${errText}`);
    }

    return (await res.json()) as PreTradeGateResult;
  }

  /**
   * Deterministic TRUST or BLOCK gate combining liquidity, honeypot checks, and CanaryGuard injection scrubbing (0.010 USDC).
   */
  async preTradeGate(
    tokenOrAddress: string,
    options?: { chain?: string; strictMode?: boolean }
  ): Promise<PreTradeGateResult> {
    const res = await this.payingFetch(`${this.baseUrl}/v1/pre_trade_agent_gate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        token_or_service_address: tokenOrAddress,
        chain: options?.chain ?? "base",
        strict_mode: options?.strictMode ?? true,
      }),
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`StealthGuard Pre-Trade Gate HTTP ${res.status}: ${errText}`);
    }

    return (await res.json()) as PreTradeGateResult;
  }

  /**
   * Bypass Cloudflare Turnstile anti-bot via Scrapling, extract clean DOM to Markdown, and scrub prompt injections (0.015 USDC).
   */
  async stealthScrape(
    url: string,
    options?: { renderJs?: boolean; strictMode?: boolean }
  ): Promise<StealthScrapeResult> {
    const res = await this.payingFetch(`${this.baseUrl}/v1/stealth_scrape_and_sanitize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url,
        render_js: options?.renderJs ?? false,
        strict_mode: options?.strictMode ?? true,
      }),
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`StealthGuard Scrape HTTP ${res.status}: ${errText}`);
    }

    return (await res.json()) as StealthScrapeResult;
  }

  /**
   * Scan Polymarket CLOB orderbooks for volume spikes and smart-money spread divergence (0.020 USDC).
   */
  async polymarketAlpha(options?: {
    category?: string;
    limit?: number;
    strictMode?: boolean;
  }): Promise<PolymarketAlphaResult> {
    const res = await this.payingFetch(`${this.baseUrl}/v1/polymarket_alpha_divergence`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        category: options?.category ?? "crypto",
        limit: options?.limit ?? 15,
        strict_mode: options?.strictMode ?? true,
      }),
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`StealthGuard Polymarket Alpha HTTP ${res.status}: ${errText}`);
    }

    return (await res.json()) as PolymarketAlphaResult;
  }

  async health(): Promise<{ status: string; service: string }> {
    const res = await fetch(`${this.baseUrl}/health`);
    return await res.json();
  }
}
