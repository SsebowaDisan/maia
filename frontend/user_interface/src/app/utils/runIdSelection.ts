import type { AgentActivityEvent } from "../types";

function normalizeRunId(value: unknown): string {
  return String(value || "").trim();
}

function isPlaceholderRunId(runId: string): boolean {
  const normalized = normalizeRunId(runId).toLowerCase();
  return normalized.startsWith("brain_") || normalized.startsWith("assembly_");
}

export function resolvePreferredRunId(
  explicitRunId: unknown,
  events: AgentActivityEvent[],
): string {
  const explicit = normalizeRunId(explicitRunId);
  const eventRunIds: string[] = [];
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const runId = normalizeRunId(events[index]?.run_id);
    if (!runId || eventRunIds.includes(runId)) {
      continue;
    }
    eventRunIds.push(runId);
  }

  if (explicit && !isPlaceholderRunId(explicit)) {
    return explicit;
  }

  const preferredEventRunId = eventRunIds.find((runId) => !isPlaceholderRunId(runId));
  if (preferredEventRunId) {
    return preferredEventRunId;
  }

  return eventRunIds[0] || explicit;
}

