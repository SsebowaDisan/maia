/**
 * Telemetry — auto-instrument LLM calls for OpenTelemetry.
 *
 * Creates spans for every LLM call with attributes:
 * model, provider, tokens, cost, latency, success.
 *
 * Works with any OTel-compatible backend (Datadog, Jaeger, Honeycomb).
 * If no OTel SDK is installed, telemetry is a no-op.
 */

declare const require: (name: string) => any;

export interface LLMSpan {
  traceId: string;
  spanId: string;
  model: string;
  provider: string;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  costUsd: number;
  durationMs: number;
  success: boolean;
  error?: string;
  cached: boolean;
}

export interface TelemetryConfig {
  /** Enable telemetry (default: true). */
  enabled?: boolean;
  /** Service name for traces (default: "maia-brain"). */
  serviceName?: string;
  /** Custom span processor callback. */
  onSpan?: (span: LLMSpan) => void;
}

export interface Telemetry {
  startSpan(model: string, provider: string): SpanHandle;
  getSpans(): LLMSpan[];
  summary(): TelemetrySummary;
}

export interface SpanHandle {
  end(result: {
    inputTokens: number;
    outputTokens: number;
    costUsd: number;
    success: boolean;
    cached?: boolean;
    error?: string;
  }): LLMSpan;
}

export interface TelemetrySummary {
  totalCalls: number;
  successCalls: number;
  failedCalls: number;
  cachedCalls: number;
  totalTokens: number;
  totalCostUsd: number;
  avgLatencyMs: number;
  byModel: Record<string, { calls: number; tokens: number; costUsd: number }>;
  byProvider: Record<string, { calls: number; tokens: number; costUsd: number }>;
}

let _spanCounter = 0;

/**
 * Create a telemetry instance.
 */
export function createTelemetry(config: TelemetryConfig = {}): Telemetry {
  const enabled = config.enabled !== false;
  const spans: LLMSpan[] = [];
  const onSpan = config.onSpan;

  // Try to detect OpenTelemetry SDK
  let otelTracer: any = null;
  try {
    const otelApi = require("@opentelemetry/api");
    otelTracer = otelApi.trace.getTracer(config.serviceName ?? "maia-brain");
  } catch {
    // OTel not installed — use internal tracking only
  }

  function startSpan(model: string, provider: string): SpanHandle {
    const startTime = Date.now();
    const spanId = `span_${(++_spanCounter).toString(36)}`;
    const traceId = `trace_${Date.now().toString(36)}`;

    // Start OTel span if available
    let otelSpan: any = null;
    if (otelTracer) {
      otelSpan = otelTracer.startSpan("llm.call", {
        attributes: {
          "llm.model": model,
          "llm.provider": provider,
          "service.name": config.serviceName ?? "maia-brain",
        },
      });
    }

    return {
      end(result) {
        const duration = Date.now() - startTime;
        const totalTokens = result.inputTokens + result.outputTokens;

        const span: LLMSpan = {
          traceId, spanId, model, provider,
          inputTokens: result.inputTokens,
          outputTokens: result.outputTokens,
          totalTokens, costUsd: result.costUsd,
          durationMs: duration, success: result.success,
          error: result.error, cached: result.cached ?? false,
        };

        if (enabled) spans.push(span);

        // End OTel span
        if (otelSpan) {
          otelSpan.setAttributes({
            "llm.tokens.input": result.inputTokens,
            "llm.tokens.output": result.outputTokens,
            "llm.tokens.total": totalTokens,
            "llm.cost.usd": result.costUsd,
            "llm.cached": result.cached ?? false,
            "llm.success": result.success,
          });
          if (result.error) otelSpan.setAttributes({ "llm.error": result.error });
          otelSpan.end();
        }

        onSpan?.(span);
        return span;
      },
    };
  }

  function getSpans(): LLMSpan[] { return [...spans]; }

  function summary(): TelemetrySummary {
    const byModel: Record<string, { calls: number; tokens: number; costUsd: number }> = {};
    const byProvider: Record<string, { calls: number; tokens: number; costUsd: number }> = {};
    let totalLatency = 0;

    for (const s of spans) {
      totalLatency += s.durationMs;
      const m = byModel[s.model] ?? { calls: 0, tokens: 0, costUsd: 0 };
      m.calls++; m.tokens += s.totalTokens; m.costUsd += s.costUsd;
      byModel[s.model] = m;

      const p = byProvider[s.provider] ?? { calls: 0, tokens: 0, costUsd: 0 };
      p.calls++; p.tokens += s.totalTokens; p.costUsd += s.costUsd;
      byProvider[s.provider] = p;
    }

    return {
      totalCalls: spans.length,
      successCalls: spans.filter((s) => s.success).length,
      failedCalls: spans.filter((s) => !s.success).length,
      cachedCalls: spans.filter((s) => s.cached).length,
      totalTokens: spans.reduce((a, s) => a + s.totalTokens, 0),
      totalCostUsd: Math.round(spans.reduce((a, s) => a + s.costUsd, 0) * 10000) / 10000,
      avgLatencyMs: spans.length > 0 ? Math.round(totalLatency / spans.length) : 0,
      byModel, byProvider,
    };
  }

  return { startSpan, getSpans, summary };
}
