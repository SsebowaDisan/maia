import { useMemo } from "react";
import { getRawFileUrl } from "../../../api/client";
import type { AgentActivityEvent, ChatAttachment } from "../../types";
import {
  type PreviewTab,
  eventMetadataString,
  findRecentMetadataString,
  sampleFilmstripEvents,
} from "../agentActivityMeta";
import { EMAIL_SCENE_EVENT_TYPES, readEventIndex } from "./deriveHelpers";
import { mergeLiveSceneData, phaseForEvent, readNumberField, readStringField } from "./helpers";
import { desktopStatusForEventType } from "./labels";
import { derivePlannedRoadmap } from "./roadmapDerivation";
import {
  resolveBrowserUrl,
  resolveDocBodyHint,
  resolveEmailBodyHint,
  resolveEmailRecipient,
  resolveEmailSubject,
  resolveSceneSnapshotUrl,
  resolveSheetBodyHint,
} from "./contentDerivation";
import { deriveSurfaceCommit } from "./surfaceCommitDerivation";
import {
  agentColorFromEvent,
  agentEventTypeFromEvent,
  agentLabelFromEvent,
  cursorFromEvent,
  cursorLabelFromSemantics,
  eventTab,
  interactionActionFromEvent,
  interactionActionPhaseFromEvent,
  interactionActionStatusFromEvent,
  isApiRuntimeEvent,
  roleKeyFromEvent,
  roleLabelFromKey,
  roleNarrativeFromSemantics,
  sceneSurfaceFromEvent,
  surfaceLabelForSceneKey,
  tabForSceneSurface,
} from "./interactionSemantics";

interface UseAgentActivityDerivedParams {
  events: AgentActivityEvent[];
  cursor: number;
  previewTab: PreviewTab;
  stageAttachment?: ChatAttachment;
  snapshotFailedEventId: string;
  streaming: boolean;
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
      const leftEventIndex = readEventIndex(left.event, left.index + 1);
      const rightEventIndex = readEventIndex(right.event, right.index + 1);
      if (leftEventIndex !== rightEventIndex) {
        return leftEventIndex - rightEventIndex;
      }
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
  const activeTab = eventTab(activeEvent);

  const sceneEvent = useMemo(() => {
    if (!activeEvent) {
      return null;
    }
    const activeEventTab = eventTab(activeEvent);
    if (activeEventTab !== "system" || isApiRuntimeEvent(activeEvent)) {
      return activeEvent;
    }
    for (let idx = visibleEvents.length - 1; idx >= 0; idx -= 1) {
      const candidate = visibleEvents[idx];
      if (eventTab(candidate) !== "system" || isApiRuntimeEvent(candidate)) {
        return candidate;
      }
    }
    return activeEvent;
  }, [activeEvent, visibleEvents]);

  const sceneTab = eventTab(sceneEvent || activeEvent);
  const activePhase = useMemo(() => phaseForEvent(activeEvent), [activeEvent?.event_id, activeEvent?.event_type]);
  const progressPercent =
    orderedEvents.length <= 1
      ? 100
      : Math.round((safeCursor / (orderedEvents.length - 1)) * 100);

  const browserEvents = useMemo(
    () => visibleEvents.filter((event) => eventTab(event) === "browser"),
    [visibleEvents],
  );
  const documentEvents = useMemo(
    () => visibleEvents.filter((event) => eventTab(event) === "document"),
    [visibleEvents],
  );
  const emailEvents = useMemo(
    () => visibleEvents.filter((event) => eventTab(event) === "email"),
    [visibleEvents],
  );
  const systemEvents = useMemo(
    () => visibleEvents.filter((event) => eventTab(event) === "system"),
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
  const hasEmailSceneSignal = useMemo(() => {
    for (const event of visibleEvents) {
      const eventType = String(event.event_type || "").toLowerCase();
      if (EMAIL_SCENE_EVENT_TYPES.has(eventType)) {
        return true;
      }
      if (tabForSceneSurface(sceneSurfaceFromEvent(event)) === "email") {
        return true;
      }
    }
    return false;
  }, [visibleEvents]);
  const isEmailScene = previewTab === "email" && hasEmailSceneSignal;
  const isDocumentScene = previewTab === "document";
  const isSystemScene = previewTab === "system";
  const isApiScene = isApiRuntimeEvent(sceneEvent || activeEvent);

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
  const hasDocumentUrlSignal =
    sceneDocumentUrl.length > 0 ||
    currentSceneSourceUrl.includes("docs.google.com/document/");
  const sceneSurface = sceneSurfaceFromEvent(sceneEvent).toLowerCase();
  const sceneShadowFlagRaw = sceneEvent?.data?.["shadow"] ?? sceneEvent?.metadata?.["shadow"];
  const isSceneShadowEvent =
    typeof sceneShadowFlagRaw === "boolean"
      ? sceneShadowFlagRaw
      : ["true", "1", "yes"].includes(String(sceneShadowFlagRaw ?? "").trim().toLowerCase());
  const isSheetsScene =
    isDocumentScene &&
    (sceneEventType.startsWith("sheet_") ||
      sceneEventType.startsWith("sheets.") ||
      sceneEventType === "drive.go_to_sheet" ||
      sceneSurface === "google_sheets" ||
      hasSpreadsheetUrlSignal);

  const mergedPdfPage = readNumberField(mergedSceneData["pdf_page"]);
  const mergedPdfTotal = readNumberField(mergedSceneData["pdf_total_pages"]);
  const hasPdfEventSignal = sceneEventType.startsWith("pdf_");
  const hasPdfDataSignal = mergedPdfPage !== null || mergedPdfTotal !== null;
  const isPdfScene =
    isDocumentScene &&
    canRenderPdfFrame &&
    !isSheetsScene &&
    !hasDocumentUrlSignal &&
    (hasPdfEventSignal || hasPdfDataSignal || !sceneSpreadsheetUrl);

  const docsExplicitlyRequested = useMemo(() => {
    for (let idx = visibleEvents.length - 1; idx >= 0; idx -= 1) {
      const event = visibleEvents[idx];
      const eventType = String(event.event_type || "").toLowerCase();
      if (eventType === "llm.task_contract_completed") {
        const requiredActions = Array.isArray(event.metadata?.["required_actions"])
          ? event.metadata["required_actions"]
          : Array.isArray(event.data?.["required_actions"])
            ? event.data["required_actions"]
            : [];
        if (
          requiredActions.some(
            (item) => String(item || "").trim().toLowerCase() === "create_document",
          )
        ) {
          return true;
        }
      }
      if (eventType === "llm.intent_tags") {
        const tags = Array.isArray(event.metadata?.["intent_tags"])
          ? event.metadata["intent_tags"]
          : Array.isArray(event.data?.["intent_tags"])
            ? event.data["intent_tags"]
            : [];
        if (tags.some((item) => String(item || "").trim().toLowerCase() === "docs_write")) return true;
      }
    }
    return false;
  }, [visibleEvents]);

  // Docs scene is gated to explicit docs interactions only.
  const hasDocsEventSignal =
    !isSceneShadowEvent &&
    (sceneEventType.startsWith("doc_") ||
      sceneEventType.startsWith("docs.") ||
      sceneEventType === "drive.go_to_doc") &&
    (sceneSurface === "google_docs" || sceneSurface === "docs" || hasDocumentUrlSignal);
  const isDocsScene =
    isDocumentScene && !isSheetsScene && !isPdfScene && hasDocsEventSignal && docsExplicitlyRequested;

  const sceneSurfaceKey = isBrowserScene
    ? "website"
    : isSheetsScene
      ? "google_sheets"
      : isPdfScene
        ? "document"
      : isDocsScene
        ? "google_docs"
        : isEmailScene
          ? "email"
          : isApiScene
            ? "api"
          : isSystemScene
            ? "system"
            : "workspace";
  const sceneSurfaceLabel = surfaceLabelForSceneKey(sceneSurfaceKey);

  const snapshotUrl = useMemo(
    () => resolveSceneSnapshotUrl(sceneEvent, visibleEvents),
    [sceneEvent, visibleEvents],
  );
  const effectiveSnapshotUrl =
    sceneEvent && snapshotFailedEventId === sceneEvent.event_id ? "" : snapshotUrl;

  const browserUrl = useMemo(
    () => resolveBrowserUrl(visibleEvents),
    [visibleEvents],
  );
  const surfaceCommit = useMemo(() => deriveSurfaceCommit(visibleEvents), [visibleEvents]);
  const emailRecipient = useMemo(
    () => resolveEmailRecipient(visibleEvents),
    [visibleEvents],
  );
  const emailSubject = useMemo(
    () => resolveEmailSubject(visibleEvents),
    [visibleEvents],
  );
  const emailBodyHint = useMemo(
    () => resolveEmailBodyHint(visibleEvents),
    [visibleEvents],
  );
  const docBodyHint = useMemo(
    () => resolveDocBodyHint(visibleEvents),
    [visibleEvents],
  );
  const sheetBodyHint = useMemo(
    () => resolveSheetBodyHint(visibleEvents),
    [visibleEvents],
  );

  const desktopStatus = useMemo(
    () => desktopStatusForEventType(activeEvent?.event_type || "", streaming),
    [activeEvent?.event_type, streaming],
  );

  const activeRoleKey = useMemo(
    () =>
      roleKeyFromEvent(sceneEvent) ||
      roleKeyFromEvent(activeEvent) ||
      roleKeyFromEvent(visibleEvents[visibleEvents.length - 1] || null),
    [activeEvent, sceneEvent, visibleEvents],
  );
  const activeRoleLabel =
    agentLabelFromEvent(sceneEvent) ||
    agentLabelFromEvent(activeEvent) ||
    roleLabelFromKey(activeRoleKey) ||
    "Agent";
  const activeRoleColor =
    agentColorFromEvent(sceneEvent) ||
    agentColorFromEvent(activeEvent) ||
    "#6b7280";
  const agentEventType =
    agentEventTypeFromEvent(sceneEvent) ||
    agentEventTypeFromEvent(activeEvent) ||
    "";

  const interactionAction =
    interactionActionFromEvent(sceneEvent) || interactionActionFromEvent(activeEvent);
  const interactionActionPhase =
    interactionActionPhaseFromEvent(sceneEvent) || interactionActionPhaseFromEvent(activeEvent);
  const interactionActionStatus =
    interactionActionStatusFromEvent(sceneEvent) || interactionActionStatusFromEvent(activeEvent);

  const cursorLabel = useMemo(
    () =>
      cursorLabelFromSemantics({
        action: interactionAction,
        actionStatus: interactionActionStatus,
        actionPhase: interactionActionPhase,
        sceneSurfaceLabel,
        roleLabel: activeRoleLabel,
        agentEventType,
      }),
    [
      activeRoleLabel,
      agentEventType,
      interactionAction,
      interactionActionPhase,
      interactionActionStatus,
      sceneSurfaceLabel,
    ],
  );

  const roleNarrative = useMemo(
    () =>
      roleNarrativeFromSemantics({
        roleLabel: activeRoleLabel,
        action: interactionAction,
        sceneSurfaceLabel,
        fallback: sceneEvent?.title || activeEvent?.title || "working",
        agentEventType,
      }),
    [
      activeRoleLabel,
      activeEvent?.title,
      agentEventType,
      interactionAction,
      sceneEvent?.title,
      sceneSurfaceLabel,
    ],
  );

  const eventCursor = useMemo(() => {
    const activeCursor = cursorFromEvent(activeEvent);
    if (activeCursor) {
      return activeCursor;
    }
    return cursorFromEvent(sceneEvent);
  }, [activeEvent, sceneEvent]);
  const { plannedRoadmapSteps, roadmapActiveIndex } = useMemo(
    () => derivePlannedRoadmap(visibleEvents),
    [visibleEvents],
  );

  return {
    activeEvent,
    activeRoleKey,
    activeRoleLabel,
    activeRoleColor,
    activePhase,
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
    interactionAction,
    interactionActionPhase,
    interactionActionStatus,
    isBrowserScene,
    isDocsScene,
    isDocumentScene,
    isEmailScene,
    isApiScene,
    isPdfScene,
    isSheetsScene,
    isSystemScene,
    mergedSceneData,
    orderedEvents,
    progressPercent,
    roleNarrative,
    safeCursor,
    sceneDocumentUrl,
    sceneEvent,
    sceneSpreadsheetUrl,
    sceneSurfaceKey,
    sceneSurfaceLabel,
    sceneTab,
    surfaceCommit,
    sheetBodyHint,
    stageFileName,
    stageFileUrl,
    systemEvents,
    visibleEvents,
    plannedRoadmapSteps,
    roadmapActiveIndex,
  };
}

export { useAgentActivityDerived };
