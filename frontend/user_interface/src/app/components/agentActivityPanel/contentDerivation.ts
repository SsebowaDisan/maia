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
  const isGoogleWorkspaceUrl = (value: string): boolean => {
    const normalized = String(value || "").trim().toLowerCase();
    if (!normalized) {
      return false;
    }
    return (
      normalized.includes("docs.google.com/document/") ||
      normalized.includes("docs.google.com/spreadsheets/")
    );
  };

  const isHttpUrl = (value: string): boolean =>
    value.startsWith("http://") || value.startsWith("https://");

  const firstHttpUrl = (...candidates: unknown[]): string => {
    for (const candidate of candidates) {
      const value = readStringField(candidate);
      if (isHttpUrl(value)) {
        return value;
      }
    }
    return "";
  };
  const fromTargetObject = (value: unknown): string => {
    if (!value || typeof value !== "object") {
      return "";
    }
    const row = value as Record<string, unknown>;
    return firstHttpUrl(
      row["url"],
      row["source_url"],
      row["target_url"],
      row["page_url"],
      row["final_url"],
      row["link"],
    );
  };
  const fromRows = (value: unknown): string => {
    if (!Array.isArray(value)) {
      return "";
    }
    for (let rowIdx = value.length - 1; rowIdx >= 0; rowIdx -= 1) {
      const row = value[rowIdx];
      const extracted = fromTargetObject(row);
      if (extracted) {
        return extracted;
      }
      const direct = readStringField(row);
      if (direct.startsWith("http://") || direct.startsWith("https://")) {
        return direct;
      }
    }
    return "";
  };
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
      firstHttpUrl(
        meta["url"],
        meta["source_url"],
        meta["target_url"],
        meta["page_url"],
        meta["final_url"],
        meta["link"],
      ) ||
      fromTargetObject(meta["action_target"]) ||
      fromRows(meta["opened_pages"]) ||
      fromRows(meta["top_urls"]);
    if (fromMeta) {
      return fromMeta;
    }
    const fromData =
      firstHttpUrl(
        data["url"],
        data["source_url"],
        data["target_url"],
        data["page_url"],
        data["final_url"],
        data["link"],
      ) ||
      fromTargetObject(data["action_target"]) ||
      fromRows(data["opened_pages"]) ||
      fromRows(data["top_urls"]);
    if (fromData) {
      return fromData;
    }
    const mergedText = `${event.title} ${event.detail}`.trim();
    const match = mergedText.match(URL_PATTERN);
    if (match?.[1]) {
      return match[1];
    }
  }

  const readEventUrl = (event: AgentActivityEvent): string => {
    const meta = event.metadata || {};
    const data = event.data || {};
    const direct =
      firstHttpUrl(
        meta["url"],
        meta["source_url"],
        meta["target_url"],
        meta["page_url"],
        meta["final_url"],
        meta["link"],
        data["url"],
        data["source_url"],
        data["target_url"],
        data["page_url"],
        data["final_url"],
        data["link"],
      ) ||
      fromTargetObject(meta["action_target"]) ||
      fromTargetObject(data["action_target"]) ||
      fromRows(meta["opened_pages"]) ||
      fromRows(data["opened_pages"]) ||
      fromRows(meta["top_urls"]) ||
      fromRows(data["top_urls"]);
    if (direct) {
      return direct;
    }
    const mergedText = `${event.title} ${event.detail}`.trim();
    const match = mergedText.match(URL_PATTERN);
    return String(match?.[1] || "");
  };

  // Fallback: if scene tagging is missing, recover a website URL from any event.
  for (let idx = visibleEvents.length - 1; idx >= 0; idx -= 1) {
    const candidate = readEventUrl(visibleEvents[idx]);
    if (candidate && isHttpUrl(candidate) && !isGoogleWorkspaceUrl(candidate)) {
      return candidate;
    }
  }

  // Last-resort fallback: return any HTTP URL to avoid an empty browser frame.
  for (let idx = visibleEvents.length - 1; idx >= 0; idx -= 1) {
    const candidate = readEventUrl(visibleEvents[idx]);
    if (candidate && isHttpUrl(candidate)) {
      return candidate;
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
  let streamed = "";
  let fallback = "";
  for (let idx = 0; idx < visibleEvents.length; idx += 1) {
    const event = visibleEvents[idx];
    const type = String(event.event_type || "");
    if (type !== "email_set_body" && type !== "email_type_body" && type !== "email_ready_to_send") {
      continue;
    }
    const dataPreview =
      typeof event.data?.["typed_preview"] === "string"
        ? event.data["typed_preview"]
        : "";
    const chunkIndex = Number(event.data?.["chunk_index"]);
    const chunkTotal = Number(event.data?.["chunk_total"]);
    const detail = String(event.detail || "");

    if (type === "email_type_body") {
      const chunk = dataPreview || detail;
      if (!chunk) {
        continue;
      }
      const hasChunkMeta =
        Number.isFinite(chunkIndex) &&
        chunkIndex > 0 &&
        Number.isFinite(chunkTotal) &&
        chunkTotal > 0;
      if (hasChunkMeta && chunkIndex === 1 && chunk.length < streamed.length) {
        streamed = "";
      }
      if (chunk.startsWith(streamed)) {
        streamed = chunk;
      } else if (!streamed.endsWith(chunk)) {
        streamed += chunk;
      }
      continue;
    }

    if (dataPreview) {
      streamed = dataPreview.length >= streamed.length ? dataPreview : streamed;
      fallback = dataPreview;
      continue;
    }
    if (detail) {
      fallback = detail;
    }
  }
  return streamed || fallback;
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
