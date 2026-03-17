import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  cancelComputerUseSession,
  streamComputerUseSession,
  type ComputerUseStreamEvent,
} from "../../../api/client";
import { ClickRipple } from "./ClickRipple";
import type { ClickRippleEntry } from "./ClickRipple";
import { GhostCursor } from "./GhostCursor";
import { ThoughtBubble } from "./ThoughtBubble";
import { InteractionOverlay } from "./InteractionOverlay";
import {
  ComparePanel,
  CopyPulse,
  ExecutionRoadmapOverlay,
  FindOverlay,
  ScrollMeter,
  VerifierConflictBadge,
  ZoomBadge,
} from "./browser_scene_panels";
import { useBrowserPageQueue } from "./browser_scene_page_queue";
import { useRoadmapTransition } from "./browser_scene_roadmap_transition";
import { useBrowserSceneScrollState } from "./browser_scene_scroll_state";
import type { MergedInteractionSource } from "../agentActivityPanel/interactionSuggestionMerge";
import type { HighlightRegion, ZoomHistoryEntry } from "./types";

type BrowserSceneProps = {
  activeDetail: string;
  activeEventType: string;
  activeTitle: string;
  action: string;
  actionPhase: string;
  actionStatus: string;
  actionTargetLabel: string;
  browserUrl: string;
  blockedSignal: boolean;
  canRenderLiveUrl: boolean;
  copyPulseText: string;
  copyPulseVisible: boolean;
  dedupedBrowserKeywords: string[];
  findMatchCount: number;
  findQuery: string;
  semanticFindResults: Array<{ term: string; confidence: number }>;
  onSnapshotError?: () => void;
  readingMode: boolean;
  sceneText: string;
  scrollDirection: string;
  scrollPercent: number | null;
  targetRegion: HighlightRegion | null;
  zoomHistory: ZoomHistoryEntry[];
  zoomLevel: number | null;
  zoomReason: string;
  compareLeft: string;
  compareRight: string;
  compareVerdict: string;
  verifierConflict: boolean;
  verifierConflictReason: string;
  verifierRecheckRequired: boolean;
  zoomEscalationRequested: boolean;
  showFindOverlay: boolean;
  snapshotUrl: string;
  renderQuality: string;
  pageIndex: number | null;
  openedPages: Array<{ url: string; title: string; pageIndex: number | null; reviewed: boolean }>;
  cursorX?: number | null;
  cursorY?: number | null;
  isClickEvent?: boolean;
  clickRipples?: ClickRippleEntry[];
  cursorSource?: MergedInteractionSource;
  narration?: string | null;
  roadmapSteps?: Array<{ toolId: string; title: string; whyThisStep: string }>;
  roadmapActiveIndex?: number;
  runId?: string;
  computerUseSessionId?: string;
  computerUseTask?: string;
  computerUseModel?: string;
  computerUseMaxIterations?: number | null;
  onComputerUseCancelled?: () => void;
};

function BrowserScene({
  activeDetail,
  activeEventType,
  activeTitle,
  action,
  actionPhase,
  actionStatus,
  actionTargetLabel,
  browserUrl,
  blockedSignal,
  canRenderLiveUrl,
  copyPulseText,
  copyPulseVisible,
  dedupedBrowserKeywords,
  findMatchCount,
  findQuery,
  semanticFindResults,
  onSnapshotError,
  readingMode,
  sceneText,
  scrollDirection,
  scrollPercent,
  targetRegion,
  zoomHistory,
  zoomLevel,
  zoomReason,
  compareLeft,
  compareRight,
  compareVerdict,
  verifierConflict,
  verifierConflictReason,
  verifierRecheckRequired,
  zoomEscalationRequested,
  showFindOverlay,
  snapshotUrl,
  renderQuality,
  pageIndex,
  openedPages,
  cursorX = null,
  cursorY = null,
  isClickEvent = false,
  clickRipples = [],
  cursorSource = "none",
  narration = null,
  roadmapSteps = [],
  roadmapActiveIndex = -1,
  runId = "",
  computerUseSessionId = "",
  computerUseTask = "",
  computerUseModel = "",
  computerUseMaxIterations = null,
  onComputerUseCancelled,
}: BrowserSceneProps) {
  const normalizedAction = String(action || "").trim().toLowerCase();
  const normalizedEventType = String(activeEventType || "").trim().toLowerCase();
  const normalizedScrollDirection = String(scrollDirection || "").trim().toLowerCase();
  const actionIndicatesScroll = normalizedAction === "scroll" || normalizedAction.includes("scroll");
  const eventIndicatesScroll = normalizedEventType.includes("scroll");
  const hasDirectionalScroll = normalizedScrollDirection === "up" || normalizedScrollDirection === "down";
  const [computerUseScreenshotUrl, setComputerUseScreenshotUrl] = useState("");
  const [computerUseNarration, setComputerUseNarration] = useState("");
  const [computerUseStreamStatus, setComputerUseStreamStatus] = useState<
    "idle" | "streaming" | "done" | "max_iterations" | "error"
  >("idle");
  const [computerUseIteration, setComputerUseIteration] = useState<number | null>(null);
  const [computerUseError, setComputerUseError] = useState("");
  const [computerUseStreamUrl, setComputerUseStreamUrl] = useState("");
  const [computerUseCancelling, setComputerUseCancelling] = useState(false);
  const computerUseCleanupRef = useRef<(() => void) | null>(null);
  const computerUseStreamKeyRef = useRef("");
  useEffect(
    () => () => {
      if (computerUseCleanupRef.current) {
        computerUseCleanupRef.current();
        computerUseCleanupRef.current = null;
      }
    },
    [],
  );
  useEffect(() => {
    const sessionId = String(computerUseSessionId || "").trim();
    const task = String(computerUseTask || "").trim();
    if (!sessionId || !task) {
      if (computerUseCleanupRef.current) {
        computerUseCleanupRef.current();
        computerUseCleanupRef.current = null;
      }
      computerUseStreamKeyRef.current = "";
      setComputerUseScreenshotUrl("");
      setComputerUseNarration("");
      setComputerUseStreamStatus("idle");
      setComputerUseIteration(null);
      setComputerUseError("");
      setComputerUseStreamUrl("");
      return;
    }
    const streamKey = [
      sessionId,
      task,
      String(computerUseModel || ""),
      String(computerUseMaxIterations ?? ""),
      String(runId || ""),
    ].join("::");
    if (computerUseStreamKeyRef.current === streamKey) {
      return;
    }
    if (computerUseCleanupRef.current) {
      computerUseCleanupRef.current();
      computerUseCleanupRef.current = null;
    }
    computerUseStreamKeyRef.current = streamKey;
    setComputerUseScreenshotUrl("");
    setComputerUseNarration("");
    setComputerUseStreamStatus("streaming");
    setComputerUseIteration(null);
    setComputerUseError("");
    setComputerUseStreamUrl("");
    computerUseCleanupRef.current = streamComputerUseSession(sessionId, {
      task,
      model: String(computerUseModel || "").trim() || undefined,
      maxIterations:
        typeof computerUseMaxIterations === "number" && Number.isFinite(computerUseMaxIterations)
          ? computerUseMaxIterations
          : undefined,
      runId: String(runId || "").trim() || undefined,
      onEvent: (event: ComputerUseStreamEvent) => {
        const eventType = String(event.event_type || "").trim().toLowerCase();
        const iterationRaw = Number(event.iteration ?? Number.NaN);
        if (Number.isFinite(iterationRaw) && iterationRaw > 0) {
          setComputerUseIteration(Math.round(iterationRaw));
        }
        if (eventType === "screenshot") {
          const screenshotB64 = String(event.screenshot_b64 || "").trim();
          if (screenshotB64) {
            setComputerUseScreenshotUrl(`data:image/png;base64,${screenshotB64}`);
          }
          const streamUrl = String(event.url || "").trim();
          if (streamUrl) {
            setComputerUseStreamUrl(streamUrl);
          }
          return;
        }
        if (eventType === "text") {
          const nextText = String(event.text || "").trim();
          if (!nextText) {
            return;
          }
          setComputerUseNarration((previous) => {
            const combined = previous ? `${previous}\n${nextText}` : nextText;
            return combined.length > 480 ? combined.slice(combined.length - 480) : combined;
          });
          return;
        }
        if (eventType === "action") {
          const actionLabel = String(event.action || "").trim();
          if (actionLabel) {
            setComputerUseNarration(`Running action: ${actionLabel}`);
          }
          return;
        }
        if (eventType === "done") {
          setComputerUseStreamStatus("done");
          const streamUrl = String(event.url || "").trim();
          if (streamUrl) {
            setComputerUseStreamUrl(streamUrl);
          }
          return;
        }
        if (eventType === "max_iterations") {
          setComputerUseStreamStatus("max_iterations");
          return;
        }
        if (eventType === "error") {
          setComputerUseStreamStatus("error");
          setComputerUseError(String(event.detail || "Computer Use stream failed.").trim());
        }
      },
      onDone: () => {
        setComputerUseStreamStatus((previous) => (previous === "streaming" ? "done" : previous));
      },
      onError: (error) => {
        setComputerUseStreamStatus("error");
        setComputerUseError(String(error?.message || "Computer Use stream disconnected."));
      },
    });
    return () => {
      if (computerUseCleanupRef.current) {
        computerUseCleanupRef.current();
        computerUseCleanupRef.current = null;
      }
    };
  }, [computerUseMaxIterations, computerUseModel, computerUseSessionId, computerUseTask, runId]);
  const streamStatusChip =
    computerUseStreamStatus === "streaming"
      ? `Computer Use${computerUseIteration ? ` · Step ${computerUseIteration}` : ""}`
      : computerUseStreamStatus === "done"
        ? "Computer Use done"
        : computerUseStreamStatus === "max_iterations"
          ? "Computer Use limit reached"
          : computerUseStreamStatus === "error"
            ? "Computer Use error"
            : "";
  const sceneSnapshotUrl = computerUseScreenshotUrl || snapshotUrl;
  const sceneNarration = computerUseNarration || narration;
  const handleCancelComputerUse = async () => {
    const sessionId = String(computerUseSessionId || "").trim();
    if (!sessionId || computerUseCancelling) {
      return;
    }
    setComputerUseCancelling(true);
    try {
      await cancelComputerUseSession(sessionId);
      if (computerUseCleanupRef.current) {
        computerUseCleanupRef.current();
        computerUseCleanupRef.current = null;
      }
      computerUseStreamKeyRef.current = "";
      setComputerUseStreamStatus("done");
      setComputerUseNarration((previous) =>
        previous || "Computer Use session stopped.",
      );
      onComputerUseCancelled?.();
    } catch (error) {
      const message = String(
        (error as { message?: string } | undefined)?.message || error || "Failed to stop session.",
      ).trim();
      setComputerUseStreamStatus("error");
      setComputerUseError(message);
    } finally {
      setComputerUseCancelling(false);
    }
  };
  const [snapshotErrored, setSnapshotErrored] = useState(false);
  const statusChipLabel = blockedSignal
    ? "Needs attention"
      : streamStatusChip
        ? streamStatusChip
      : readingMode
        ? "Reading"
        : action === "navigate"
          ? "Navigating"
        : actionIndicatesScroll
          ? "Scanning"
        : action === "extract"
        ? "Extracting"
        : "";
  const { activePageUrl } = useBrowserPageQueue({
    browserUrl,
    openedPages,
    pageIndex,
  });
  const resolvedPageUrl = computerUseStreamUrl || activePageUrl;
  const previewHint = (findQuery || actionTargetLabel || "").slice(0, 180);
  const shouldAnnotatePreview = showFindOverlay || normalizedAction === "find";
  const proxyPreviewUrl = useMemo(() => {
    const source = String(resolvedPageUrl || "").trim();
    if (!source || (!source.startsWith("http://") && !source.startsWith("https://"))) {
      return "";
    }
    const params = new URLSearchParams();
    params.set("url", source);
    if (shouldAnnotatePreview && previewHint) {
      params.set("highlight", previewHint);
      params.set("claim", previewHint);
      params.set("question", previewHint);
    }
    params.set("viewport", "desktop");
    params.set("highlight_strategy", "heuristic");
    return `/api/web/preview?${params.toString()}`;
  }, [previewHint, resolvedPageUrl, shouldAnnotatePreview]);
  const shouldUseProxyPreview =
    Boolean(proxyPreviewUrl) &&
    (blockedSignal ||
      shouldAnnotatePreview ||
      !canRenderLiveUrl);
  const preferPreviewProxy =
    shouldUseProxyPreview &&
    (!sceneSnapshotUrl || snapshotErrored);
  const [snapshotReady, setSnapshotReady] = useState(false);
  const [crossFadeUrl, setCrossFadeUrl] = useState<string>("");
  const [proxyLoaded, setProxyLoaded] = useState(false);
  const [frameScrollPercent, setFrameScrollPercent] = useState<number | null>(null);
  const prevSnapshotUrlRef = useRef<string>(sceneSnapshotUrl);
  const frameRef = useRef<HTMLIFrameElement | null>(null);
  const frameScrollObserverCleanupRef = useRef<(() => void) | null>(null);
  const showSnapshotPrimary = Boolean(sceneSnapshotUrl) && !snapshotErrored && !preferPreviewProxy;
  const frameUrl = useMemo(() => {
    if (shouldUseProxyPreview && proxyPreviewUrl) {
      return proxyPreviewUrl;
    }
    return resolvedPageUrl;
  }, [proxyPreviewUrl, resolvedPageUrl, shouldUseProxyPreview]);
  const showFramePreview = Boolean(frameUrl);
  useEffect(() => {
    if (!sceneSnapshotUrl || sceneSnapshotUrl === prevSnapshotUrlRef.current) return;
    if (prevSnapshotUrlRef.current) setCrossFadeUrl(prevSnapshotUrlRef.current);
    setSnapshotReady(false);
    setSnapshotErrored(false);
  }, [sceneSnapshotUrl]);
  const handleSnapshotLoad = () => {
    setSnapshotReady(true);
    prevSnapshotUrlRef.current = sceneSnapshotUrl;
    setTimeout(() => setCrossFadeUrl(""), 400);
  };
  useEffect(() => {
    setProxyLoaded(false);
    setFrameScrollPercent(null);
    if (frameScrollObserverCleanupRef.current) {
      frameScrollObserverCleanupRef.current();
      frameScrollObserverCleanupRef.current = null;
    }
  }, [frameUrl]);
  useEffect(
    () => () => {
      if (frameScrollObserverCleanupRef.current) {
        frameScrollObserverCleanupRef.current();
        frameScrollObserverCleanupRef.current = null;
      }
    },
    [],
  );
  const bindFrameScrollObserver = () => {
    if (frameScrollObserverCleanupRef.current) {
      frameScrollObserverCleanupRef.current();
      frameScrollObserverCleanupRef.current = null;
    }
    const frame = frameRef.current;
    if (!frame) {
      return;
    }
    try {
      const computePercent = () => {
        try {
          const liveFrame = frameRef.current;
          const frameWindow = liveFrame?.contentWindow;
          const frameDocument = frameWindow?.document;
          if (!frameWindow || !frameDocument) {
            setFrameScrollPercent(null);
            return;
          }
          const doc = frameDocument.documentElement;
          const body = frameDocument.body;
          const scrollTop = Number(frameWindow.scrollY || doc?.scrollTop || body?.scrollTop || 0);
          const scrollHeight = Number(doc?.scrollHeight || body?.scrollHeight || 0);
          const viewportHeight = Number(frameWindow.innerHeight || doc?.clientHeight || 0);
          const maxScrollable = Math.max(0, scrollHeight - viewportHeight);
          if (maxScrollable <= 0) {
            setFrameScrollPercent(0);
            return;
          }
          const nextPercent = Math.max(0, Math.min(100, (scrollTop / maxScrollable) * 100));
          setFrameScrollPercent(nextPercent);
        } catch {
          setFrameScrollPercent(null);
        }
      };
      const frameWindow = frame.contentWindow;
      if (!frameWindow) {
        return;
      }
      frameWindow.addEventListener("scroll", computePercent, { passive: true });
      frameWindow.addEventListener("hashchange", computePercent);
      frameWindow.addEventListener("popstate", computePercent);
      frame.addEventListener("load", computePercent);
      computePercent();
      const syncTimer = window.setTimeout(computePercent, 150);
      const syncInterval = window.setInterval(computePercent, 900);
      frameScrollObserverCleanupRef.current = () => {
        frameWindow.removeEventListener("scroll", computePercent);
        frameWindow.removeEventListener("hashchange", computePercent);
        frameWindow.removeEventListener("popstate", computePercent);
        frame.removeEventListener("load", computePercent);
        window.clearTimeout(syncTimer);
        window.clearInterval(syncInterval);
      };
    } catch {
      setFrameScrollPercent(null);
    }
  };
  const canProgrammaticallyScrollFrame = showFramePreview && shouldUseProxyPreview && !showSnapshotPrimary;
  const resolvedScrollPercent = canProgrammaticallyScrollFrame
    ? frameScrollPercent ?? scrollPercent
    : scrollPercent;
  const scrollFrameToPercent = (percent: number): boolean => {
    if (!canProgrammaticallyScrollFrame) {
      return false;
    }
    const frame = frameRef.current;
    if (!frame) {
      return false;
    }
    try {
      const frameWindow = frame.contentWindow;
      const frameDocument = frameWindow?.document;
      if (!frameWindow || !frameDocument) {
        return false;
      }
      const doc = frameDocument.documentElement;
      const body = frameDocument.body;
      const scrollHeight = Number(doc?.scrollHeight || body?.scrollHeight || 0);
      const viewportHeight = Number(frameWindow.innerHeight || doc?.clientHeight || 0);
      const maxScrollable = Math.max(0, scrollHeight - viewportHeight);
      if (maxScrollable <= 0) {
        return false;
      }
      const nextPercent = Math.max(0, Math.min(100, Number(percent)));
      frameWindow.scrollTo({
        top: (nextPercent / 100) * maxScrollable,
        behavior: "smooth",
      });
      setFrameScrollPercent(nextPercent);
      return true;
    } catch {
      return false;
    }
  };
  const { navigationHint, effectiveScrollPercent, handleScrollSelect } = useBrowserSceneScrollState({
    activePageUrl: resolvedPageUrl,
    actionIndicatesScroll,
    eventIndicatesScroll,
    hasDirectionalScroll,
    normalizedAction,
    normalizedScrollDirection,
    readingMode,
    scrollPercent: resolvedScrollPercent,
    allowSyntheticScroll: false,
    canSelect: canProgrammaticallyScrollFrame,
    onSelectPercent: scrollFrameToPercent,
  });
  const showOverlayCursor = cursorX !== null && cursorY !== null;
  const viewportScrollOffsetPx = 0;
  const roadmapVisible = useRoadmapTransition({
    roadmapStepCount: roadmapSteps.length,
    roadmapActiveIndex,
    activeEventType,
  });
  const scrollControls = (
    <>
      <ScrollMeter
        scrollPercent={effectiveScrollPercent}
        onSelect={canProgrammaticallyScrollFrame ? handleScrollSelect : undefined}
      />
    </>
  );
  return (
    <div className="absolute inset-0 bg-[radial-gradient(circle_at_12%_8%,rgba(168,216,255,0.92),rgba(122,176,244,0.72)_40%,rgba(98,148,232,0.9)_100%)] p-9 text-[#1d1d1f]">
      <div className="relative mx-auto flex h-full w-full max-w-[840px] flex-col overflow-hidden rounded-[20px] border border-black/[0.1] bg-[#fcfcfd] shadow-[0_26px_58px_-42px_rgba(0,0,0,0.52)]">
      <div className="relative z-40 flex items-center gap-2 border-b border-black/[0.08] bg-[#fcfcfd] px-3 py-2.5">
        <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
        <span className="h-2.5 w-2.5 rounded-full bg-[#ffbd2e]" />
        <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
        <div className="ml-2 flex-1 truncate rounded-full border border-black/[0.08] bg-[#f7f8fb] px-3 py-1 text-[11px] text-[#2b3140]">
          {resolvedPageUrl || "Searching the web and opening result pages..."}
        </div>
        {statusChipLabel ? (
          <span className="rounded-full border border-black/[0.1] bg-[#f7f8fb] px-2 py-0.5 text-[10px] text-[#4a4f5c]">
            {statusChipLabel}
          </span>
        ) : null}
        {computerUseSessionId ? (
          <button
            type="button"
            onClick={() => {
              void handleCancelComputerUse();
            }}
            disabled={computerUseCancelling}
            className="rounded-full border border-[#fca5a5]/70 bg-[#fff5f5] px-2.5 py-0.5 text-[10px] font-semibold text-[#b42318] transition hover:bg-[#ffeaea] disabled:opacity-60"
          >
            {computerUseCancelling ? "Stopping..." : "Stop"}
          </button>
        ) : null}
      </div>
      {computerUseError ? (
        <div className="pointer-events-none absolute left-3 top-12 z-30 rounded-full border border-[#7f1d1d]/40 bg-[#7f1d1d]/88 px-2.5 py-1 text-[10px] text-white/95 backdrop-blur-sm">
          {computerUseError}
        </div>
      ) : null}
      {navigationHint ? (
        <div className="pointer-events-none absolute right-3 top-12 z-30 rounded-full border border-white/20 bg-black/58 px-2.5 py-1 text-[10px] text-white/90 backdrop-blur-sm">
          {navigationHint}
        </div>
      ) : null}
      {showSnapshotPrimary ? (
        <div className="relative flex-1 overflow-hidden bg-[#f5f7fb]">
          {/* Skeleton shown while loading and no cross-fade underlay is available */}
          {!snapshotReady && !crossFadeUrl ? (
            <div className="absolute inset-0 flex items-center justify-center bg-[#f5f5f7]">
              <div className="space-y-2.5 w-[55%]">
                <div className="h-2 rounded-full bg-black/10 animate-pulse" />
                <div className="h-2 rounded-full bg-black/8 animate-pulse w-[82%]" />
                <div className="h-2 rounded-full bg-black/10 animate-pulse w-[90%]" />
              </div>
            </div>
          ) : null}
          {/* Previous snapshot underlay — stays fully visible while next image loads,
              giving a smooth cross-dissolve rather than a skeleton flash. */}
          {crossFadeUrl && !snapshotReady ? (
            <img
              src={crossFadeUrl}
              alt=""
              aria-hidden="true"
              className="absolute inset-0 h-full w-full object-contain object-top bg-transparent"
              style={{
                transform: `translate3d(0, ${viewportScrollOffsetPx}px, 0)`,
                transition: "transform 220ms ease-out",
              }}
            />
          ) : null}
          <img
            src={sceneSnapshotUrl}
            alt="Live browser capture"
            className={`absolute inset-0 h-full w-full object-contain object-top bg-transparent ${snapshotReady ? "opacity-100" : "opacity-0"}`}
            style={{
              transition: "opacity 320ms ease-in-out, transform 220ms ease-out",
              transform: `translate3d(0, ${viewportScrollOffsetPx}px, 0)`,
            }}
            onLoad={handleSnapshotLoad}
            onError={() => {
              setSnapshotReady(false);
              setSnapshotErrored(true);
              onSnapshotError?.();
            }}
          />
          {scrollControls}
          <VerifierConflictBadge
            verifierConflict={verifierConflict}
            verifierConflictReason={verifierConflictReason}
            verifierRecheckRequired={verifierRecheckRequired}
            zoomEscalationRequested={zoomEscalationRequested}
          />
          <ZoomBadge zoomLevel={zoomLevel} zoomReason={zoomReason} />
          <ComparePanel
            compareLeft={compareLeft}
            compareRight={compareRight}
            compareVerdict={compareVerdict}
          />
          <InteractionOverlay
            sceneSurface="website"
            activeEventType={activeEventType}
            activeDetail={activeDetail}
            scrollDirection={scrollDirection}
            action={action}
            actionPhase={actionPhase}
            actionStatus={actionStatus}
            actionTargetLabel={actionTargetLabel}
          />
          {showFindOverlay ? (
            <FindOverlay
              dedupedBrowserKeywords={dedupedBrowserKeywords}
              findMatchCount={findMatchCount}
              findQuery={findQuery}
              semanticFindResults={semanticFindResults}
            />
          ) : null}
          <CopyPulse copyPulseText={copyPulseText} copyPulseVisible={copyPulseVisible} />
          {showOverlayCursor ? (
            <>
              <GhostCursor
                cursorX={cursorX}
                cursorY={cursorY}
                isClick={isClickEvent}
                advisory={cursorSource === "suggested"}
              />
              <ClickRipple ripples={clickRipples} />
            </>
          ) : null}
          <ThoughtBubble text={sceneNarration} />
        </div>
      ) : showFramePreview ? (
        <div className="relative flex-1 overflow-hidden bg-[#f5f7fb]">
          {!proxyLoaded ? (
            <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-[#f5f5f7]">
              <div className="space-y-2.5 w-[52%]">
                <div className="h-2 rounded-full bg-black/10 animate-pulse" />
                <div className="h-2 rounded-full bg-black/8 animate-pulse w-[80%]" />
                <div className="h-2 rounded-full bg-black/10 animate-pulse w-[88%]" />
              </div>
            </div>
          ) : null}
          <iframe
            ref={frameRef}
            src={frameUrl || resolvedPageUrl}
            title="Live website preview"
            className="absolute inset-0 h-full w-full border-0"
            style={{
              transform: `translate3d(0, ${viewportScrollOffsetPx}px, 0)`,
              transition: "transform 220ms ease-out",
            }}
            sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
            referrerPolicy="no-referrer-when-downgrade"
            onLoad={() => {
              setProxyLoaded(true);
              if (shouldUseProxyPreview) {
                bindFrameScrollObserver();
              } else {
                setFrameScrollPercent(null);
              }
            }}
          />
          {scrollControls}
          <VerifierConflictBadge
            verifierConflict={verifierConflict}
            verifierConflictReason={verifierConflictReason}
            verifierRecheckRequired={verifierRecheckRequired}
            zoomEscalationRequested={zoomEscalationRequested}
          />
          <ZoomBadge zoomLevel={zoomLevel} zoomReason={zoomReason} />
          <ComparePanel
            compareLeft={compareLeft}
            compareRight={compareRight}
            compareVerdict={compareVerdict}
          />
          <InteractionOverlay
            sceneSurface="website"
            activeEventType={activeEventType}
            activeDetail={activeDetail}
            scrollDirection={scrollDirection}
            action={action}
            actionPhase={actionPhase}
            actionStatus={actionStatus}
            actionTargetLabel={actionTargetLabel}
          />
          {showFindOverlay ? (
            <FindOverlay
              dedupedBrowserKeywords={dedupedBrowserKeywords}
              findMatchCount={findMatchCount}
              findQuery={findQuery}
              semanticFindResults={semanticFindResults}
            />
          ) : null}
          <CopyPulse copyPulseText={copyPulseText} copyPulseVisible={copyPulseVisible} />
          <GhostCursor
            cursorX={cursorX}
            cursorY={cursorY}
            isClick={isClickEvent}
            advisory={cursorSource === "suggested"}
          />
          <ClickRipple ripples={clickRipples} />
          <ThoughtBubble text={sceneNarration} />
        </div>
      ) : (
        <div className="relative flex-1 space-y-3 p-4">
          <InteractionOverlay
            sceneSurface="website"
            activeEventType={activeEventType}
            activeDetail={activeDetail}
            scrollDirection={scrollDirection}
            action={action}
            actionPhase={actionPhase}
            actionStatus={actionStatus}
            actionTargetLabel={actionTargetLabel}
          />
          <p className="text-[13px] font-semibold text-[#1d1d1f]">{activeTitle || "Browser scene"}</p>
          <p className="text-[12px] text-[#4a4f5c]">
            {sceneText || activeDetail || "Inspecting page content and extracting evidence..."}
          </p>
          <div className="relative overflow-hidden rounded-xl border border-black/[0.08] bg-white px-3 py-3">
            <div
              className="space-y-2 transition-transform duration-200 ease-out"
              style={{ transform: `translate3d(0, ${viewportScrollOffsetPx}px, 0)` }}
            >
              <div className="h-2 w-[92%] rounded-full bg-black/12" />
              <div className="h-2 w-[84%] rounded-full bg-black/8" />
              <div className="h-2 w-[88%] rounded-full bg-black/12" />
              <div className="h-2 w-[63%] rounded-full bg-black/8" />
              <div className="h-2 w-[76%] rounded-full bg-black/10" />
              <div className="h-2 w-[68%] rounded-full bg-black/8" />
            </div>
          </div>
          {showFindOverlay ? (
            <div className="rounded-lg border border-black/[0.08] bg-white px-2.5 py-2 text-[11px] text-[#1d1d1f]">
              <p className="font-semibold">
                Find: {findQuery || dedupedBrowserKeywords.slice(0, 2).join(" ")}
              </p>
              {dedupedBrowserKeywords.length ? (
                <p className="mt-0.5 text-[#4a4f5c]">Terms: {dedupedBrowserKeywords.slice(0, 5).join(", ")}</p>
              ) : null}
            </div>
          ) : null}
          {copyPulseVisible ? (
            <div className="rounded-lg border border-black/[0.08] bg-white px-2.5 py-1.5 text-[11px] text-[#1d1d1f]">
              Copied: {copyPulseText}
            </div>
          ) : null}
          {scrollControls}
          {sceneSnapshotUrl && snapshotReady ? (
            <img
              src={sceneSnapshotUrl}
              alt="Browser capture"
              className="absolute bottom-3 right-3 h-24 w-36 rounded-lg border border-black/[0.08] object-contain bg-[#f5f7fb]"
              onError={() => { setSnapshotReady(false); onSnapshotError?.(); }}
            />
          ) : null}
          {showOverlayCursor ? (
            <>
              <GhostCursor
                cursorX={cursorX}
                cursorY={cursorY}
                isClick={isClickEvent}
                advisory={cursorSource === "suggested"}
              />
              <ClickRipple ripples={clickRipples} />
            </>
          ) : null}
        </div>
      )}
      {pageIndex !== null ? (
        <div
          className="pointer-events-none absolute right-3 bottom-3 rounded-full border border-black/[0.1] bg-white/92 px-2.5 py-1 text-[10px] text-[#4a4f5c]"
        >
          Page {Math.max(1, pageIndex)}
        </div>
      ) : null}
      <ExecutionRoadmapOverlay
        roadmapSteps={roadmapSteps}
        roadmapActiveIndex={roadmapActiveIndex}
        visible={roadmapVisible}
      />
    </div>
    </div>
  );
}

export { BrowserScene };
