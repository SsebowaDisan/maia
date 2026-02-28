import type { AgentActivityEvent } from "../../types";

function eventMetadataString(event: AgentActivityEvent | null, key: string): string {
  if (!event || !event.metadata) {
    return "";
  }
  const value = event.metadata[key];
  return typeof value === "string" ? value.trim() : "";
}

function findRecentMetadataString(events: AgentActivityEvent[], key: string): string {
  for (let idx = events.length - 1; idx >= 0; idx -= 1) {
    const value = eventMetadataString(events[idx], key);
    if (value) {
      return value;
    }
  }
  return "";
}

export { eventMetadataString, findRecentMetadataString };
