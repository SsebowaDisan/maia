import type { AgentActivityEvent } from "../../types";
import type { PreviewTab } from "../agentActivityMeta";
import { eventTab, isApiRuntimeEvent, sceneSurfaceFromEvent } from "./interactionSemantics";

type SurfaceCommit = {
  tab: PreviewTab;
  surface: string;
  subtype: string;
  sourceUrl: string;
  committedEventId: string;
  committedAt: string;
  confidence: "high" | "medium";
};

function readString(value: unknown): string {
  return String(value || "").trim();
}

function firstHttpUrl(...candidates: unknown[]): string {
  for (const candidate of candidates) {
    const value = readString(candidate);
    if (value.startsWith("http://") || value.startsWith("https://")) {
      return value;
    }
  }
  return "";
}

function fromTargetObject(value: unknown): string {
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
}

function fromRows(value: unknown): string {
  if (!Array.isArray(value)) {
    return "";
  }
  for (let idx = value.length - 1; idx >= 0; idx -= 1) {
    const row = value[idx];
    const nested = fromTargetObject(row);
    if (nested) {
      return nested;
    }
    const direct = firstHttpUrl(row);
    if (direct) {
      return direct;
    }
  }
  return "";
}

function extractUrlFromEvent(event: AgentActivityEvent): string {
  const metadata = event.metadata || {};
  const data = event.data || {};
  return (
    firstHttpUrl(
      metadata["url"],
      metadata["source_url"],
      metadata["target_url"],
      metadata["page_url"],
      metadata["final_url"],
      metadata["link"],
      data["url"],
      data["source_url"],
      data["target_url"],
      data["page_url"],
      data["final_url"],
      data["link"],
      data["document_url"],
      metadata["document_url"],
      data["spreadsheet_url"],
      metadata["spreadsheet_url"],
    ) ||
    fromTargetObject(metadata["action_target"]) ||
    fromTargetObject(data["action_target"]) ||
    fromRows(metadata["opened_pages"]) ||
    fromRows(data["opened_pages"]) ||
    fromRows(metadata["top_urls"]) ||
    fromRows(data["top_urls"])
  );
}

function inferSubtypeFromUrl(url: string): string {
  const normalized = readString(url).toLowerCase();
  if (!normalized) {
    return "";
  }
  if (normalized.includes("docs.google.com/spreadsheets/")) {
    return "google_sheets";
  }
  if (normalized.includes("docs.google.com/document/")) {
    return "google_docs";
  }
  if (normalized.includes(".pdf") || normalized.includes("application/pdf") || normalized.includes("/pdf?")) {
    return "pdf";
  }
  return "";
}

function deriveSurfaceCommit(visibleEvents: AgentActivityEvent[]): SurfaceCommit | null {
  for (let idx = visibleEvents.length - 1; idx >= 0; idx -= 1) {
    const event = visibleEvents[idx];
    const normalizedType = readString(event.event_type).toLowerCase();
    const sceneSurface = readString(sceneSurfaceFromEvent(event)).toLowerCase();

    // Metadata-first: use scene_family from event data if available
    const sceneFamily = readString(event.data?.["scene_family"] ?? event.metadata?.["scene_family"]).toLowerCase();
    if (sceneFamily) {
      const sfMap: Record<string, { tab: string; surface: string }> = {
        email: { tab: "email", surface: "email" },
        sheet: { tab: "document", surface: "sheet" },
        document: { tab: "document", surface: "document" },
        browser: { tab: "browser", surface: "website" },
        api: { tab: "system", surface: "api" },
        chat: { tab: "system", surface: "api" },
      };
      const mapped = sfMap[sceneFamily];
      if (mapped) {
        const sourceUrl = extractUrlFromEvent(event);
        return {
          tab: mapped.tab,
          surface: mapped.surface,
          subtype: readString(event.data?.["brand_slug"]) || sceneFamily,
          sourceUrl,
          committedEventId: readString(event.event_id),
          committedAt: readString(event.timestamp || event.ts),
          confidence: "high",
        };
      }
    }

    const uiTarget = readString(event.data?.["ui_target"] ?? event.metadata?.["ui_target"]).toLowerCase();
    const uiCommitCandidate =
      (event.data?.["ui_commit"] as Record<string, unknown> | undefined) ||
      (event.metadata?.["ui_commit"] as Record<string, unknown> | undefined) ||
      {};
    const uiCommitSurface = readString(uiCommitCandidate["surface"]).toLowerCase();
    const uiCommitUrl = firstHttpUrl(uiCommitCandidate["url"], uiCommitCandidate["source_url"]);
    const tab = eventTab(event);
    const sourceUrl = extractUrlFromEvent(event);
    if (uiTarget || uiCommitSurface) {
      const resolvedTab =
        uiTarget === "browser" || uiCommitSurface === "browser"
          ? "browser"
          : uiTarget === "document" || uiCommitSurface === "document"
            ? "document"
            : uiTarget === "email" || uiCommitSurface === "email"
              ? "email"
              : "system";
      const resolvedSurface =
        uiCommitSurface || (resolvedTab === "browser" ? "website" : resolvedTab);
      if (resolvedTab !== "system" || resolvedSurface === "api") {
        return {
          tab: resolvedTab,
          surface: resolvedSurface,
          subtype: inferSubtypeFromUrl(uiCommitUrl || sourceUrl) || resolvedSurface,
          sourceUrl: uiCommitUrl || sourceUrl,
          committedEventId: readString(event.event_id),
          committedAt: readString(event.timestamp || event.ts),
          confidence: uiCommitUrl || sourceUrl ? "high" : "medium",
        };
      }
      if (resolvedSurface === "api") {
        return {
          tab: "system",
          surface: "api",
          subtype: "api",
          sourceUrl: uiCommitUrl || sourceUrl,
          committedEventId: readString(event.event_id),
          committedAt: readString(event.timestamp || event.ts),
          confidence: "high",
        };
      }
    }

    if (
      tab === "browser" ||
      sceneSurface === "website" ||
      sceneSurface === "browser" ||
      sceneSurface === "web"
    ) {
      return {
        tab: "browser",
        surface: "website",
        subtype: inferSubtypeFromUrl(sourceUrl) || "website",
        sourceUrl,
        committedEventId: readString(event.event_id),
        committedAt: readString(event.timestamp || event.ts),
        confidence: sourceUrl ? "high" : "medium",
      };
    }

    if (tab === "document" || sceneSurface === "google_docs" || sceneSurface === "google_sheets") {
      return {
        tab: "document",
        surface: "document",
        subtype: sceneSurface || inferSubtypeFromUrl(sourceUrl) || "document",
        sourceUrl,
        committedEventId: readString(event.event_id),
        committedAt: readString(event.timestamp || event.ts),
        confidence: sourceUrl ? "high" : "medium",
      };
    }

    if (
      tab === "email" ||
      sceneSurface === "email" ||
      sceneSurface === "gmail" ||
      normalizedType.startsWith("email_") ||
      normalizedType.startsWith("email.") ||
      normalizedType.startsWith("gmail_") ||
      normalizedType.startsWith("gmail.")
    ) {
      return {
        tab: "email",
        surface: "email",
        subtype: sceneSurface || "email",
        sourceUrl,
        committedEventId: readString(event.event_id),
        committedAt: readString(event.timestamp || event.ts),
        confidence: "high",
      };
    }

    if (isApiRuntimeEvent(event)) {
      return {
        tab: "system",
        surface: "api",
        subtype: "api",
        sourceUrl,
        committedEventId: readString(event.event_id),
        committedAt: readString(event.timestamp || event.ts),
        confidence: "high",
      };
    }
  }
  return null;
}

export { deriveSurfaceCommit };
export type { SurfaceCommit };
