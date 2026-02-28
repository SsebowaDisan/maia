import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Pause, Play, SkipBack, SkipForward, Timer } from "lucide-react";
import { exportAgentRunEvents } from "../../../api/client";
import type { AgentActivityEvent } from "../../types";
import { derivePhaseTimeline, resolveEventSourceUrl } from "./helpers";
import { DesktopViewer } from "./DesktopViewer";
import { FullscreenViewerOverlay } from "./FullscreenViewerOverlay";
import { PhaseTimeline } from "./PhaseTimeline";
import { PreviewTabsCard } from "./PreviewTabsCard";
import { ReplayTimeline } from "./ReplayTimeline";
import type { AgentActivityPanelProps } from "./types";
import { useAgentActivityDerived } from "./useAgentActivityDerived";

const playbackRates = [0.75, 1, 1.5, 2] as const;

export function AgentActivityPanel({
  events,
  streaming,
  stageAttachment,
  needsHumanReview,
  humanReviewNotes,
  onJumpToEvent,
}: AgentActivityPanelProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState<(typeof playbackRates)[number]>(1);
  const [cursor, setCursor] = useState(0);
  const [sceneText, setSceneText] = useState("");
  const [cursorPoint, setCursorPoint] = useState({ x: 14, y: 24 });
  const [previewTab, setPreviewTab] = useState<"browser" | "document" | "email" | "system">("document");
  const [isExporting, setIsExporting] = useState(false);
  const [isTheaterView, setIsTheaterView] = useState(true);
  const [isFullscreenViewer, setIsFullscreenViewer] = useState(false);
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

    const baseText = [activeEvent.title, activeEvent.detail].filter(Boolean).join(" - ");
    const targetText = baseText || "Processing step...";
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

  useEffect(() => {
    if (!isFullscreenViewer) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsFullscreenViewer(false);
      }
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [isFullscreenViewer]);

  if (!orderedEvents.length) {
    return null;
  }

  const trimmedReviewNotes = String(humanReviewNotes || "").trim();

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
    activeSceneData: mergedSceneData,
    sceneDocumentUrl,
    sceneSpreadsheetUrl,
    onSnapshotError: () => {
      if (sceneEvent?.event_id) {
        setSnapshotFailedEventId(sceneEvent.event_id);
      }
    },
  };

  return (
    <div className="mb-4 overflow-hidden rounded-3xl border border-black/[0.08] bg-[radial-gradient(circle_at_10%_0%,#ffffff_0%,#f5f5f7_55%,#efeff2_100%)] p-4 shadow-[0_10px_30px_-25px_rgba(0,0,0,0.45)]">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.14em] text-[#86868b]">Agent Activity</p>
          <p className="text-[16px] font-semibold text-[#1d1d1f]">
            {streaming ? "Live execution feed" : "Replay timeline"}
          </p>
          {needsHumanReview ? (
            <div className="mt-1.5 inline-flex max-w-[520px] items-start gap-1.5 rounded-lg border border-[#f5a524]/40 bg-[#fff7e6] px-2.5 py-1.5 text-[11px] text-[#7a4a00]">
              <AlertTriangle className="mt-[1px] h-3.5 w-3.5 shrink-0" />
              <div className="space-y-0.5">
                <p className="font-medium leading-tight">Needs human review</p>
                {trimmedReviewNotes ? (
                  <p className="leading-tight text-[#8e5710]">{trimmedReviewNotes}</p>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>

        <div className="inline-flex items-center gap-1 rounded-xl border border-black/[0.08] bg-white/90 p-1 backdrop-blur">
          <button
            type="button"
            onClick={() => {
              void exportRun();
            }}
            disabled={isExporting || !runId}
            className="rounded-lg px-2 py-1.5 text-[11px] text-[#4c4c50] transition hover:bg-[#f3f3f5] disabled:cursor-not-allowed disabled:opacity-50"
            title="Export run JSON"
          >
            {isExporting ? "Exporting..." : "Export"}
          </button>
          <button
            type="button"
            onClick={() => {
              setCursor(0);
              setIsPlaying(false);
            }}
            className="rounded-lg p-2 text-[#6e6e73] transition hover:bg-[#f3f3f5]"
            title="Jump to first step"
          >
            <SkipBack className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={() => setIsPlaying((prev) => !prev)}
            disabled={streaming}
            className="rounded-lg p-2 text-[#1d1d1f] transition hover:bg-[#f3f3f5] disabled:cursor-not-allowed disabled:opacity-50"
            title={isPlaying ? "Pause replay" : "Play replay"}
          >
            {isPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
          </button>
          <button
            type="button"
            onClick={() => {
              setCursor(orderedEvents.length - 1);
              setIsPlaying(false);
            }}
            className="rounded-lg p-2 text-[#6e6e73] transition hover:bg-[#f3f3f5]"
            title="Jump to latest step"
          >
            <SkipForward className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={() => {
              const currentIndex = playbackRates.findIndex((item) => item === speed);
              const nextRate = playbackRates[(currentIndex + 1) % playbackRates.length];
              setSpeed(nextRate);
            }}
            disabled={streaming}
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-[11px] font-medium text-[#4c4c50] transition hover:bg-[#f3f3f5] disabled:cursor-not-allowed disabled:opacity-50"
            title="Cycle replay speed"
          >
            <Timer className="h-3.5 w-3.5" />
            {speed}x
          </button>
        </div>
      </div>

      <DesktopViewer
        {...sharedViewerProps}
        onToggleTheaterView={() => setIsTheaterView((prev) => !prev)}
        onToggleFocusMode={() => setIsFocusMode((prev) => !prev)}
        onOpenFullscreen={() => {
          setIsFullscreenViewer(true);
          setIsFocusMode(true);
        }}
      />

      <PhaseTimeline phases={phaseTimeline} streaming={streaming} />

      <PreviewTabsCard
        previewTab={previewTab}
        setPreviewTab={setPreviewTab}
        browserEvents={browserEvents}
        documentEvents={documentEvents}
        emailEvents={emailEvents}
        systemEvents={systemEvents}
        stageFileName={stageFileName}
        activeTab={activeTab}
        totalEvents={orderedEvents.length}
      />

      <ReplayTimeline
        streaming={streaming}
        safeCursor={safeCursor}
        totalEvents={orderedEvents.length}
        progressPercent={progressPercent}
        setCursor={setCursor}
        setIsPlaying={setIsPlaying}
        activeEvent={activeEvent}
        sceneText={sceneText}
        filmstripEvents={filmstripEvents}
        visibleEvents={visibleEvents}
        onSelectEvent={handleSelectEvent}
        listRef={listRef}
      />

      <FullscreenViewerOverlay
        isOpen={isFullscreenViewer}
        isFocusMode={isFocusMode}
        onToggleFocusMode={() => setIsFocusMode((prev) => !prev)}
        onClose={() => setIsFullscreenViewer(false)}
        desktopViewer={
          <DesktopViewer
            {...sharedViewerProps}
            fullscreen
            onToggleTheaterView={() => setIsTheaterView((prev) => !prev)}
            onToggleFocusMode={() => setIsFocusMode((prev) => !prev)}
            onOpenFullscreen={() => setIsFullscreenViewer(true)}
          />
        }
        visibleEvents={visibleEvents}
        activeEvent={activeEvent}
        sceneText={sceneText}
        onSelectEvent={handleSelectEvent}
      />
    </div>
  );
}
