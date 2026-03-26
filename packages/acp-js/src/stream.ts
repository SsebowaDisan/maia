// ─── ACP Stream Utilities ───────────────────────────────────────────────────
// Parse raw SSE streams into typed ACP events.
// Works with any SSE source — not just ACP-native servers.

import type { ACPEvent } from "./types";

/**
 * Parse a raw SSE line into an ACP event.
 * Returns null if the line is not a valid ACP event.
 * Gracefully handles non-ACP SSE data by wrapping it as an activity event.
 */
export function parseSSELine(line: string): ACPEvent | null {
  const trimmed = line.trim();
  if (!trimmed || !trimmed.startsWith("data: ")) return null;

  const dataStr = trimmed.slice(6);
  if (dataStr === "[DONE]") return null;

  try {
    const parsed = JSON.parse(dataStr);

    // Native ACP event — pass through
    if (parsed.acp_version) {
      return parsed as ACPEvent;
    }

    // Non-ACP event — try to wrap it intelligently
    return wrapNonACPEvent(parsed);
  } catch {
    return null;
  }
}

/**
 * Wrap a non-ACP JSON event into an ACP envelope.
 * This is what makes Theatre work with ANY existing SSE stream.
 */
function wrapNonACPEvent(data: Record<string, unknown>): ACPEvent {
  // Try to detect common patterns from popular frameworks
  const agentId =
    (data.agent_id as string) ??
    (data.agent as string) ??
    (data.sender as string) ??
    (data.name as string) ??
    "agent://unknown";

  const agentUri = agentId.startsWith("agent://")
    ? agentId
    : `agent://${agentId}`;

  // Detect event type from common fields
  let eventType: ACPEvent["event_type"] = "event";
  if (data.content || data.message || data.text) {
    eventType = "message";
  } else if (data.tool_call || data.tool || data.function_call) {
    eventType = "event";
  }

  const content =
    (data.content as string) ??
    (data.message as string) ??
    (data.text as string) ??
    (data.output as string) ??
    JSON.stringify(data);

  return {
    acp_version: "1.0",
    run_id: (data.run_id as string) ?? (data.thread_id as string) ?? "unknown",
    agent_id: agentUri,
    event_type: eventType,
    timestamp: (data.timestamp as string) ?? new Date().toISOString(),
    payload:
      eventType === "message"
        ? {
            from: agentUri,
            to: "agent://user",
            intent: "propose" as const,
            content,
          }
        : {
            agent_id: agentUri,
            activity: "tool_calling" as const,
            detail: content,
          },
  };
}

/**
 * Async generator that reads a ReadableStream (e.g. fetch response body)
 * and yields ACP events.
 */
export async function* streamToACPEvents(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<ACPEvent> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        const event = parseSSELine(line);
        if (event) yield event;
      }
    }

    // Process remaining buffer
    if (buffer.trim()) {
      const event = parseSSELine(buffer);
      if (event) yield event;
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * Connect to an SSE endpoint and yield ACP events.
 * Works with both ACP-native and non-ACP SSE streams.
 */
export async function* connectToSSE(
  url: string,
  options?: RequestInit,
): AsyncGenerator<ACPEvent> {
  const response = await fetch(url, {
    ...options,
    headers: {
      Accept: "text/event-stream",
      ...options?.headers,
    },
  });

  if (!response.ok) {
    throw new Error(`ACP stream connection failed: ${response.status}`);
  }

  if (!response.body) {
    throw new Error("No response body");
  }

  yield* streamToACPEvents(response.body);
}
