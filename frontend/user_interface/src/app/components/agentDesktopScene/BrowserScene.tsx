import React, { useEffect, useRef, useState } from "react";

import { ClickRipple } from "./ClickRipple";
import type { ClickRippleEntry } from "./ClickRipple";
import { GhostCursor } from "./GhostCursor";
import { ThoughtBubble } from "./ThoughtBubble";
import { InteractionOverlay } from "./InteractionOverlay";
import {
  ComparePanel,
  CopyPulse,
  FindOverlay,
  HighlightOverlay,
  TargetFocusRing,
  VerifierConflictBadge,
  ZoomBadge,
} from "./browser_scene_panels";
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
  providerLabel: string;
  renderQualityLabel: string;
  contentDensityLabel: string;
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
  // T1: Ghost Cursor + Click Ripple + Interaction Trace
  cursorX?: number | null;
  cursorY?: number | null;
  isClickEvent?: boolean;
  clickRipples?: ClickRippleEntry[];
  // T5: Thought Bubble narration
  narration?: string | null;
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
  providerLabel,
  renderQualityLabel,
  contentDensityLabel,
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
  cursorX = null,
  cursorY = null,
  isClickEvent = false,
  clickRipples = [],
  narration = null,
}: BrowserSceneProps) {
  const showSnapshotPrimary = Boolean(snapshotUrl);

  // Track whether the current snapshot image has successfully loaded.
  // Reset to false whenever the URL changes so we never flash the broken-image icon.
  const [snapshotReady, setSnapshotReady] = useState(false);
  useEffect(() => {
    setSnapshotReady(false);
  }, [snapshotUrl]);

  // Scroll impulse: when scrollPercent changes, briefly translate the scene to give
  // a physical sense of the page moving, then spring back to resting position.
  const prevScrollRef = useRef<number | null>(null);
  const [scrollOffset, setScrollOffset] = useState(0);
  const scrollSettledRef = useRef(true);
  useEffect(() => {
    const prev = prevScrollRef.current;
    prevScrollRef.current = scrollPercent;
    if (prev === null || scrollPercent === null) return;
    const delta = scrollPercent - prev;
    if (Math.abs(delta) < 1.5) return;
    // Scroll down → content moves up (negative offset); scroll up → positive
    const direction = delta > 0 ? -1 : 1;
    const magnitude = Math.min(Math.abs(delta) * 0.45, 26);
    scrollSettledRef.current = false;
    setScrollOffset(direction * magnitude);
    const t = setTimeout(() => {
      setScrollOffset(0);
      scrollSettledRef.current = true;
    }, 80);
    return () => clearTimeout(t);
  }, [scrollPercent]);

  return (
    <div className="absolute inset-0 flex flex-col bg-[#0d1118] text-white/90">
      <div className="flex items-center gap-2 border-b border-white/10 px-3 py-2">
        <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
        <span className="h-2.5 w-2.5 rounded-full bg-[#ffbd2e]" />
        <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
        <div className="ml-2 flex-1 truncate rounded-full border border-white/15 bg-white/5 px-3 py-1 text-[11px] text-white/85">
          {browserUrl || "Searching the web and opening result pages..."}
        </div>
        <div className="flex items-center gap-1.5 text-[10px]">
          {providerLabel ? (
            <span className="rounded-full border border-white/25 bg-white/10 px-2 py-0.5 text-white/85">
              {providerLabel}
            </span>
          ) : null}
          {renderQualityLabel ? (
            <span className="rounded-full border border-white/25 bg-white/10 px-2 py-0.5 text-white/85">
              quality: {renderQualityLabel}
            </span>
          ) : null}
          {contentDensityLabel ? (
            <span className="rounded-full border border-white/25 bg-white/10 px-2 py-0.5 text-white/85">
              density: {contentDensityLabel}
            </span>
          ) : null}
          {readingMode ? (
            <span className="rounded-full border border-[#86d9ff]/60 bg-[#86d9ff]/20 px-2 py-0.5 text-[#d7f4ff]">
              reading mode
            </span>
          ) : null}
          {blockedSignal ? (
            <span className="rounded-full border border-[#ff9b6a]/60 bg-[#ff9b6a]/20 px-2 py-0.5 text-[#ffd7c2]">
              blocked
            </span>
          ) : null}
        </div>
      </div>

      {showSnapshotPrimary ? (
        <div className="relative flex-1 overflow-hidden bg-white">
          {/* Skeleton shown while loading — prevents the native broken-image icon */}
          {!snapshotReady ? (
            <div className="absolute inset-0 flex items-center justify-center bg-[#f5f5f7]">
              <div className="space-y-2.5 w-[55%]">
                <div className="h-2 rounded-full bg-black/10 animate-pulse" />
                <div className="h-2 rounded-full bg-black/8 animate-pulse w-[82%]" />
                <div className="h-2 rounded-full bg-black/10 animate-pulse w-[90%]" />
              </div>
            </div>
          ) : null}
          <img
            key={snapshotUrl}
            src={snapshotUrl}
            alt="Live browser capture"
            className={`h-full w-full object-cover ${snapshotReady ? "opacity-100" : "opacity-0"}`}
            style={{
              transform: `translateY(${scrollOffset}px)`,
              transition: scrollOffset === 0
                ? "opacity 150ms, transform 420ms cubic-bezier(0.25,0.46,0.45,0.94)"
                : "opacity 150ms",
            }}
            onLoad={() => setSnapshotReady(true)}
            onError={() => { setSnapshotReady(false); onSnapshotError?.(); }}
          />
          {/* Slim scroll rail — only shown when scroll position is known */}
          {scrollPercent !== null ? (
            <div className="pointer-events-none absolute right-0 top-0 bottom-0 w-[3px] z-10">
              <div className="absolute inset-0 bg-black/[0.06]" />
              <div
                className="absolute inset-x-0 rounded-full bg-black/30 transition-all duration-300"
                style={{ height: "16%", top: `${Math.max(0, Math.min(84, scrollPercent))}%` }}
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
          <GhostCursor cursorX={cursorX} cursorY={cursorY} isClick={isClickEvent} />
          <ClickRipple ripples={clickRipples} />
          <ThoughtBubble text={narration} />
        </div>
      ) : canRenderLiveUrl ? (
        <div className="relative flex-1 bg-white">
          <iframe
            src={browserUrl}
            title="Live website preview"
            className="h-full w-full border-0"
            sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
            referrerPolicy="no-referrer-when-downgrade"
          />
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
            <div className="rounded-lg border border-[#ffdc80]/60 bg-[#fff5cf]/90 px-2.5 py-1.5 text-[11px] text-[#2f250f]">
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
    </div>
  );
}

export { BrowserScene };
