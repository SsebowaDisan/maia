import type { AgentActivityEvent } from "../../types";

function compactNarrative(value: string, maxLength = 140): string {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) {
    return "";
  }
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength - 1).trimEnd()}...`;
}

function buildSceneNarrative(event: AgentActivityEvent | null): string {
  if (!event) {
    return "";
  }
  const title = compactNarrative(event.title || "", 80);
  const detail = compactNarrative(event.detail || "", 120);
  if (detail && detail.length <= 90 && title && detail.toLowerCase() !== title.toLowerCase()) {
    return `${title} - ${detail}`;
  }
  return detail || title || "Processing step...";
}

export { buildSceneNarrative };

