/**
 * Multi-provider LLM routing with automatic fallback.
 *
 * Supports: OpenAI, Anthropic, Qwen/DashScope, any OpenAI-compatible API.
 * Auto-failover: if provider A fails, try provider B, then C.
 * Per-agent model override: different agents can use different models.
 */

export interface LLMProvider {
  /** Provider name for logging. */
  name: string;
  /** API base URL. */
  baseUrl: string;
  /** API key. */
  apiKey: string;
  /** Default model for this provider. */
  model: string;
  /** Max retries before failover (default: 1). */
  maxRetries?: number;
  /** Request timeout in ms (default: 30000). */
  timeoutMs?: number;
  /** Transform request body for non-OpenAI providers. */
  transformRequest?: (body: any) => any;
  /** Transform response for non-OpenAI providers. */
  transformResponse?: (data: any) => { text: string; tokensUsed: number };
}

export interface ProviderChain {
  providers: LLMProvider[];
  /** Per-role model overrides (e.g., { analyst: "gpt-4o", writer: "claude-sonnet" }). */
  roleModelOverrides?: Record<string, string>;
}

/** Pre-configured provider constructors. */

export function openai(apiKey: string, model: string = "gpt-4o"): LLMProvider {
  return { name: "openai", baseUrl: "https://api.openai.com/v1", apiKey, model };
}

export function anthropic(apiKey: string, model: string = "claude-sonnet-4-20250514"): LLMProvider {
  return {
    name: "anthropic",
    baseUrl: "https://api.anthropic.com/v1",
    apiKey,
    model,
    transformRequest: (body) => ({
      model: body.model,
      max_tokens: body.max_tokens ?? 4096,
      messages: body.messages,
      temperature: body.temperature,
    }),
    transformResponse: (data) => ({
      text: data?.content?.[0]?.text ?? "",
      tokensUsed: (data?.usage?.input_tokens ?? 0) + (data?.usage?.output_tokens ?? 0),
    }),
  };
}

export function qwen(apiKey: string, model: string = "qwen3.5-35b-a3b"): LLMProvider {
  return {
    name: "qwen",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    apiKey, model,
  };
}

export function custom(name: string, baseUrl: string, apiKey: string, model: string): LLMProvider {
  return { name, baseUrl, apiKey, model };
}

/**
 * Call LLM with provider chain — tries each provider in order until one succeeds.
 */
export async function callWithProviderChain(
  chain: ProviderChain,
  systemPrompt: string,
  userPrompt: string,
  options?: { roleId?: string; temperature?: number; maxTokens?: number },
): Promise<{ text: string; tokensUsed: number; costUsd: number; model: string; provider: string; success: boolean }> {
  const temp = options?.temperature ?? 0.3;
  const maxTokens = options?.maxTokens;

  // Resolve model: check role override first
  const roleModel = options?.roleId ? chain.roleModelOverrides?.[options.roleId] : undefined;

  for (const provider of chain.providers) {
    const model = roleModel ?? provider.model;
    const url = `${provider.baseUrl.replace(/\/$/, "")}/chat/completions`;
    const retries = provider.maxRetries ?? 1;
    const timeout = provider.timeoutMs ?? 30000;

    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        let body: any = {
          model,
          temperature: temp,
          messages: [
            { role: "system", content: systemPrompt },
            { role: "user", content: userPrompt },
          ],
        };
        if (maxTokens) body.max_tokens = maxTokens;
        if (provider.transformRequest) body = provider.transformRequest(body);

        const headers: Record<string, string> = { "Content-Type": "application/json" };
        if (provider.name === "anthropic") {
          headers["x-api-key"] = provider.apiKey;
          headers["anthropic-version"] = "2023-06-01";
        } else {
          headers["Authorization"] = `Bearer ${provider.apiKey}`;
        }

        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeout);

        const response = await fetch(url, {
          method: "POST", headers, body: JSON.stringify(body), signal: controller.signal,
        });
        clearTimeout(timer);

        if (!response.ok) {
          if ((response.status === 429 || response.status >= 500) && attempt < retries) {
            await sleep(500 * Math.pow(2, attempt));
            continue;
          }
          break; // Try next provider
        }

        const data = await response.json() as any;
        let text: string;
        let tokensUsed: number;

        if (provider.transformResponse) {
          const r = provider.transformResponse(data);
          text = r.text;
          tokensUsed = r.tokensUsed;
        } else {
          text = data?.choices?.[0]?.message?.content ?? "";
          tokensUsed = data?.usage?.total_tokens ?? 0;
        }

        if (!text && attempt < retries) continue;
        if (!text) break; // Try next provider

        return {
          text, tokensUsed,
          costUsd: estimateProviderCost(provider.name, model, data?.usage ?? {}),
          model, provider: provider.name, success: true,
        };
      } catch {
        if (attempt < retries) { await sleep(500 * Math.pow(2, attempt)); continue; }
        break; // Try next provider
      }
    }
  }

  return { text: "", tokensUsed: 0, costUsd: 0, model: "", provider: "", success: false };
}

function estimateProviderCost(provider: string, model: string, usage: any): number {
  const p = usage.prompt_tokens ?? 0;
  const c = usage.completion_tokens ?? usage.output_tokens ?? 0;
  if (provider === "anthropic") return p * 0.000003 + c * 0.000015;
  if (provider === "qwen") return p * 0.000001 + c * 0.000003;
  const m = model.toLowerCase();
  if (m.includes("gpt-4o")) return p * 0.0000025 + c * 0.00001;
  if (m.includes("gpt-4")) return p * 0.00003 + c * 0.00006;
  return (p + c) * 0.000005;
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}