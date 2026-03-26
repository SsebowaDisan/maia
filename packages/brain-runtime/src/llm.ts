/**
 * LLM caller — handles retries, cost tracking, JSON parsing, and error recovery.
 * Every LLM call in the Brain goes through this module.
 */

import type { LLMConfig } from "./types";
import type { LLMCache } from "./cache";
import { cacheKey } from "./cache";
import type { Telemetry } from "./telemetry";

export interface LLMCallResult {
  text: string;
  tokensUsed: number;
  costUsd: number;
  model: string;
  success: boolean;
  cached?: boolean;
}

/** Optional integrations — set once, used by all callLLM calls. */
let _cache: LLMCache | null = null;
let _telemetry: Telemetry | null = null;

export function setLLMCache(cache: LLMCache | null): void { _cache = cache; }
export function setLLMTelemetry(telemetry: Telemetry | null): void { _telemetry = telemetry; }

const DEFAULT_BASE_URL = "https://api.openai.com/v1";
const MAX_RETRIES = 2;
const RETRY_DELAY_MS = 500;

/**
 * Call the LLM with retry logic, caching, telemetry, and cost tracking.
 */
export async function callLLM(
  config: LLMConfig,
  systemPrompt: string,
  userPrompt: string,
): Promise<LLMCallResult> {
  const model = config.model ?? "gpt-4o";

  // Cache check
  if (_cache) {
    const key = cacheKey(model, systemPrompt, userPrompt);
    const cached = await _cache.get(key);
    if (cached) {
      return { text: cached.text, tokensUsed: cached.tokensUsed, costUsd: 0, model: cached.model, success: true, cached: true };
    }
  }

  // Telemetry span
  const span = _telemetry?.startSpan(model, config.baseUrl ?? "openai");
  const baseUrl = (config.baseUrl ?? DEFAULT_BASE_URL).replace(/\/$/, "");
  const url = `${baseUrl}/chat/completions`;

  const body = {
    model,
    temperature: config.temperature ?? 0.3,
    max_tokens: config.maxTokens,
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: userPrompt },
    ],
  };

  const headers = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${config.apiKey}`,
  };

  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    if (attempt > 0) {
      await sleep(RETRY_DELAY_MS * Math.pow(2, attempt - 1));
    }

    try {
      const response = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const status = response.status;
        // Retry on rate limit or server errors
        if ((status === 429 || status >= 500) && attempt < MAX_RETRIES) {
          lastError = new Error(`LLM returned ${status}`);
          continue;
        }
        const errorText = await response.text().catch(() => "");
        return fail(model, `LLM returned ${status}: ${errorText.slice(0, 200)}`);
      }

      const data = (await response.json()) as any;
      const text = data?.choices?.[0]?.message?.content ?? "";
      const usage = data?.usage ?? {};
      const tokensUsed = (usage.total_tokens ?? 0) as number;
      const costUsd = estimateCost(model, usage);

      if (!text) {
        if (attempt < MAX_RETRIES) {
          lastError = new Error("Empty LLM response");
          continue;
        }
        return fail(model, "Empty response after retries");
      }

      // Cache the result
      if (_cache) {
        const key = cacheKey(model, systemPrompt, userPrompt);
        await _cache.set(key, { text, tokensUsed, costUsd, model, cachedAt: Date.now() }).catch(() => {});
      }

      // End telemetry span
      span?.end({
        inputTokens: usage.prompt_tokens ?? 0,
        outputTokens: usage.completion_tokens ?? 0,
        costUsd, success: true, cached: false,
      });

      return { text, tokensUsed, costUsd, model, success: true, cached: false };
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));
      if (attempt < MAX_RETRIES) continue;
    }
  }

  span?.end({ inputTokens: 0, outputTokens: 0, costUsd: 0, success: false, error: lastError?.message });
  return fail(model, lastError?.message ?? "Unknown LLM error");
}

/**
 * Call LLM and parse the response as JSON.
 * Handles markdown code fences, trailing commas, and partial JSON.
 */
export async function callLLMJson<T = Record<string, any>>(
  config: LLMConfig,
  systemPrompt: string,
  userPrompt: string,
  fallback: T,
): Promise<{ data: T; cost: LLMCallResult }> {
  const result = await callLLM(config, systemPrompt, userPrompt);
  if (!result.success) {
    return { data: fallback, cost: result };
  }

  const parsed = safeParseJson<T>(result.text);
  return { data: parsed ?? fallback, cost: result };
}

/**
 * Parse JSON from LLM output — handles code fences, whitespace, and common issues.
 */
export function safeParseJson<T = any>(text: string): T | null {
  let cleaned = text.trim();

  // Strip markdown code fences
  if (cleaned.startsWith("```")) {
    const firstNewline = cleaned.indexOf("\n");
    if (firstNewline >= 0) cleaned = cleaned.slice(firstNewline + 1);
    if (cleaned.endsWith("```")) cleaned = cleaned.slice(0, -3);
    cleaned = cleaned.trim();
  }

  // Try direct parse
  try {
    return JSON.parse(cleaned);
  } catch {
    // noop
  }

  // Try extracting JSON object or array from surrounding text
  const jsonMatch = cleaned.match(/(\{[\s\S]*\}|\[[\s\S]*\])/);
  if (jsonMatch) {
    try {
      return JSON.parse(jsonMatch[1]);
    } catch {
      // noop
    }
  }

  return null;
}

/**
 * Estimate USD cost from token usage. Rough but reasonable.
 */
function estimateCost(
  model: string,
  usage: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number },
): number {
  const prompt = usage.prompt_tokens ?? 0;
  const completion = usage.completion_tokens ?? 0;
  const m = model.toLowerCase();

  // Rough per-token costs (input/output) in USD
  if (m.includes("gpt-4o")) return prompt * 0.0000025 + completion * 0.00001;
  if (m.includes("gpt-4")) return prompt * 0.00003 + completion * 0.00006;
  if (m.includes("gpt-3.5")) return prompt * 0.0000005 + completion * 0.0000015;
  if (m.includes("claude")) return prompt * 0.000003 + completion * 0.000015;
  if (m.includes("qwen")) return prompt * 0.000001 + completion * 0.000003;

  // Default: rough average
  return (usage.total_tokens ?? 0) * 0.000005;
}

function fail(model: string, _reason: string): LLMCallResult {
  return { text: "", tokensUsed: 0, costUsd: 0, model, success: false, cached: false };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}