import type { AgentActivityEvent } from "../../types";

function normalizeTokenList(values: string[] | undefined): string[] {
  if (!Array.isArray(values)) {
    return [];
  }
  const cleaned = values
    .map((value) => String(value || "").trim().toLowerCase())
    .filter((value) => value.length > 0);
  return Array.from(new Set(cleaned)).slice(0, 16);
}

function readEventString(event: AgentActivityEvent, key: string): string {
  const direct = String((event as Record<string, unknown>)[key] || "").trim();
  if (direct) {
    return direct;
  }
  const payload = (event.data || event.metadata || {}) as Record<string, unknown>;
  return String(payload[key] || "").trim();
}

function readEventStringList(event: AgentActivityEvent, key: string): string[] {
  const payload = (event.data || event.metadata || {}) as Record<string, unknown>;
  const raw = payload[key];
  if (Array.isArray(raw)) {
    return normalizeTokenList(raw.map((value) => String(value || "")));
  }
  const text = String(raw || "").trim();
  if (!text) {
    return [];
  }
  return normalizeTokenList(text.split(","));
}

export { normalizeTokenList, readEventString, readEventStringList };
