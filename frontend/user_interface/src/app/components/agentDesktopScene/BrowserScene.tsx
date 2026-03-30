import React, { useMemo } from "react";
import { useRoadmapTransition } from "./browser_scene_roadmap_transition";
import { FallbackPane, FramePane, SnapshotPane } from "./browserSceneSections/panes";
import { BrowserSceneProps } from "./browserSceneSections/common";
import { useComputerUseStream } from "./browserSceneSections/useComputerUseStream";
import { useBrowserPreviewState } from "./browserSceneSections/useBrowserPreviewState";

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

  const computerUse = useComputerUseStream({
    sessionId: computerUseSessionId,
    task: computerUseTask,
    model: computerUseModel,
    maxIterations: computerUseMaxIterations,
    runId,
    onCancelled: onComputerUseCancelled,
  });

  const previewHint = (findQuery || actionTargetLabel || "").slice(0, 180);
  const shouldAnnotatePreview = showFindOverlay || normalizedAction === "find";
  const preview = useBrowserPreviewState({
    browserUrl,
    openedPages,
    pageIndex,
    snapshotUrl,
    previewHint,
    shouldAnnotatePreview,
    blockedSignal,
    canRenderLiveUrl,
    scrollPercent,
    actionIndicatesScroll,
    eventIndicatesScroll,
    hasDirectionalScroll,
    normalizedAction,
    normalizedScrollDirection,
    readingMode,
    onSnapshotError,
    computerUseScreenshotUrl: computerUse.screenshotUrl,
    computerUseStreamUrl: computerUse.streamUrl,
  });

  const streamStatusChip =
    computerUse.streamStatus === "streaming"
      ? `Computer Use${computerUse.iteration ? ` · Step ${computerUse.iteration}` : ""}`
      : computerUse.streamStatus === "done"
        ? "Computer Use done"
        : computerUse.streamStatus === "max_iterations"
          ? "Computer Use limit reached"
          : computerUse.streamStatus === "error"
            ? "Computer Use error"
            : "";
  const sceneNarration = computerUse.narration || narration;
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
  const showOverlayCursor = cursorX !== null && cursorY !== null;
  const roadmapVisible = useRoadmapTransition({
    roadmapStepCount: roadmapSteps.length,
    roadmapActiveIndex,
    activeEventType,
  });

  const overlayProps = useMemo(
    () => ({
      activeDetail,
      activeEventType,
      action,
      actionPhase,
      actionStatus,
      actionTargetLabel,
      clickRipples,
      compareLeft,
      compareRight,
      compareVerdict,
      copyPulseText,
      copyPulseVisible,
      cursorSource,
      cursorX,
      cursorY,
      dedupedBrowserKeywords,
      effectiveScrollPercent: preview.effectiveScrollPercent,
      findMatchCount,
      findQuery,
      handleScrollSelect: preview.canProgrammaticallyScrollFrame ? preview.handleScrollSelect : undefined,
      isClickEvent,
      pageIndex,
      roadmapActiveIndex,
      roadmapSteps,
      roadmapVisible,
      sceneNarration,
      semanticFindResults,
      scrollDirection,
      showFindOverlay,
      showOverlayCursor,
      verifierConflict,
      verifierConflictReason,
      verifierRecheckRequired,
      zoomEscalationRequested,
      zoomLevel,
      zoomReason,
    }),
    [
      activeDetail,
      activeEventType,
      action,
      actionPhase,
      actionStatus,
      actionTargetLabel,
      clickRipples,
      compareLeft,
      compareRight,
      compareVerdict,
      copyPulseText,
      copyPulseVisible,
      cursorSource,
      cursorX,
      cursorY,
      dedupedBrowserKeywords,
      findMatchCount,
      findQuery,
      isClickEvent,
      pageIndex,
      preview.canProgrammaticallyScrollFrame,
      preview.effectiveScrollPercent,
      preview.handleScrollSelect,
      roadmapActiveIndex,
      roadmapSteps,
      roadmapVisible,
      sceneNarration,
      semanticFindResults,
      scrollDirection,
      showFindOverlay,
      showOverlayCursor,
      verifierConflict,
      verifierConflictReason,
      verifierRecheckRequired,
      zoomEscalationRequested,
      zoomLevel,
      zoomReason,
    ],
  );

  return (
    <div className="absolute inset-0 bg-[radial-gradient(circle_at_12%_8%,rgba(168,216,255,0.92),rgba(122,176,244,0.72)_40%,rgba(98,148,232,0.9)_100%)] p-9 text-[#1d1d1f]">
      <div className="relative mx-auto flex h-full w-full max-w-[840px] flex-col overflow-hidden rounded-[20px] border border-black/[0.1] bg-[#fcfcfd] shadow-[0_26px_58px_-42px_rgba(0,0,0,0.52)]">
        <div className="relative z-40 flex items-center gap-2 border-b border-black/[0.08] bg-[#fcfcfd] px-3 py-2.5">
          <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#ffbd2e]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
          <div className="ml-2 flex-1 truncate rounded-full border border-black/[0.08] bg-[#f7f8fb] px-3 py-1 text-[11px] text-[#2b3140]">
            {preview.resolvedPageUrl || "Searching the web and opening result pages..."}
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
                void computerUse.cancel();
              }}
              disabled={computerUse.cancelling}
              className="rounded-full border border-[#fca5a5]/70 bg-[#fff5f5] px-2.5 py-0.5 text-[10px] font-semibold text-[#b42318] transition hover:bg-[#ffeaea] disabled:opacity-60"
            >
              {computerUse.cancelling ? "Stopping..." : "Stop"}
            </button>
          ) : null}
        </div>
        {computerUse.error ? (
          <div className="pointer-events-none absolute left-3 top-12 z-30 rounded-full border border-[#7f1d1d]/40 bg-[#7f1d1d]/88 px-2.5 py-1 text-[10px] text-white/95 backdrop-blur-sm">
            {computerUse.error}
          </div>
        ) : null}
        {preview.navigationHint ? (
          <div className="pointer-events-none absolute right-3 top-12 z-30 rounded-full border border-white/20 bg-black/58 px-2.5 py-1 text-[10px] text-white/90 backdrop-blur-sm">
            {preview.navigationHint}
          </div>
        ) : null}
        {preview.showSnapshotPrimary ? (
          <SnapshotPane
            {...overlayProps}
            crossFadeUrl={preview.crossFadeUrl}
            handleSnapshotLoad={preview.handleSnapshotLoad}
            sceneSnapshotUrl={preview.sceneSnapshotUrl}
            snapshotReady={preview.snapshotReady}
            viewportScrollOffsetPx={preview.viewportScrollOffsetPx}
            onSnapshotError={preview.handleSnapshotError}
          />
        ) : preview.showFramePreview ? (
          <FramePane
            {...overlayProps}
            frameRef={preview.frameRef}
            frameScale={preview.frameScale}
            frameUrl={preview.frameUrl}
            frameViewportRef={preview.frameViewportRef}
            frameVirtualHeight={preview.frameVirtualHeight}
            handleFrameLoad={preview.handleFrameLoad}
            proxyLoaded={preview.proxyLoaded}
            resolvedPageUrl={preview.resolvedPageUrl}
            viewportScrollOffsetPx={preview.viewportScrollOffsetPx}
          />
        ) : (
          <FallbackPane
            {...overlayProps}
            activeTitle={fallbackTitle}
            sceneSnapshotUrl={preview.sceneSnapshotUrl}
            sceneText={fallbackSceneText}
            onFallbackSnapshotError={preview.handleSnapshotError}
            snapshotReady={preview.snapshotReady}
            viewportScrollOffsetPx={preview.viewportScrollOffsetPx}
          />
        )}
      </div>
    </div>
  );
}

export { BrowserScene };
