import { getAgentEventSnapshotUrl } from "../../../api/client";
import type { AgentActivityEvent } from "../../types";
import { readStringField, URL_PATTERN } from "./helpers";
import { eventTab } from "./interactionSemantics";

function resolveSceneSnapshotUrl(
  sceneEvent: AgentActivityEvent | null,
  visibleEvents: AgentActivityEvent[],
): string {
  const resolveSnapshot = (event: AgentActivityEvent | null): string => {
    if (!event) return "";
    const raw = readStringField(event.snapshot_ref);
    if (!raw) return "";
    if (raw.startsWith("http://") || raw.startsWith("https://") || raw.startsWith("data:image/")) {
      return raw;
    }
    if (!event.run_id || !event.event_id) {
      return "";
    }
    return getAgentEventSnapshotUrl(event.run_id, event.event_id);
  };

  const preferred = resolveSnapshot(sceneEvent);
  if (preferred) {
    return preferred;
  }
  for (let idx = visibleEvents.length - 1; idx >= 0; idx -= 1) {
    const fallback = resolveSnapshot(visibleEvents[idx]);
    if (fallback) {
      return fallback;
    }
  }
  return "";
}

function resolveBrowserUrl(visibleEvents: AgentActivityEvent[]): string {
  for (let idx = visibleEvents.length - 1; idx >= 0; idx -= 1) {
    const event = visibleEvents[idx];
    const eventType = String(event.event_type || "").toLowerCase();
    const sceneSurface = String(event.metadata?.["scene_surface"] || event.data?.["scene_surface"] || "")
      .trim()
      .toLowerCase();
    const browserLike =
      eventTab(event) === "browser" ||
      sceneSurface === "website" ||
      sceneSurface === "browser" ||
      eventType.startsWith("browser_") ||
      eventType.startsWith("web_");
    if (!browserLike) {
      continue;
    }
    const meta = event.metadata || {};
    const data = event.data || {};
    const fromMeta =
      readStringField(meta["url"]) ||
      readStringField(meta["source_url"]) ||
      readStringField(meta["target_url"]) ||
      readStringField(meta["page_url"]) ||
      readStringField(meta["final_url"]) ||
      readStringField(meta["link"]);
    if (fromMeta.startsWith("http://") || fromMeta.startsWith("https://")) {
      return fromMeta;
    }
    const fromData =
      readStringField(data["url"]) ||
      readStringField(data["source_url"]) ||
      readStringField(data["target_url"]) ||
      readStringField(data["page_url"]) ||
      readStringField(data["final_url"]) ||
      readStringField(data["link"]);
    if (fromData.startsWith("http://") || fromData.startsWith("https://")) {
      return fromData;
    }
    if (eventType.startsWith("browser_") || eventType.startsWith("web_")) {
      const mergedText = `${event.title} ${event.detail}`.trim();
      const match = mergedText.match(URL_PATTERN);
      if (match?.[1]) {
        return match[1];
      }
    }
  }
  return "";
}

function resolveEmailRecipient(visibleEvents: AgentActivityEvent[]): string {
  for (let idx = visibleEvents.length - 1; idx >= 0; idx -= 1) {
    const event = visibleEvents[idx];
    if (event.event_type !== "email_set_to" && event.event_type !== "email_draft_create") {
      continue;
    }
    if (event.detail) {
      return event.detail;
    }
  }
  return "";
}

function resolveEmailSubject(visibleEvents: AgentActivityEvent[]): string {
  for (let idx = visibleEvents.length - 1; idx >= 0; idx -= 1) {
    const event = visibleEvents[idx];
    if (event.event_type !== "email_set_subject") {
      continue;
    }
    if (event.detail) {
      return event.detail;
    }
  }
  return "";
}

function resolveEmailBodyHint(visibleEvents: AgentActivityEvent[]): string {
  for (let idx = visibleEvents.length - 1; idx >= 0; idx -= 1) {
    const event = visibleEvents[idx];
    if (
      event.event_type !== "email_set_body" &&
      event.event_type !== "email_type_body" &&
      event.event_type !== "email_ready_to_send"
    ) {
      continue;
    }
    const dataPreview =
      typeof event.data?.["typed_preview"] === "string"
        ? event.data["typed_preview"]
        : "";
    if (dataPreview) {
      return dataPreview;
    }
    if (event.detail) {
      return event.detail;
    }
  }
  return "";
}

function resolveDocBodyHint(visibleEvents: AgentActivityEvent[]): string {
  let aggregated = "";
  for (let idx = 0; idx < visibleEvents.length; idx += 1) {
    const event = visibleEvents[idx];
    if (event.event_type !== "doc_type_text") {
      continue;
    }
    const dataPreview =
      typeof event.data?.["typed_preview"] === "string"
        ? event.data["typed_preview"]
        : "";
    if (dataPreview) {
      aggregated = dataPreview;
      continue;
    }
    const chunk = String(event.detail || "").trim();
    if (!chunk) {
      continue;
    }
    aggregated += chunk;
    if (aggregated.length > 4000) {
      aggregated = aggregated.slice(-4000);
    }
  }
  return aggregated.trim();
}

function resolveSheetBodyHint(visibleEvents: AgentActivityEvent[]): string {
  const lines: string[] = [];
  for (let idx = visibleEvents.length - 1; idx >= 0; idx -= 1) {
    const event = visibleEvents[idx];
    const type = String(event.event_type || "");
    if (
      !(
        type === "sheet_open" ||
        type === "sheet_cell_update" ||
        type === "sheet_append_row" ||
        type === "sheet_save" ||
        type.startsWith("sheets.")
      )
    ) {
      continue;
    }
    const detail = String(event.detail || "").trim();
    const title = String(event.title || "").trim();
    const line = [title, detail].filter(Boolean).join(": ").trim();
    if (!line) {
      continue;
    }
    lines.unshift(line);
    if (lines.length >= 24) {
      break;
    }
  }
  return lines.join("\n");
}

export {
  resolveBrowserUrl,
  resolveDocBodyHint,
  resolveEmailBodyHint,
  resolveEmailRecipient,
  resolveEmailSubject,
  resolveSceneSnapshotUrl,
  resolveSheetBodyHint,
};
