import { useEffect, useMemo, useRef, useState } from "react";
import { exportAgentRunEvents } from "../../../api/client";
import type { AgentActivityEvent } from "../../types";
import { derivePhaseTimeline, resolveEventSourceUrl } from "./helpers";
import { DesktopViewer } from "./DesktopViewer";
import type { AgentActivityPanelProps } from "./types";
import { useAgentActivityDerived } from "./useAgentActivityDerived";
import { ActivityHeader } from "./ActivityHeader";
import { ActivityPanelBody } from "./ActivityPanelBody";
import { CinemaOverlay } from "./CinemaOverlay";
import { useAutoScrollTimeline, useJumpTargetSelection, useOverlayKeyboardShortcuts } from "./useActivityPanelNavigation";

const playbackRates = [0.75, 1, 1.5, 2] as const;

function compactNarrative(value: string, maxLength = 140): string {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) {
    return "";
  }
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength - 1).trimEnd()}…`;
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

export function AgentActivityPanel({
  events,
  streaming,
  stageAttachment,
  needsHumanReview,
  humanReviewNotes,
  jumpTarget = null,
  onJumpToEvent,
}: AgentActivityPanelProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState<(typeof playbackRates)[number]>(1);
  const [cursor, setCursor] = useState(0);
  const [sceneText, setSceneText] = useState("");
  const [cursorPoint, setCursorPoint] = useState({ x: 14, y: 24 });
  const [previewTab, setPreviewTab] = useState<"browser" | "document" | "email" | "system">("browser");
  const [isExporting, setIsExporting] = useState(false);
  const [isTheaterView, setIsTheaterView] = useState(true);
  const [isFullscreenViewer, setIsFullscreenViewer] = useState(false);
  const [isCinemaMode, setIsCinemaMode] = useState(false);
  const [approvalDismissed, setApprovalDismissed] = useState<string>("");
  const [isFocusMode, setIsFocusMode] = useState(true);
  const [snapshotFailedEventId, setSnapshotFailedEventId] = useState("");
  const [sceneTransitionLabel, setSceneTransitionLabel] = useState("");

  const timerRef = useRef<number | null>(null);
  const typeTimerRef = useRef<number | null>(null);
  const sceneTransitionTimerRef = useRef<number | null>(null);
  const sceneSurfaceCommitTimerRef = useRef<number | null>(null);
  const sceneTabSwitchTimerRef = useRef<number | null>(null);
  const previousSceneSurfaceRef = useRef("");
  const listRef = useRef<HTMLDivElement | null>(null);

  const derived = useAgentActivityDerived({
    events,
    cursor,
    previewTab,
    stageAttachment,
    snapshotFailedEventId,
    streaming,
  });

  const {
    activeEvent,
    activeRoleColor,
    activeRoleLabel,
    browserUrl,
    canRenderPdfFrame,
    cursorLabel,
    desktopStatus,
    docBodyHint,
    effectiveSnapshotUrl,
    emailBodyHint,
    emailRecipient,
    emailSubject,
    eventCursor,
    isBrowserScene,
    isDocsScene,
    isDocumentScene,
    isEmailScene,
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
    sheetBodyHint,
    stageFileName,
    stageFileUrl,
    visibleEvents,
    plannedRoadmapSteps,
    roadmapActiveIndex,
  } = derived;

  const [stableSceneSurfaceKey, setStableSceneSurfaceKey] = useState(sceneSurfaceKey);
  const [stableSceneSurfaceLabel, setStableSceneSurfaceLabel] = useState(sceneSurfaceLabel);

  const phaseTimeline = useMemo(
    () => derivePhaseTimeline(visibleEvents, activeEvent),
    [visibleEvents, activeEvent?.event_id],
  );

  const handleSelectEvent = (event: AgentActivityEvent, index: number) => {
    setCursor(index);
    setIsPlaying(false);
    onJumpToEvent?.(event);
    const shadowRaw = event.data?.["shadow"] ?? event.metadata?.["shadow"];
    const isShadowEvent =
      typeof shadowRaw === "boolean"
        ? shadowRaw
        : ["true", "1", "yes"].includes(String(shadowRaw ?? "").trim().toLowerCase());
    if (isShadowEvent) {
      return;
    }
    if (
      event.event_type === "drive.go_to_doc" ||
      event.event_type === "drive.go_to_sheet" ||
      event.event_type.startsWith("docs.") ||
      event.event_type.startsWith("sheets.")
    ) {
      const sourceUrl = resolveEventSourceUrl(event);
      if (sourceUrl) {
        window.open(sourceUrl, "_blank", "noopener,noreferrer");
      }
    }
  };

  useEffect(() => {
    if (!orderedEvents.length) {
      setCursor(0);
      setIsPlaying(false);
      return;
    }
    if (streaming) {
      setCursor(orderedEvents.length - 1);
      setIsPlaying(false);
    } else if (cursor > orderedEvents.length - 1) {
      setCursor(orderedEvents.length - 1);
    }
  }, [orderedEvents.length, streaming, cursor]);

  useEffect(() => {
    if (!isPlaying || streaming || orderedEvents.length <= 1) {
      if (timerRef.current) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
      return;
    }

    timerRef.current = window.setInterval(() => {
      setCursor((prev) => {
        const next = prev + 1;
        if (next >= orderedEvents.length) {
          setIsPlaying(false);
          return orderedEvents.length - 1;
        }
        return next;
      });
    }, Math.max(190, Math.round(520 / speed)));

    return () => {
      if (timerRef.current) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [isPlaying, speed, orderedEvents.length, streaming]);

  useEffect(() => {
    if (!activeEvent) {
      setSceneText("");
      return;
    }

    const targetText = buildSceneNarrative(activeEvent) || "Processing step...";
    setSceneText("");

    let index = 0;
    if (typeTimerRef.current) {
      window.clearInterval(typeTimerRef.current);
      typeTimerRef.current = null;
    }

    typeTimerRef.current = window.setInterval(() => {
      index += 1;
      setSceneText(targetText.slice(0, index));
      if (index >= targetText.length && typeTimerRef.current) {
        window.clearInterval(typeTimerRef.current);
        typeTimerRef.current = null;
      }
    }, 8);

    return () => {
      if (typeTimerRef.current) {
        window.clearInterval(typeTimerRef.current);
        typeTimerRef.current = null;
      }
    };
  }, [activeEvent?.event_id]);

  // Reset previewTab to browser whenever a new streaming run starts so that
  // stale "document" state from a previous run doesn't open Google Docs uninvited.
  const prevStreamingRef = useRef(streaming);
  useEffect(() => {
    if (streaming && !prevStreamingRef.current) {
      setPreviewTab("browser");
    }
    prevStreamingRef.current = streaming;
  }, [streaming]);

  useEffect(() => {
    if (!activeEvent) {
      return;
    }
    if (!streaming) {
      if (sceneTabSwitchTimerRef.current) {
        window.clearTimeout(sceneTabSwitchTimerRef.current);
        sceneTabSwitchTimerRef.current = null;
      }
      return;
    }
    const nextTab = sceneTab === "system" ? previewTab : sceneTab;
    if (sceneTabSwitchTimerRef.current) {
      window.clearTimeout(sceneTabSwitchTimerRef.current);
      sceneTabSwitchTimerRef.current = null;
    }
    if (nextTab !== previewTab) {
      sceneTabSwitchTimerRef.current = window.setTimeout(() => {
        setPreviewTab(nextTab);
        sceneTabSwitchTimerRef.current = null;
      }, 180);
    }
  }, [activeEvent?.event_id, previewTab, sceneTab, streaming]);

  useEffect(() => {
    if (!streaming) {
      setStableSceneSurfaceKey(sceneSurfaceKey);
      setStableSceneSurfaceLabel(sceneSurfaceLabel);
      return;
    }
    if (sceneSurfaceKey === stableSceneSurfaceKey) {
      return;
    }
    if (sceneSurfaceCommitTimerRef.current) {
      window.clearTimeout(sceneSurfaceCommitTimerRef.current);
      sceneSurfaceCommitTimerRef.current = null;
    }
    sceneSurfaceCommitTimerRef.current = window.setTimeout(() => {
      setStableSceneSurfaceKey(sceneSurfaceKey);
      setStableSceneSurfaceLabel(sceneSurfaceLabel);
      sceneSurfaceCommitTimerRef.current = null;
    }, 180);
  }, [sceneSurfaceKey, sceneSurfaceLabel, stableSceneSurfaceKey, streaming]);

  useEffect(() => {
    if (!streaming) {
      return;
    }
    const previous = previousSceneSurfaceRef.current;
    if (!previous) {
      previousSceneSurfaceRef.current = stableSceneSurfaceKey;
      return;
    }
    if (previous === stableSceneSurfaceKey) {
      return;
    }
    previousSceneSurfaceRef.current = stableSceneSurfaceKey;
    setSceneTransitionLabel(`Switched to ${stableSceneSurfaceLabel}`);
    if (sceneTransitionTimerRef.current) {
      window.clearTimeout(sceneTransitionTimerRef.current);
      sceneTransitionTimerRef.current = null;
    }
    sceneTransitionTimerRef.current = window.setTimeout(() => {
      setSceneTransitionLabel("");
      sceneTransitionTimerRef.current = null;
    }, 1100);
  }, [stableSceneSurfaceKey, stableSceneSurfaceLabel, streaming]);

  useEffect(() => {
    if (!activeEvent?.event_id) {
      return;
    }
    setSnapshotFailedEventId("");
  }, [activeEvent?.event_id]);

  useEffect(
    () => () => {
      if (sceneTransitionTimerRef.current) {
        window.clearTimeout(sceneTransitionTimerRef.current);
        sceneTransitionTimerRef.current = null;
      }
      if (sceneSurfaceCommitTimerRef.current) {
        window.clearTimeout(sceneSurfaceCommitTimerRef.current);
        sceneSurfaceCommitTimerRef.current = null;
      }
      if (sceneTabSwitchTimerRef.current) {
        window.clearTimeout(sceneTabSwitchTimerRef.current);
        sceneTabSwitchTimerRef.current = null;
      }
    },
    [],
  );

  useEffect(() => {
    if (!eventCursor) {
      return;
    }
    setCursorPoint(eventCursor);
  }, [eventCursor]);

  useJumpTargetSelection({
    jumpTarget,
    orderedEvents,
    setCursor,
    setIsPlaying,
  });

  useOverlayKeyboardShortcuts({
    isFullscreenViewer,
    isCinemaMode,
    streaming,
    orderedEventsLength: orderedEvents.length,
    setIsFullscreenViewer,
    setIsCinemaMode,
    setIsPlaying,
    setCursor,
  });

  useAutoScrollTimeline({
    streaming,
    orderedEventsLength: orderedEvents.length,
    activeEventId: activeEvent?.event_id,
    listRef,
  });

  if (!orderedEvents.length) {
    return null;
  }

  const runId = orderedEvents[0]?.run_id || activeEvent?.run_id || "";

  const exportRun = async () => {
    if (!runId || isExporting) {
      return;
    }
    setIsExporting(true);
    try {
      const payload = await exportAgentRunEvents(runId);
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json;charset=utf-8",
      });
      const href = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = href;
      link.download = `agent-run-${runId}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(href);
    } finally {
      setIsExporting(false);
    }
  };

  const sharedViewerProps = {
    streaming,
    isTheaterView,
    isFocusMode,
    desktopStatus,
    sceneTransitionLabel,
    safeCursor,
    totalEvents: orderedEvents.length,
    activeRoleColor,
    activeRoleLabel,
    roleNarrative,
    activeTitle: sceneEvent?.title || activeEvent?.title || "",
    activeDetail: sceneEvent?.detail || activeEvent?.detail || "",
    sceneText,
    cursorLabel,
    stageFileName,
    eventCursor,
    cursorPoint,
    effectiveSnapshotUrl,
    isBrowserScene,
    isEmailScene,
    isDocumentScene,
    isDocsScene,
    isSheetsScene,
    isSystemScene,
    canRenderPdfFrame,
    stageFileUrl,
    browserUrl,
    emailRecipient,
    emailSubject,
    emailBodyHint,
    docBodyHint,
    sheetBodyHint,
    activeEventType: activeEvent?.event_type || sceneEvent?.event_type || "",
    activeSceneData: plannedRoadmapSteps.length
      ? { ...mergedSceneData, __roadmap_steps: plannedRoadmapSteps, __roadmap_active_index: roadmapActiveIndex }
      : mergedSceneData,
    sceneDocumentUrl,
    sceneSpreadsheetUrl,
    onSnapshotError: () => {
      if (sceneEvent?.event_id) {
        setSnapshotFailedEventId(sceneEvent.event_id);
      }
    },
  };

  const approvalEvent = streaming
    ? orderedEvents
        .slice()
        .reverse()
        .find((event) => event.event_type === "approval_required") || null
    : null;

  return (
    <div className="mb-4 overflow-hidden rounded-3xl border border-black/[0.08] bg-[#f7f7f8] p-4 shadow-[0_8px_24px_-20px_rgba(0,0,0,0.32)]">
      <ActivityHeader
        streaming={streaming}
        isExporting={isExporting}
        runId={runId}
        isPlaying={isPlaying}
        speed={speed}
        onExport={() => {
          void exportRun();
        }}
        onJumpFirst={() => {
          setCursor(0);
          setIsPlaying(false);
        }}
        onTogglePlay={() => setIsPlaying((prev) => !prev)}
        onJumpLast={() => {
          setCursor(orderedEvents.length - 1);
          setIsPlaying(false);
        }}
        onCycleSpeed={() => {
          const currentIndex = playbackRates.findIndex((item) => item === speed);
          const nextRate = playbackRates[(currentIndex + 1) % playbackRates.length];
          setSpeed(nextRate);
        }}
      />

      <ActivityPanelBody
        sharedViewerProps={sharedViewerProps}
        phaseTimeline={phaseTimeline}
        streaming={streaming}
        visibleEvents={visibleEvents}
        orderedEvents={orderedEvents}
        safeCursor={safeCursor}
        progressPercent={progressPercent}
        activeEvent={activeEvent}
        sceneText={sceneText}
        onSelectEvent={handleSelectEvent}
        listRef={listRef}
        setCursor={setCursor}
        setIsPlaying={setIsPlaying}
        isFocusMode={isFocusMode}
        setIsFocusMode={setIsFocusMode}
        isTheaterView={isTheaterView}
        setIsTheaterView={setIsTheaterView}
        isFullscreenViewer={isFullscreenViewer}
        setIsFullscreenViewer={setIsFullscreenViewer}
        approvalEvent={approvalEvent}
        approvalDismissed={approvalDismissed}
        setApprovalDismissed={setApprovalDismissed}
      />

      <CinemaOverlay
        open={isCinemaMode}
        phaseTimeline={phaseTimeline}
        safeCursor={safeCursor}
        orderedEvents={orderedEvents}
        activeEvent={activeEvent}
        visibleEvents={visibleEvents}
        plannedRoadmapSteps={plannedRoadmapSteps}
        roadmapActiveIndex={roadmapActiveIndex}
        sharedViewerProps={{
          ...sharedViewerProps,
          onToggleTheaterView: () => setIsTheaterView((prev) => !prev),
          onToggleFocusMode: () => setIsFocusMode((prev) => !prev),
          onOpenFullscreen: () => {},
        }}
        streaming={streaming}
        isPlaying={isPlaying}
        setIsPlaying={setIsPlaying}
        setCursor={setCursor}
        onClose={() => setIsCinemaMode(false)}
      />

    </div>
  );
}
