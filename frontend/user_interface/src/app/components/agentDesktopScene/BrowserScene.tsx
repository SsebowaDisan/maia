import React, { useEffect, useMemo, useRef, useState } from "react";
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
  HighlightOverlay,
  OpenedPagesRail,
  TargetFocusRing,
  VerifierConflictBadge,
  ZoomBadge,
} from "./browser_scene_panels";
import { useBrowserPageQueue } from "./browser_scene_page_queue";
import { useRoadmapTransition } from "./browser_scene_roadmap_transition";
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
  highlightRegions: HighlightRegion[];
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
  narration?: string | null;
  roadmapSteps?: Array<{ toolId: string; title: string; whyThisStep: string }>;
  roadmapActiveIndex?: number;
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
  highlightRegions,
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
  narration = null,
  roadmapSteps = [],
  roadmapActiveIndex = -1,
}: BrowserSceneProps) {
  const [snapshotErrored, setSnapshotErrored] = useState(false);
  const statusChipLabel = blockedSignal
    ? "Needs attention"
    : readingMode
      ? "Reading"
      : action === "navigate"
        ? "Navigating"
        : action === "scroll"
          ? "Scanning"
          : action === "extract"
        ? "Extracting"
        : "";
  const normalizedRenderQuality = String(renderQuality || "").trim().toLowerCase();
  const lowQualitySignal =
    normalizedRenderQuality === "low" ||
    normalizedRenderQuality === "blocked" ||
    normalizedRenderQuality === "none" ||
    normalizedRenderQuality === "empty";
  const { dedupedOpenedPages, activePageUrl, setSelectedPageUrl } = useBrowserPageQueue({
    browserUrl,
    openedPages,
    pageIndex,
  });
  const surfaceHint = (findQuery || actionTargetLabel || activeDetail || "").slice(0, 180);
  const proxyPreviewUrl = useMemo(() => {
    const source = String(activePageUrl || "").trim();
    if (!source || (!source.startsWith("http://") && !source.startsWith("https://"))) {
      return "";
    }
    const params = new URLSearchParams();
    params.set("url", source);
    if (surfaceHint) {
      params.set("highlight", surfaceHint);
      params.set("claim", surfaceHint);
      params.set("question", surfaceHint);
    }
    params.set("viewport", "desktop");
    return `/api/web/preview?${params.toString()}`;
  }, [activePageUrl, surfaceHint]);
  const preferPreviewProxy =
    Boolean(proxyPreviewUrl) &&
    (blockedSignal ||
      lowQualitySignal ||
      !snapshotUrl ||
      action === "navigate" ||
      action === "scroll" ||
      action === "extract");
  const [snapshotReady, setSnapshotReady] = useState(false);
  const [crossFadeUrl, setCrossFadeUrl] = useState<string>("");
  const [proxyLoaded, setProxyLoaded] = useState(false);
  const prevSnapshotUrlRef = useRef<string>(snapshotUrl);
  const showSnapshotPrimary = Boolean(snapshotUrl) && !snapshotErrored && !preferPreviewProxy;
  const showProxyPreview = Boolean(proxyPreviewUrl) && (preferPreviewProxy || !showSnapshotPrimary);
  useEffect(() => {
    if (!snapshotUrl || snapshotUrl === prevSnapshotUrlRef.current) return;
    if (prevSnapshotUrlRef.current) setCrossFadeUrl(prevSnapshotUrlRef.current);
    setSnapshotReady(false);
    setSnapshotErrored(false);
  }, [snapshotUrl]);
  const handleSnapshotLoad = () => {
    setSnapshotReady(true);
    prevSnapshotUrlRef.current = snapshotUrl;
    setTimeout(() => setCrossFadeUrl(""), 400);
  };
  useEffect(() => {
    setProxyLoaded(false);
  }, [proxyPreviewUrl]);
  const [scrollOffset, setScrollOffset] = useState(0);
  const [syntheticScrollPercent, setSyntheticScrollPercent] = useState<number | null>(null);
  const scrollTargetRef = useRef(0);
  const scrollRafRef = useRef<number | null>(null);
  const syntheticRafRef = useRef<number | null>(null);
  const syntheticTickRef = useRef(0);
  const effectiveScrollPercent = scrollPercent ?? syntheticScrollPercent;

  useEffect(() => {
    if (effectiveScrollPercent === null) {
      return;
    }
    scrollTargetRef.current = Math.max(-14, Math.min(14, ((50 - effectiveScrollPercent) / 50) * 10));
  }, [effectiveScrollPercent]);
  useEffect(() => {
    if (scrollPercent !== null) {
      setSyntheticScrollPercent(null);
      if (syntheticRafRef.current != null) {
        cancelAnimationFrame(syntheticRafRef.current);
        syntheticRafRef.current = null;
      }
      return;
    }
    const shouldSimulate =
      action === "scroll" ||
      action === "navigate" ||
      action === "extract" ||
      action === "verify" ||
      readingMode;
    if (!shouldSimulate) {
      setSyntheticScrollPercent(null);
      if (syntheticRafRef.current != null) {
        cancelAnimationFrame(syntheticRafRef.current);
        syntheticRafRef.current = null;
      }
      return;
    }
    const animate = () => {
      syntheticTickRef.current = (syntheticTickRef.current + 0.55) % 100;
      setSyntheticScrollPercent(syntheticTickRef.current);
      syntheticRafRef.current = requestAnimationFrame(animate);
    };
    syntheticRafRef.current = requestAnimationFrame(animate);
    return () => {
      if (syntheticRafRef.current != null) {
        cancelAnimationFrame(syntheticRafRef.current);
        syntheticRafRef.current = null;
      }
    };
  }, [action, readingMode, scrollPercent]);
  const showOverlayCursor = !showSnapshotPrimary;
  const roadmapVisible = useRoadmapTransition({
    roadmapStepCount: roadmapSteps.length,
    roadmapActiveIndex,
    activeEventType,
  });
  useEffect(() => {
    const animate = () => {
      setScrollOffset((previous) => {
        const delta = scrollTargetRef.current - previous;
        if (Math.abs(delta) < 0.08) {
          return scrollTargetRef.current;
        }
        return previous + delta * 0.16;
      });
      scrollRafRef.current = requestAnimationFrame(animate);
    };
    scrollRafRef.current = requestAnimationFrame(animate);
    return () => {
      if (scrollRafRef.current != null) {
        cancelAnimationFrame(scrollRafRef.current);
        scrollRafRef.current = null;
      }
    };
  }, []);
  return (
    <div className="absolute inset-0 flex flex-col bg-[#0d1118] text-white/90">
      <div className="flex items-center gap-2 border-b border-white/10 px-3 py-2">
        <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
        <span className="h-2.5 w-2.5 rounded-full bg-[#ffbd2e]" />
        <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
        <div className="ml-2 flex-1 truncate rounded-full border border-white/15 bg-white/5 px-3 py-1 text-[11px] text-white/85">
          {activePageUrl || "Searching the web and opening result pages..."}
        </div>
        {statusChipLabel ? (
          <span className="rounded-full border border-white/25 bg-white/10 px-2 py-0.5 text-[10px] text-white/85">
            {statusChipLabel}
          </span>
        ) : null}
      </div>
      {showSnapshotPrimary ? (
        <div className="relative flex-1 overflow-hidden bg-white">
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
              className="absolute inset-0 h-full w-full object-cover"
            />
          ) : null}
          <img
            src={snapshotUrl}
            alt="Live browser capture"
            className={`h-full w-full object-cover ${snapshotReady ? "opacity-100" : "opacity-0"}`}
            style={{
              transform: `translateY(${scrollOffset}px)`,
              transition: "opacity 320ms ease-in-out",
            }}
            onLoad={handleSnapshotLoad}
            onError={() => {
              setSnapshotReady(false);
              setSnapshotErrored(true);
              onSnapshotError?.();
            }}
          />
          {/* Slim scroll rail — only shown when scroll position is known */}
          {effectiveScrollPercent !== null ? (
            <div className="pointer-events-none absolute right-0 top-0 bottom-0 w-[3px] z-10">
              <div className="absolute inset-0 bg-black/[0.06]" />
              <div
                className="absolute inset-x-0 rounded-full bg-black/30 transition-all duration-300"
                style={{ height: "16%", top: `${Math.max(0, Math.min(84, effectiveScrollPercent))}%` }}
              />
            </div>
          ) : null}
          <VerifierConflictBadge
            verifierConflict={verifierConflict}
            verifierConflictReason={verifierConflictReason}
            verifierRecheckRequired={verifierRecheckRequired}
            zoomEscalationRequested={zoomEscalationRequested}
          />
          <HighlightOverlay highlightRegions={highlightRegions} keyPrefix="browser-image" />
          <TargetFocusRing targetRegion={targetRegion} />
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
              <GhostCursor cursorX={cursorX} cursorY={cursorY} isClick={isClickEvent} />
              <ClickRipple ripples={clickRipples} />
            </>
          ) : null}
          <ThoughtBubble text={narration} />
        </div>
      ) : showProxyPreview || canRenderLiveUrl ? (
        <div className="relative flex-1 bg-white">
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
            src={proxyPreviewUrl || activePageUrl}
            title="Live website preview"
            className="h-full w-full border-0"
            sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
            referrerPolicy="no-referrer-when-downgrade"
            onLoad={() => setProxyLoaded(true)}
          />
          {effectiveScrollPercent !== null ? (
            <div className="pointer-events-none absolute right-0 top-0 bottom-0 w-[3px] z-10">
              <div className="absolute inset-0 bg-black/[0.06]" />
              <div
                className="absolute inset-x-0 rounded-full bg-black/30 transition-all duration-300"
                style={{ height: "16%", top: `${Math.max(0, Math.min(84, effectiveScrollPercent))}%` }}
              />
            </div>
          ) : null}
          <VerifierConflictBadge
            verifierConflict={verifierConflict}
            verifierConflictReason={verifierConflictReason}
            verifierRecheckRequired={verifierRecheckRequired}
            zoomEscalationRequested={zoomEscalationRequested}
          />
          <HighlightOverlay highlightRegions={highlightRegions} keyPrefix="browser-iframe" />
          <TargetFocusRing targetRegion={targetRegion} />
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
          <GhostCursor cursorX={cursorX} cursorY={cursorY} isClick={isClickEvent} />
          <ClickRipple ripples={clickRipples} />
          <ThoughtBubble text={narration} />
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
          <p className="text-[13px] font-semibold text-white">{activeTitle || "Browser scene"}</p>
          <p className="text-[12px] text-white/80">
            {sceneText || activeDetail || "Inspecting page content and extracting evidence..."}
          </p>
          <div className="space-y-2">
            <div className="h-2 w-[92%] rounded-full bg-white/20" />
            <div className="h-2 w-[84%] rounded-full bg-white/15" />
            <div className="h-2 w-[88%] rounded-full bg-white/20" />
            <div className="h-2 w-[63%] rounded-full bg-white/15" />
          </div>
          {showFindOverlay ? (
            <div className="rounded-lg border border-white/20 bg-white/10 px-2.5 py-2 text-[11px] text-white/90">
              <p className="font-semibold">
                Find: {findQuery || dedupedBrowserKeywords.slice(0, 2).join(" ")}
              </p>
              {dedupedBrowserKeywords.length ? (
                <p className="mt-0.5 text-white/75">Terms: {dedupedBrowserKeywords.slice(0, 5).join(", ")}</p>
              ) : null}
            </div>
          ) : null}
          {copyPulseVisible ? (
            <div className="rounded-lg border border-white/20 bg-white/8 px-2.5 py-1.5 text-[11px] text-white/90">
              Copied: {copyPulseText}
            </div>
          ) : null}
          {snapshotUrl && snapshotReady ? (
            <img
              src={snapshotUrl}
              alt="Browser capture"
              className="absolute bottom-3 right-3 h-24 w-36 rounded-lg border border-white/20 object-contain bg-black/25"
              onError={() => { setSnapshotReady(false); onSnapshotError?.(); }}
            />
          ) : null}
        </div>
      )}
      {pageIndex !== null ? (
        <div
          className={`pointer-events-none absolute right-3 rounded-full border border-white/20 bg-black/55 px-2.5 py-1 text-[10px] text-white/85 ${
            dedupedOpenedPages.length > 1 ? "bottom-12" : "bottom-3"
          }`}
        >
          Page {Math.max(1, pageIndex)}
        </div>
      ) : null}
      <ExecutionRoadmapOverlay
        roadmapSteps={roadmapSteps}
        roadmapActiveIndex={roadmapActiveIndex}
        visible={roadmapVisible}
      />
      {dedupedOpenedPages.length > 1 ? (
        <OpenedPagesRail
          openedPages={dedupedOpenedPages}
          activePageUrl={activePageUrl}
          onSelectPage={setSelectedPageUrl}
        />
      ) : null}
    </div>
  );
}

export { BrowserScene };
