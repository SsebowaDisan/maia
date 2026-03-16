import { useEffect, useMemo, useRef, useState } from "react";
import { exportAgentRunEvents } from "../../../api/client";
import type { AgentActivityEvent } from "../../types";
import { derivePhaseTimeline } from "./helpers";
import type { AgentActivityPanelProps } from "./types";
import { useAgentActivityDerived } from "./useAgentActivityDerived";
import { ActivityHeader } from "./ActivityHeader";
import { ActivityPanelBody } from "./ActivityPanelBody";
import { CinemaOverlay } from "./CinemaOverlay";
import { useAutoScrollTimeline, useJumpTargetSelection, useOverlayKeyboardShortcuts } from "./useActivityPanelNavigation";
import { deriveTheatreStage, desiredPreviewTabForStage } from "./deriveTheatreStage";
import { useSceneTextTyping } from "./useSceneTextTyping";
import { useSceneSurfaceTransition } from "./useSceneSurfaceTransition";
import { useManualPreviewTabOverride } from "./useManualPreviewTabOverride";
import { useTheatreTelemetry } from "./useTheatreTelemetry";
import { resolveStagedTheatreEnabled } from "./theatreFeatureFlags";
import { latestOpenApprovalEvent } from "./approvalGateState";
import { maybeOpenEventSource } from "./eventSelection";
const playbackRates = [0.75, 1, 1.5, 2] as const;

export function AgentActivityPanel({
  events,
  streaming,
  stageAttachment,
  needsHumanReview,
  humanReviewNotes,
  jumpTarget = null,
  onJumpToEvent,
}: AgentActivityPanelProps) {
  const stagedTheatreEnabled = resolveStagedTheatreEnabled(import.meta.env.VITE_STAGED_THEATRE_ENABLED);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState<(typeof playbackRates)[number]>(1);
  const [cursor, setCursor] = useState(0);
  const [cursorPoint, setCursorPoint] = useState({ x: 14, y: 24 });
  const [previewTab, setPreviewTab] = useState<"browser" | "document" | "email" | "system">(
    stagedTheatreEnabled ? "system" : "browser",
  );
  const [manualTabOverride, setManualTabOverride] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [isTheaterView, setIsTheaterView] = useState(true);
  const [isFullscreenViewer, setIsFullscreenViewer] = useState(false);
  const [isCinemaMode, setIsCinemaMode] = useState(false);
  const [approvalDismissed, setApprovalDismissed] = useState<string>("");
  const [isFocusMode, setIsFocusMode] = useState(true);
  const [snapshotFailedEventId, setSnapshotFailedEventId] = useState("");

  const timerRef = useRef<number | null>(null);
  const sceneTabSwitchTimerRef = useRef<number | null>(null);
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
    activePhase,
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
    surfaceCommit,
    sheetBodyHint,
    stageFileName,
    stageFileUrl,
    visibleEvents,
    plannedRoadmapSteps,
    roadmapActiveIndex,
    activeSuggestion,
    activeStepIndex,
  } = derived;

  const { sceneTransitionLabel } = useSceneSurfaceTransition({
    sceneSurfaceKey,
    sceneSurfaceLabel,
    streaming,
  });

  const sceneText = useSceneTextTyping(activeEvent);

  const phaseTimeline = useMemo(
    () => derivePhaseTimeline(visibleEvents, activeEvent),
    [visibleEvents, activeEvent?.event_id],
  );

  const handleSelectEvent = (event: AgentActivityEvent, index: number) => {
    setCursor(index);
    setIsPlaying(false);
    onJumpToEvent?.(event);
    maybeOpenEventSource(event);
  };

  const handleReplayStep = (event: Record<string, unknown>, index: number) => {
    const replayEventId = String(event.event_id || "").trim();
    if (replayEventId) {
      const matchedIndex = orderedEvents.findIndex(
        (candidate) => String(candidate.event_id || "").trim() === replayEventId,
      );
      if (matchedIndex >= 0) {
        setCursor(matchedIndex);
        setIsPlaying(false);
        return;
      }
    }
    const clampedIndex = Math.max(0, Math.min(orderedEvents.length - 1, Number(index) || 0));
    setCursor(clampedIndex);
    setIsPlaying(false);
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

  const approvalEvent = useMemo(
    () => (streaming ? latestOpenApprovalEvent(orderedEvents) : null),
    [orderedEvents, streaming],
  );
  const approvalEventId = String(approvalEvent?.event_id || "");
  const hasApprovalGate = Boolean(approvalEventId && approvalDismissed !== approvalEventId);
  const activeEventType = String(activeEvent?.event_type || "").toLowerCase();
  const blockedReason = String(
    activeEvent?.data?.["blocked_reason"] ?? activeEvent?.metadata?.["blocked_reason"] ?? "",
  ).trim();
  const needsInput = String(
    activeEvent?.data?.["needs_input"] ?? activeEvent?.metadata?.["needs_input"] ?? "",
  ).trim();
  const hasError =
    activeEventType.endsWith("_failed") ||
    activeEventType === "tool_failed" ||
    activeEventType === "error" ||
    activeEventType === "policy_blocked";
  const isBlocked = Boolean(activeEventType === "policy_blocked" || blockedReason.length > 0);
  const theatreStage = useMemo(
    () =>
      deriveTheatreStage({
        streaming,
        hasEvents: orderedEvents.length > 0,
        activePhase,
        surfaceCommit,
        needsHumanReview: Boolean(needsHumanReview),
        hasApprovalGate,
        isBlocked,
        needsInput: needsInput.length > 0,
        hasError,
      }),
    [
      activePhase,
      hasApprovalGate,
      hasError,
      isBlocked,
      needsHumanReview,
      needsInput,
      orderedEvents.length,
      streaming,
      surfaceCommit,
    ],
  );
  const desiredPreviewTab = useMemo(
    () => {
      if (!stagedTheatreEnabled) {
        return sceneTab === "system" ? previewTab : sceneTab;
      }
      return desiredPreviewTabForStage({
        stage: theatreStage,
        sceneTab,
        surfaceCommit,
        fallbackPreviewTab: previewTab,
        manualOverride: manualTabOverride,
      });
    },
    [manualTabOverride, previewTab, sceneTab, stagedTheatreEnabled, surfaceCommit, theatreStage],
  );

  const prevStreamingRef = useRef(streaming);
  useEffect(() => {
    if (streaming && !prevStreamingRef.current) {
      setPreviewTab(stagedTheatreEnabled ? "system" : "browser");
      setManualTabOverride(false);
    }
    if (!streaming) {
      setManualTabOverride(false);
    }
    prevStreamingRef.current = streaming;
  }, [stagedTheatreEnabled, streaming]);

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
    if (manualTabOverride) {
      return;
    }
    const nextTab = desiredPreviewTab;
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
  }, [activeEvent?.event_id, desiredPreviewTab, manualTabOverride, previewTab, streaming]);

  useManualPreviewTabOverride({ streaming: streaming && stagedTheatreEnabled, setPreviewTab, setManualTabOverride });
  useTheatreTelemetry({
    streaming,
    theatreStage,
    manualTabOverride,
    runId: orderedEvents[0]?.run_id || "",
  });

  useEffect(() => {
    if (!activeEvent?.event_id) {
      return;
    }
    setSnapshotFailedEventId("");
  }, [activeEvent?.event_id]);

  useEffect(
    () => () => {
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
    runId,
    activeStepIndex,
    interactionSuggestion: activeSuggestion,
    computerUseSessionId: String(mergedSceneData["computer_use_session_id"] ?? "").trim() || undefined,
    computerUseTask: String(mergedSceneData["computer_use_task"] ?? "").trim() || undefined,
    computerUseModel: String(mergedSceneData["computer_use_model"] ?? "").trim() || undefined,
    computerUseMaxIterations: (() => {
      const value = Number(mergedSceneData["computer_use_max_iterations"] ?? Number.NaN);
      return Number.isFinite(value) && value > 0 ? Math.round(value) : null;
    })(),
    activeSceneData: plannedRoadmapSteps.length
      ? { ...mergedSceneData, __roadmap_steps: plannedRoadmapSteps, __roadmap_active_index: roadmapActiveIndex }
      : mergedSceneData,
    sceneDocumentUrl,
    sceneSpreadsheetUrl,
    showDoneStage: (() => {
      const finalEventType = String(activeEvent?.event_type || sceneEvent?.event_type || "").toLowerCase();
      const completionEventSignal =
        finalEventType === "email_sent" ||
        finalEventType === "browser_contact_confirmation" ||
        finalEventType === "verification_completed" ||
        finalEventType === "llm.delivery_check_completed" ||
        finalEventType.endsWith("_completed") ||
        finalEventType.endsWith("_done") ||
        finalEventType.endsWith("_finished");
      const terminalState =
        theatreStage === "done" ||
        (theatreStage !== "error" &&
          theatreStage !== "blocked" &&
          theatreStage !== "needs_input" &&
          theatreStage !== "review" &&
          theatreStage !== "confirm" &&
          completionEventSignal);
      return !streaming && safeCursor >= Math.max(0, orderedEvents.length - 1) && terminalState;
    })(),
    doneStageTitle: desktopStatus || "Task completed",
    doneStageDetail:
      (sceneText || roleNarrative || sceneEvent?.detail || activeEvent?.detail || "").trim() ||
      "All requested work is complete and ready.",
    onSnapshotError: () => {
      if (sceneEvent?.event_id) {
        setSnapshotFailedEventId(sceneEvent.event_id);
      }
    },
  };

  return (
    <div className="mb-4 overflow-hidden rounded-3xl border border-[#e5e7eb] bg-[#f8f9fb] p-4 shadow-[0_20px_40px_-36px_rgba(15,23,42,0.45)]">
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
        plannedRoadmapSteps={plannedRoadmapSteps}
        roadmapActiveIndex={roadmapActiveIndex}
        theatreStage={theatreStage}
        needsHumanReview={Boolean(needsHumanReview)}
        humanReviewNotes={humanReviewNotes}
        activityRunId={runId}
        onReplayStep={handleReplayStep}
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
