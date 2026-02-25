import { useEffect, useMemo, useRef, useState } from "react";
import {
  Maximize2,
  Minimize2,
  Monitor,
  MousePointer2,
  Pause,
  Play,
  SkipBack,
  SkipForward,
  Timer,
  X,
} from "lucide-react";
import { exportAgentRunEvents, getAgentEventSnapshotUrl, getRawFileUrl } from "../../api/client";
import type { AgentActivityEvent, ChatAttachment } from "../types";
import {
  type PreviewTab,
  eventMetadataString,
  findRecentMetadataString,
  sampleFilmstripEvents,
  styleForEvent,
  tabForEventType,
} from "./agentActivityMeta";
import { AgentDesktopScene } from "./AgentDesktopScene";

interface AgentActivityPanelProps {
  events: AgentActivityEvent[];
  streaming: boolean;
  stageAttachment?: ChatAttachment;
  onJumpToEvent?: (event: AgentActivityEvent) => void;
}

const playbackRates = [0.75, 1, 1.5, 2] as const;
const URL_PATTERN = /(https?:\/\/[^\s]+)/i;

function readStringField(
  value: unknown,
): string {
  return typeof value === "string" ? value.trim() : "";
}

export function AgentActivityPanel({
  events,
  streaming,
  stageAttachment,
  onJumpToEvent,
}: AgentActivityPanelProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState<(typeof playbackRates)[number]>(1);
  const [cursor, setCursor] = useState(0);
  const [sceneText, setSceneText] = useState("");
  const [cursorPoint, setCursorPoint] = useState({ x: 14, y: 24 });
  const [previewTab, setPreviewTab] = useState<PreviewTab>("document");
  const [isExporting, setIsExporting] = useState(false);
  const [isTheaterView, setIsTheaterView] = useState(true);
  const [isFullscreenViewer, setIsFullscreenViewer] = useState(false);
  const [isFocusMode, setIsFocusMode] = useState(true);
  const [snapshotFailedEventId, setSnapshotFailedEventId] = useState("");

  const timerRef = useRef<number | null>(null);
  const typeTimerRef = useRef<number | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

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
  const activeStyle = styleForEvent(activeEvent);
  const activeTab = tabForEventType(activeEvent?.event_type || "");
  const sceneEvent = useMemo(() => {
    if (!activeEvent) {
      return null;
    }
    const activeEventTab = tabForEventType(activeEvent.event_type || "");
    if (activeEventTab !== "system") {
      return activeEvent;
    }
    for (let idx = visibleEvents.length - 1; idx >= 0; idx -= 1) {
      const candidate = visibleEvents[idx];
      if (tabForEventType(candidate.event_type || "") !== "system") {
        return candidate;
      }
    }
    return activeEvent;
  }, [activeEvent, visibleEvents]);

  const progressPercent =
    orderedEvents.length <= 1
      ? 100
      : Math.round((safeCursor / (orderedEvents.length - 1)) * 100);

  const browserEvents = useMemo(
    () => visibleEvents.filter((event) => tabForEventType(event.event_type) === "browser"),
    [visibleEvents],
  );
  const documentEvents = useMemo(
    () => visibleEvents.filter((event) => tabForEventType(event.event_type) === "document"),
    [visibleEvents],
  );
  const emailEvents = useMemo(
    () => visibleEvents.filter((event) => tabForEventType(event.event_type) === "email"),
    [visibleEvents],
  );
  const systemEvents = useMemo(
    () => visibleEvents.filter((event) => tabForEventType(event.event_type) === "system"),
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
  const activeSceneTab = tabForEventType(sceneEvent?.event_type || "");
  const isBrowserScene = activeSceneTab === "browser";
  const isEmailScene = activeSceneTab === "email";
  const isDocumentScene = activeSceneTab === "document";
  const isSystemScene = activeSceneTab === "system";

  const snapshotUrl = useMemo(() => {
    if (!sceneEvent) {
      return "";
    }
    const raw = readStringField(sceneEvent.snapshot_ref);
    if (!raw) {
      return "";
    }
    if (
      raw.startsWith("http://") ||
      raw.startsWith("https://") ||
      raw.startsWith("data:image/")
    ) {
      return raw;
    }
    if (!sceneEvent.run_id || !sceneEvent.event_id) {
      return "";
    }
    return getAgentEventSnapshotUrl(sceneEvent.run_id, sceneEvent.event_id);
  }, [sceneEvent?.event_id, sceneEvent?.run_id, sceneEvent?.snapshot_ref]);
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
      if (event.event_type !== "email_set_body" && event.event_type !== "email_type_body") {
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

  const desktopStatus = useMemo(() => {
    if (activeEvent?.event_type === "desktop_starting") {
      return "Starting secure agent desktop";
    }
    if (activeEvent?.event_type === "desktop_ready") {
      return "Desktop live. Beginning execution.";
    }
    if (activeEvent?.event_type === "response_writing") {
      return "Writing response while tools and evidence remain visible";
    }
    if (streaming) {
      return "Desktop session is running live";
    }
    return "Desktop replay";
  }, [activeEvent?.event_type, streaming]);

  const cursorLabel = useMemo(() => {
    const type = activeEvent?.event_type || "";
    if (type === "document_opened") {
      return "Open file";
    }
    if (type === "document_scanned") {
      return "Scanning page";
    }
    if (type === "highlights_detected") {
      return "Highlighting";
    }
    if (type === "response_writing") {
      return "Writing";
    }
    if (type === "browser_open") {
      return "Opening browser";
    }
    if (type === "browser_keyword_highlight") {
      return "Highlighting keywords";
    }
    if (type === "browser_copy_selection") {
      return "Copying excerpt";
    }
    if (type === "doc_copy_clipboard") {
      return "Copying note";
    }
    if (type === "doc_paste_clipboard") {
      return "Pasting content";
    }
    if (type === "browser_navigate" || type === "web_search_started") {
      return "Navigating";
    }
    if (type === "sheet_cell_update") {
      return "Updating cells";
    }
    if (type === "sheet_append_row") {
      return "Appending row";
    }
    if (type === "email_set_body") {
      return "Typing email";
    }
    if (type === "email_type_body") {
      return "Typing email";
    }
    if (type === "email_click_send") {
      return "Clicking send";
    }
    if (type === "email_sent") {
      return "Send complete";
    }
    if (type === "web_result_opened") {
      return "Opening source";
    }
    return "Agent cursor";
  }, [activeEvent?.event_type]);

  const shouldAnimateCursor = useMemo(() => {
    const type = activeEvent?.event_type || "";
    return (
      streaming ||
      [
        "desktop_starting",
        "desktop_ready",
        "document_opened",
        "document_scanned",
        "highlights_detected",
        "web_result_opened",
        "response_writing",
        "browser_open",
        "browser_navigate",
        "browser_keyword_highlight",
        "browser_copy_selection",
        "web_search_started",
        "doc_copy_clipboard",
        "doc_paste_clipboard",
        "doc_type_text",
        "sheet_cell_update",
        "sheet_append_row",
        "email_draft_create",
        "email_open_compose",
        "email_set_to",
        "email_set_subject",
        "email_set_body",
        "email_type_body",
        "email_ready_to_send",
        "email_click_send",
        "email_sent",
      ].includes(type)
    );
  }, [activeEvent?.event_type, streaming]);

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
    if (streaming) {
      setPreviewTab(activeTab);
    }
  }, [activeEvent?.event_id, activeTab, streaming]);

  useEffect(() => {
    if (!activeEvent?.event_id) {
      return;
    }
    setSnapshotFailedEventId("");
  }, [activeEvent?.event_id]);

  useEffect(() => {
    if (!shouldAnimateCursor) {
      return;
    }

    const interval = window.setInterval(() => {
      setCursorPoint((current) => {
        const eventType = activeEvent?.event_type || "";
        if (eventType === "document_scanned") {
          const nextY = current.y >= 84 ? 18 : Math.min(88, current.y + 10);
          const nextX = 22 + Math.random() * 54;
          return { x: nextX, y: nextY };
        }
        if (eventType === "response_writing") {
          const nextX = current.x >= 82 ? 16 : current.x + 9;
          const nextY = 70 + Math.random() * 15;
          return { x: nextX, y: nextY };
        }
        const nextX = 12 + Math.random() * 76;
        const nextY = 16 + Math.random() * 70;
        return { x: nextX, y: nextY };
      });
    }, 640);

    return () => {
      window.clearInterval(interval);
    };
  }, [shouldAnimateCursor, activeEvent?.event_id]);

  useEffect(() => {
    if (!listRef.current) {
      return;
    }
    const active = listRef.current.querySelector<HTMLElement>("[data-activity-active='true']");
    if (active) {
      active.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [safeCursor, orderedEvents.length]);

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

  const ActiveIcon = activeStyle.icon;
  const runId = orderedEvents[0]?.run_id || activeEvent?.run_id || "";
  const inlineViewerHeightClass = isTheaterView
    ? "h-[320px] md:h-[420px] xl:h-[520px]"
    : "h-[220px] md:h-[280px]";
  const fullscreenViewerHeightClass = isFocusMode
    ? "h-[calc(100vh-160px)]"
    : "h-[74vh]";

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
    } catch {
      // Keep UX quiet when export fails; run can still be replayed in-app.
    } finally {
      setIsExporting(false);
    }
  };

  const renderDesktopViewer = (options?: { fullscreen?: boolean }) => {
    const fullscreen = Boolean(options?.fullscreen);
    const viewerHeightClass = fullscreen
      ? fullscreenViewerHeightClass
      : inlineViewerHeightClass;
    return (
      <div
        className={`mb-3 rounded-2xl border border-black/[0.06] bg-[#0f1115] p-3 text-white shadow-inner ${
          fullscreen ? "mb-0" : ""
        }`}
      >
        <div className="mb-2 flex items-center justify-between gap-2 text-[11px] text-white/75">
          <span className="inline-flex items-center gap-1.5">
            <Monitor className="h-3.5 w-3.5" />
            Agent desktop
          </span>
          <div className="inline-flex items-center gap-2">
            {!fullscreen ? (
              <button
                type="button"
                onClick={() => setIsTheaterView((prev) => !prev)}
                className="rounded-full border border-white/20 px-2 py-0.5 text-[10px] text-white/85 transition hover:bg-white/10"
                title={isTheaterView ? "Switch to standard viewer size" : "Switch to theater viewer size"}
              >
                {isTheaterView ? "THEATER" : "STANDARD"}
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => {
                if (fullscreen) {
                  setIsFocusMode((prev) => !prev);
                } else {
                  setIsFullscreenViewer(true);
                  setIsFocusMode(true);
                }
              }}
              className="rounded-full border border-white/20 px-2 py-0.5 text-[10px] text-white/85 transition hover:bg-white/10"
              title={fullscreen ? "Toggle focus mode" : "Open fullscreen viewer"}
            >
              {fullscreen ? (isFocusMode ? "FOCUS: ON" : "FOCUS: OFF") : "FULLSCREEN"}
            </button>
            <span className="rounded-full border border-white/20 px-2 py-0.5">
              {streaming ? "LIVE" : "REPLAY"}
            </span>
          </div>
        </div>

        <p className="mb-2 text-[13px] font-medium text-white">{desktopStatus}</p>

        <div
          className={`relative overflow-hidden rounded-xl border border-white/15 bg-[linear-gradient(180deg,#11141b_0%,#0a0c11_100%)] ${viewerHeightClass}`}
        >
          <AgentDesktopScene
            snapshotUrl={effectiveSnapshotUrl}
            isBrowserScene={isBrowserScene}
            isEmailScene={isEmailScene}
            isDocumentScene={isDocumentScene}
            isSystemScene={isSystemScene}
            canRenderPdfFrame={canRenderPdfFrame}
            stageFileUrl={stageFileUrl}
            stageFileName={stageFileName}
            browserUrl={browserUrl}
            emailRecipient={emailRecipient}
            emailSubject={emailSubject}
            emailBodyHint={emailBodyHint}
            sceneText={sceneText}
            activeTitle={sceneEvent?.title || ""}
            activeDetail={sceneEvent?.detail || ""}
            activeEventType={sceneEvent?.event_type || ""}
            activeSceneData={sceneEvent?.data || {}}
            onSnapshotError={() => {
              if (sceneEvent?.event_id) {
                setSnapshotFailedEventId(sceneEvent.event_id);
              }
            }}
          />

          <div
            className="pointer-events-none absolute left-0 right-0 h-px bg-white/25"
            style={{ top: `${cursorPoint.y}%` }}
          />

          <div
            className="pointer-events-none absolute z-20 transition-all duration-500"
            style={{ left: `${cursorPoint.x}%`, top: `${cursorPoint.y}%` }}
          >
            <div className="relative">
              <MousePointer2 className="h-4 w-4 -translate-x-1/2 -translate-y-1/2 text-white drop-shadow-[0_1px_3px_rgba(0,0,0,0.65)]" />
            </div>
          </div>

          <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/30 via-transparent to-transparent" />

          {activeEvent ? (
            <div className="pointer-events-none absolute inset-x-3 bottom-3 z-30">
              <div className="rounded-xl border border-white/20 bg-black/55 px-3 py-2 backdrop-blur-md">
                <div className="mb-1 flex items-center justify-between gap-2 text-[10px] uppercase tracking-[0.08em] text-white/70">
                  <span>{streaming ? "Live scene" : "Current scene"}</span>
                  <span className="inline-flex items-center gap-1">
                    {streaming ? (
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" />
                    ) : null}
                    Step {safeCursor + 1}/{orderedEvents.length}
                  </span>
                </div>
                <p className="truncate text-[13px] font-semibold text-white">{activeEvent.title}</p>
                <p className="mt-0.5 line-clamp-2 text-[11px] text-white/85">
                  {sceneText || activeEvent.detail || "Processing..."}
                </p>
              </div>
            </div>
          ) : null}
        </div>

        <div className="mt-2 flex items-center justify-between gap-3 text-[11px] text-white/70">
          <span className="truncate">Opened: {stageFileName}</span>
          <span className="truncate text-right">{cursorLabel}</span>
        </div>
      </div>
    );
  };

  return (
    <div className="mb-4 overflow-hidden rounded-3xl border border-black/[0.08] bg-[radial-gradient(circle_at_10%_0%,#ffffff_0%,#f5f5f7_55%,#efeff2_100%)] p-4 shadow-[0_10px_30px_-25px_rgba(0,0,0,0.45)]">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.14em] text-[#86868b]">Agent Activity</p>
          <p className="text-[16px] font-semibold text-[#1d1d1f]">
            {streaming ? "Live execution feed" : "Replay timeline"}
          </p>
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

      {renderDesktopViewer()}

      <div className="mb-3 rounded-2xl border border-black/[0.06] bg-white/90 p-3">
        <div className="mb-2 inline-flex rounded-xl border border-black/[0.08] bg-[#f5f5f7] p-1">
          {[
            { id: "browser", label: "Browser", count: browserEvents.length },
            { id: "document", label: "Document", count: documentEvents.length },
            { id: "email", label: "Email", count: emailEvents.length },
            { id: "system", label: "System", count: systemEvents.length },
          ].map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setPreviewTab(item.id as PreviewTab)}
              className={`rounded-lg px-2.5 py-1 text-[11px] font-medium transition ${
                previewTab === item.id
                  ? "bg-[#1d1d1f] text-white"
                  : "text-[#4c4c50] hover:bg-white"
              }`}
            >
              {item.label} ({item.count})
            </button>
          ))}
        </div>

        <div className="rounded-xl border border-black/[0.06] bg-[#fafafc] p-2.5">
          {previewTab === "browser" ? (
            <div className="space-y-1">
              <p className="text-[12px] font-medium text-[#1d1d1f]">Live browser actions</p>
              {browserEvents.length > 0 ? (
                <div className="max-h-32 space-y-1 overflow-y-auto pr-1">
                  {browserEvents.map((event) => (
                    <p key={`browser-${event.event_id}`} className="text-[11px] text-[#4c4c50]">
                      {event.title}
                    </p>
                  ))}
                </div>
              ) : (
                <p className="text-[11px] text-[#6e6e73]">No browser actions in this run yet.</p>
              )}
            </div>
          ) : null}
          {previewTab === "document" ? (
            <div className="space-y-1">
              <p className="text-[12px] font-medium text-[#1d1d1f]">Live document actions</p>
              <p className="text-[11px] text-[#4c4c50]">Current source: {stageFileName}</p>
              {documentEvents.length > 0 ? (
                <div className="max-h-32 space-y-1 overflow-y-auto pr-1">
                  {documentEvents.map((event) => (
                    <p key={`doc-${event.event_id}`} className="text-[11px] text-[#4c4c50]">
                      {event.title}
                    </p>
                  ))}
                </div>
              ) : (
                <p className="text-[11px] text-[#6e6e73]">No document actions in this run yet.</p>
              )}
            </div>
          ) : null}
          {previewTab === "email" ? (
            <div className="space-y-1">
              <p className="text-[12px] font-medium text-[#1d1d1f]">Live email actions</p>
              {emailEvents.length > 0 ? (
                <div className="max-h-32 space-y-1 overflow-y-auto pr-1">
                  {emailEvents.map((event) => (
                    <p key={`email-${event.event_id}`} className="text-[11px] text-[#4c4c50]">
                      {event.title}
                    </p>
                  ))}
                </div>
              ) : (
                <p className="text-[11px] text-[#6e6e73]">No email actions in this run yet.</p>
              )}
            </div>
          ) : null}
          {previewTab === "system" ? (
            <div className="space-y-1">
              <p className="text-[12px] font-medium text-[#1d1d1f]">System session view</p>
              <p className="text-[11px] text-[#4c4c50]">
                Active focus: {activeTab} | Total events: {orderedEvents.length}
              </p>
              {systemEvents.length > 0 ? (
                <div className="max-h-32 space-y-1 overflow-y-auto pr-1">
                  {systemEvents.map((event) => (
                    <p key={`system-${event.event_id}`} className="text-[11px] text-[#4c4c50]">
                      {event.title}
                    </p>
                  ))}
                </div>
              ) : (
                <p className="text-[11px] text-[#6e6e73]">No system events in this run yet.</p>
              )}
            </div>
          ) : null}
        </div>
      </div>

      {!streaming ? (
        <>
          <div className="mb-3 rounded-2xl border border-black/[0.06] bg-white/85 px-3 py-2">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-[11px] text-[#6e6e73]">
                Step {safeCursor + 1} of {orderedEvents.length}
              </span>
              <span className="text-[11px] text-[#6e6e73]">{progressPercent}%</span>
            </div>
            <input
              type="range"
              min={0}
              max={Math.max(orderedEvents.length - 1, 0)}
              value={safeCursor}
              onChange={(event) => {
                setCursor(Number(event.target.value));
                setIsPlaying(false);
              }}
              className="w-full accent-[#2f2f34]"
            />
          </div>

          <div className="mb-3 rounded-2xl border border-black/[0.06] bg-white/90 p-3">
            <div className="mb-1 flex items-center gap-2 text-[12px] text-[#6e6e73]">
              Current scene
            </div>

            {activeEvent ? (
              <div className="flex items-start gap-3">
                <span className="mt-0.5 inline-flex h-7 w-7 items-center justify-center rounded-full border border-black/[0.08] bg-[#f3f3f5]">
                  <ActiveIcon className={`h-3.5 w-3.5 ${activeStyle.accent}`} />
                </span>
                <div className="min-w-0">
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <p className="text-[14px] font-semibold text-[#1d1d1f]">{activeEvent.title}</p>
                    <span className="rounded-full border border-black/[0.08] bg-[#fafafc] px-2 py-0.5 text-[10px] uppercase tracking-[0.08em] text-[#6e6e73]">
                      {activeStyle.label}
                    </span>
                  </div>
                  <p className="text-[12px] leading-relaxed text-[#4c4c50]">
                    {sceneText || activeEvent.detail || "Processing..."}
                  </p>
                </div>
              </div>
            ) : null}
          </div>

          <div className="mb-2 overflow-x-auto pb-1">
            <div className="inline-flex min-w-full gap-2">
              {filmstripEvents.map(({ event, index }) => {
                const isActive = index === safeCursor;
                return (
                  <button
                    key={`${event.event_id}-chip`}
                    type="button"
                    onClick={() => {
                      setCursor(index);
                      setIsPlaying(false);
                      onJumpToEvent?.(event);
                    }}
                    className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] transition ${
                      isActive
                        ? "border-[#1d1d1f]/25 bg-[#1d1d1f] text-white"
                        : "border-black/[0.08] bg-white/80 text-[#4c4c50] hover:bg-white"
                    }`}
                  >
                    <span className="font-semibold">{index + 1}</span>
                    <span className="max-w-[140px] truncate">{event.title}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <div ref={listRef} className="max-h-56 space-y-1.5 overflow-y-auto pr-1">
            {visibleEvents.map((event, index) => {
              const style = styleForEvent(event);
              const Icon = style.icon;
              const isActive = index === safeCursor;
              return (
                <button
                  key={event.event_id || `${event.timestamp}-${index}`}
                  type="button"
                  data-activity-active={isActive ? "true" : "false"}
                  onClick={() => {
                    setCursor(index);
                    setIsPlaying(false);
                    onJumpToEvent?.(event);
                  }}
                  className={`w-full rounded-xl border px-3 py-2 text-left transition ${
                    isActive
                      ? "border-[#1d1d1f]/20 bg-white"
                      : "border-black/[0.06] bg-white/80 hover:bg-white"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <Icon className={`h-3.5 w-3.5 shrink-0 ${style.accent}`} />
                      <p className="truncate text-[12px] font-medium text-[#1d1d1f]">{event.title}</p>
                    </div>
                    <span className="shrink-0 text-[10px] text-[#86868b]">
                      {new Date(event.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                  {event.detail ? (
                    <p className="mt-0.5 line-clamp-2 text-[11px] text-[#6e6e73]">{event.detail}</p>
                  ) : null}
                </button>
              );
            })}
          </div>
        </>
      ) : (
        <div className="rounded-2xl border border-black/[0.06] bg-white/85 px-3 py-2 text-[12px] text-[#6e6e73]">
          Live scene is pinned inside the theater. Full replay timeline appears below after execution completes.
        </div>
      )}

      {isFullscreenViewer ? (
        <div className="fixed inset-0 z-[120] bg-black/75 p-3 backdrop-blur-md md:p-6">
          <div className="mx-auto flex h-full w-full max-w-[1800px] flex-col overflow-hidden rounded-3xl border border-white/20 bg-[#090b10] p-4 shadow-2xl md:p-5">
            <div className="mb-3 flex items-center justify-between gap-3 text-white">
              <div>
                <p className="text-[11px] uppercase tracking-[0.14em] text-white/70">Agent Viewer</p>
                <p className="text-[16px] font-semibold">Fullscreen desktop</p>
                <p className="text-[11px] text-white/65">Press `Esc` to close</p>
              </div>
              <div className="inline-flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setIsFocusMode((prev) => !prev)}
                  className="inline-flex items-center gap-1 rounded-xl border border-white/20 bg-white/5 px-3 py-1.5 text-[12px] text-white/85 transition hover:bg-white/10"
                  title="Toggle focus mode"
                >
                  <Maximize2 className="h-3.5 w-3.5" />
                  {isFocusMode ? "Focus On" : "Focus Off"}
                </button>
                <button
                  type="button"
                  onClick={() => setIsFullscreenViewer(false)}
                  className="inline-flex items-center gap-1 rounded-xl border border-white/20 bg-white/5 px-3 py-1.5 text-[12px] text-white/85 transition hover:bg-white/10"
                  title="Exit fullscreen"
                >
                  <Minimize2 className="h-3.5 w-3.5" />
                  Exit
                </button>
                <button
                  type="button"
                  onClick={() => setIsFullscreenViewer(false)}
                  className="rounded-xl border border-white/20 bg-white/5 p-2 text-white/85 transition hover:bg-white/10"
                  title="Close fullscreen"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            {renderDesktopViewer({ fullscreen: true })}

            {!isFocusMode ? (
              <div className="mt-3 flex min-h-0 flex-1 gap-3 overflow-hidden">
                <div className="min-h-0 flex-1 overflow-y-auto rounded-2xl border border-white/10 bg-white/[0.03] p-3">
                  <p className="mb-2 text-[12px] font-medium text-white/90">Current scene</p>
                  <p className="text-[13px] text-white/85">{activeEvent?.title || "No active scene"}</p>
                  <p className="mt-1 text-[12px] text-white/70">{sceneText || activeEvent?.detail || ""}</p>
                </div>
                <div className="min-h-0 w-[340px] overflow-y-auto rounded-2xl border border-white/10 bg-white/[0.03] p-3">
                  <p className="mb-2 text-[12px] font-medium text-white/90">Live timeline</p>
                  <div className="space-y-1.5">
                    {visibleEvents.map((event, index) => (
                      <button
                        key={`fullscreen-row-${event.event_id || index}`}
                        type="button"
                        onClick={() => {
                          setCursor(index);
                          setIsPlaying(false);
                          onJumpToEvent?.(event);
                        }}
                        className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-2 text-left text-white/90 transition hover:bg-white/[0.08]"
                      >
                        <p className="truncate text-[12px] font-medium">{event.title}</p>
                        {event.detail ? (
                          <p className="mt-0.5 line-clamp-2 text-[11px] text-white/70">{event.detail}</p>
                        ) : null}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
