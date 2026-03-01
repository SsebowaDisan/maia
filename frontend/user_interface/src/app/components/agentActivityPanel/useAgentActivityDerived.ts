import { useMemo } from "react";
import { getAgentEventSnapshotUrl, getRawFileUrl } from "../../../api/client";
import type { AgentActivityEvent, ChatAttachment } from "../../types";
import {
  type PreviewTab,
  eventMetadataString,
  findRecentMetadataString,
  sampleFilmstripEvents,
  tabForEventType,
} from "../agentActivityMeta";
import {
  mergeLiveSceneData,
  readNumberField,
  readStringField,
  URL_PATTERN,
} from "./helpers";
import { cursorLabelForEventType, desktopStatusForEventType } from "./labels";

interface UseAgentActivityDerivedParams {
  events: AgentActivityEvent[];
  cursor: number;
  previewTab: PreviewTab;
  stageAttachment?: ChatAttachment;
  snapshotFailedEventId: string;
  streaming: boolean;
}

const EMAIL_TOOL_IDS = new Set([
  "mailer.report_send",
  "email.draft",
  "email.send",
  "gmail.draft",
  "gmail.send",
]);

function tabForSceneSurface(surface: string): PreviewTab | null {
  const normalized = String(surface || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "_");
  if (!normalized) {
    return null;
  }
  if (
    normalized === "browser" ||
    normalized === "website" ||
    normalized === "web" ||
    normalized === "maps"
  ) {
    return "browser";
  }
  if (
    normalized === "document" ||
    normalized === "google_docs" ||
    normalized === "google_sheets" ||
    normalized === "docs" ||
    normalized === "sheets"
  ) {
    return "document";
  }
  if (normalized === "email" || normalized === "gmail") {
    return "email";
  }
  if (normalized === "system" || normalized === "workspace") {
    return "system";
  }
  return null;
}

function tabForEvent(event: AgentActivityEvent | null): PreviewTab {
  if (!event) {
    return "system";
  }
  const sceneSurface =
    eventMetadataString(event, "scene_surface") ||
    readStringField(event.data?.["scene_surface"]);
  const surfaceTab = tabForSceneSurface(sceneSurface);
  if (surfaceTab) {
    return surfaceTab;
  }
  const byType = tabForEventType(event.event_type || "");
  if (byType !== "system") {
    return byType;
  }
  const toolId =
    eventMetadataString(event, "tool_id") || readStringField(event.data?.["tool_id"]);
  if (!toolId) {
    return byType;
  }
  if (EMAIL_TOOL_IDS.has(toolId)) {
    return "email";
  }
  if (
    toolId.startsWith("workspace.docs.") ||
    toolId.startsWith("workspace.sheets.") ||
    toolId === "docs.create"
  ) {
    return "document";
  }
  if (
    toolId.startsWith("browser.") ||
    toolId.startsWith("marketing.web_research") ||
    toolId.startsWith("documents.highlight.")
  ) {
    return "browser";
  }
  return byType;
}

function useAgentActivityDerived({
  events,
  cursor,
  previewTab,
  stageAttachment,
  snapshotFailedEventId,
  streaming,
}: UseAgentActivityDerivedParams) {
  const orderedEvents = useMemo(() => {
    const decorated = events.map((event, index) => ({ event, index }));
    decorated.sort((left, right) => {
      const leftSeq =
        typeof left.event.seq === "number" && Number.isFinite(left.event.seq)
          ? left.event.seq
          : Number.NaN;
      const rightSeq =
        typeof right.event.seq === "number" && Number.isFinite(right.event.seq)
          ? right.event.seq
          : Number.NaN;
      if (Number.isFinite(leftSeq) && Number.isFinite(rightSeq) && leftSeq !== rightSeq) {
        return leftSeq - rightSeq;
      }
      const leftTs = Date.parse(left.event.timestamp || left.event.ts || "");
      const rightTs = Date.parse(right.event.timestamp || right.event.ts || "");
      if (Number.isFinite(leftTs) && Number.isFinite(rightTs) && leftTs !== rightTs) {
        return leftTs - rightTs;
      }
      return left.index - right.index;
    });
    return decorated.map((item) => item.event);
  }, [events]);

  const safeCursor = Math.min(Math.max(0, cursor), Math.max(orderedEvents.length - 1, 0));
  const visibleEvents = useMemo(
    () => orderedEvents.slice(0, safeCursor + 1),
    [orderedEvents, safeCursor],
  );
  const filmstripEvents = useMemo(
    () => sampleFilmstripEvents(orderedEvents, safeCursor),
    [orderedEvents, safeCursor],
  );
  const activeEvent = orderedEvents[safeCursor] || null;
  const activeTab = tabForEvent(activeEvent);

  const sceneEvent = useMemo(() => {
    if (!activeEvent) {
      return null;
    }
    const activeEventTab = tabForEvent(activeEvent);
    if (activeEventTab !== "system") {
      return activeEvent;
    }
    for (let idx = visibleEvents.length - 1; idx >= 0; idx -= 1) {
      const candidate = visibleEvents[idx];
      if (tabForEvent(candidate) !== "system") {
        return candidate;
      }
    }
    return activeEvent;
  }, [activeEvent, visibleEvents]);

  const sceneTab = tabForEvent(sceneEvent || activeEvent);
  const progressPercent =
    orderedEvents.length <= 1
      ? 100
      : Math.round((safeCursor / (orderedEvents.length - 1)) * 100);

  const browserEvents = useMemo(
    () => visibleEvents.filter((event) => tabForEvent(event) === "browser"),
    [visibleEvents],
  );
  const documentEvents = useMemo(
    () => visibleEvents.filter((event) => tabForEvent(event) === "document"),
    [visibleEvents],
  );
  const emailEvents = useMemo(
    () => visibleEvents.filter((event) => tabForEvent(event) === "email"),
    [visibleEvents],
  );
  const systemEvents = useMemo(
    () => visibleEvents.filter((event) => tabForEvent(event) === "system"),
    [visibleEvents],
  );

  const derivedFileId =
    stageAttachment?.fileId ||
    eventMetadataString(sceneEvent, "file_id") ||
    findRecentMetadataString(orderedEvents, "file_id");
  const derivedFileName =
    stageAttachment?.name ||
    eventMetadataString(sceneEvent, "file_name") ||
    eventMetadataString(sceneEvent, "document_name") ||
    findRecentMetadataString(orderedEvents, "file_name") ||
    findRecentMetadataString(orderedEvents, "document_name") ||
    "";

  const stageFileName = derivedFileName || "Working document";
  const isPdfStage = /\.pdf$/i.test(stageFileName);
  const stageFileUrl = derivedFileId ? getRawFileUrl(derivedFileId) : "";
  const canRenderPdfFrame = Boolean(isPdfStage && stageFileUrl);

  const mergedSceneData = useMemo(
    () => mergeLiveSceneData(visibleEvents, activeEvent),
    [visibleEvents, activeEvent?.event_id],
  );

  const sceneEventType = String(sceneEvent?.event_type || activeEvent?.event_type || "").toLowerCase();
  const isBrowserScene = previewTab === "browser";
  const isEmailScene = previewTab === "email";
  const isDocumentScene = previewTab === "document";
  const isSystemScene = previewTab === "system";
  const currentSceneSourceUrl =
    readStringField(sceneEvent?.data?.["source_url"]) ||
    readStringField(sceneEvent?.metadata?.["source_url"]) ||
    readStringField(sceneEvent?.data?.["url"]) ||
    readStringField(sceneEvent?.metadata?.["url"]);
  const sceneDocumentUrl =
    readStringField(sceneEvent?.data?.["document_url"]) ||
    readStringField(sceneEvent?.metadata?.["document_url"]) ||
    (currentSceneSourceUrl.includes("docs.google.com/document/") ? currentSceneSourceUrl : "");
  const sceneSpreadsheetUrl =
    readStringField(sceneEvent?.data?.["spreadsheet_url"]) ||
    readStringField(sceneEvent?.metadata?.["spreadsheet_url"]) ||
    (currentSceneSourceUrl.includes("docs.google.com/spreadsheets/") ? currentSceneSourceUrl : "");
  const hasSpreadsheetUrlSignal =
    sceneSpreadsheetUrl.length > 0 ||
    currentSceneSourceUrl.includes("docs.google.com/spreadsheets/");
  const isSheetsScene =
    isDocumentScene &&
    (sceneEventType.startsWith("sheet_") ||
      sceneEventType.startsWith("sheets.") ||
      sceneEventType === "drive.go_to_sheet" ||
      hasSpreadsheetUrlSignal);
  const isDocsScene = isDocumentScene && !isSheetsScene;
  const sceneSurfaceKey = isBrowserScene
    ? "website"
    : isSheetsScene
      ? "google_sheets"
      : isDocsScene
        ? "google_docs"
        : isEmailScene
          ? "email"
          : isSystemScene
            ? "system"
            : "workspace";
  const sceneSurfaceLabel = sceneSurfaceKey === "website"
    ? "Website"
    : sceneSurfaceKey === "google_sheets"
      ? "Google Sheets"
      : sceneSurfaceKey === "google_docs"
        ? "Google Docs"
        : sceneSurfaceKey === "email"
          ? "Email"
          : sceneSurfaceKey === "system"
            ? "System"
            : "Workspace";

  const snapshotUrl = useMemo(() => {
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
  }, [sceneEvent, visibleEvents]);

  const effectiveSnapshotUrl =
    sceneEvent && snapshotFailedEventId === sceneEvent.event_id ? "" : snapshotUrl;

  const browserUrl = useMemo(() => {
    for (let idx = visibleEvents.length - 1; idx >= 0; idx -= 1) {
      const event = visibleEvents[idx];
      const meta = event.metadata || {};
      const data = event.data || {};
      const fromMeta =
        readStringField(meta["url"]) ||
        readStringField(meta["target_url"]) ||
        readStringField(meta["page_url"]) ||
        readStringField(meta["final_url"]) ||
        readStringField(meta["link"]);
      if (fromMeta.startsWith("http://") || fromMeta.startsWith("https://")) {
        return fromMeta;
      }
      const fromData =
        readStringField(data["url"]) ||
        readStringField(data["target_url"]) ||
        readStringField(data["page_url"]) ||
        readStringField(data["final_url"]) ||
        readStringField(data["link"]);
      if (fromData.startsWith("http://") || fromData.startsWith("https://")) {
        return fromData;
      }
      const mergedText = `${event.title} ${event.detail}`.trim();
      const match = mergedText.match(URL_PATTERN);
      if (match?.[1]) {
        return match[1];
      }
    }
    return "";
  }, [visibleEvents]);

  const emailRecipient = useMemo(() => {
    for (let idx = visibleEvents.length - 1; idx >= 0; idx -= 1) {
      const event = visibleEvents[idx];
      if (event.event_type !== "email_set_to" && event.event_type !== "email_draft_create") {
        continue;
      }
      if (event.detail) {
        return event.detail;
      }
    }
    return "recipient@company.com";
  }, [visibleEvents]);

  const emailSubject = useMemo(() => {
    for (let idx = visibleEvents.length - 1; idx >= 0; idx -= 1) {
      const event = visibleEvents[idx];
      if (event.event_type !== "email_set_subject") {
        continue;
      }
      if (event.detail) {
        return event.detail;
      }
    }
    return "Company update";
  }, [visibleEvents]);

  const emailBodyHint = useMemo(() => {
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
    return "Composing message body...";
  }, [visibleEvents]);

  const docBodyHint = useMemo(() => {
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
  }, [visibleEvents]);

  const sheetBodyHint = useMemo(() => {
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
  }, [visibleEvents]);

  const desktopStatus = useMemo(
    () => desktopStatusForEventType(activeEvent?.event_type || "", streaming),
    [activeEvent?.event_type, streaming],
  );
  const cursorLabel = useMemo(
    () => cursorLabelForEventType(activeEvent?.event_type || ""),
    [activeEvent?.event_type],
  );

  const eventCursor = useMemo(() => {
    if (!activeEvent) {
      return null;
    }
    const dataX = readNumberField(activeEvent.data?.["cursor_x"]);
    const dataY = readNumberField(activeEvent.data?.["cursor_y"]);
    const metaX = readNumberField(activeEvent.metadata?.["cursor_x"]);
    const metaY = readNumberField(activeEvent.metadata?.["cursor_y"]);
    const x = dataX ?? metaX;
    const y = dataY ?? metaY;
    if (x === null || y === null) {
      return null;
    }
    return {
      x: Math.max(2, Math.min(98, x)),
      y: Math.max(2, Math.min(98, y)),
    };
  }, [activeEvent]);

  return {
    activeEvent,
    activeTab,
    browserEvents,
    browserUrl,
    canRenderPdfFrame,
    cursorLabel,
    desktopStatus,
    docBodyHint,
    documentEvents,
    effectiveSnapshotUrl,
    emailBodyHint,
    emailEvents,
    emailRecipient,
    emailSubject,
    eventCursor,
    filmstripEvents,
    isBrowserScene,
    isDocsScene,
    isDocumentScene,
    isEmailScene,
    isSheetsScene,
    isSystemScene,
    mergedSceneData,
    orderedEvents,
    progressPercent,
    safeCursor,
    sceneDocumentUrl,
    sceneEvent,
    sceneSpreadsheetUrl,
    sceneSurfaceKey,
    sceneSurfaceLabel,
    sceneTab,
    sheetBodyHint,
    stageFileName,
    stageFileUrl,
    systemEvents,
    visibleEvents,
  };
}

export { useAgentActivityDerived };
