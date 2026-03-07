import React from "react";

import { highlightPalette } from "./helpers";
import type { HighlightRegion, ZoomHistoryEntry } from "./types";

function HighlightOverlay({
  highlightRegions,
  keyPrefix,
}: {
  highlightRegions: HighlightRegion[];
  keyPrefix: string;
}) {
  if (!highlightRegions.length) {
    return null;
  }
  return (
    <div className="pointer-events-none absolute inset-0">
      {highlightRegions.map((region, index) => {
        const palette = highlightPalette(region.color);
        return (
          <div
            key={`${keyPrefix}-${region.keyword}-${index}`}
            className="absolute rounded-md"
            style={{
              left: `${region.x}%`,
              top: `${region.y}%`,
              width: `${region.width}%`,
              height: `${region.height}%`,
              border: `1px solid ${palette.border}`,
              backgroundColor: palette.fill,
              boxShadow: `0 0 0 1px ${palette.fill}`,
            }}
          >
            {region.keyword ? (
              <span
                className="absolute -top-5 left-0 rounded px-1.5 py-0.5 text-[10px] font-semibold"
                style={{ backgroundColor: palette.labelBackground, color: palette.labelText }}
              >
                {region.keyword}
              </span>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function FindOverlay({
  dedupedBrowserKeywords,
  findMatchCount,
  findQuery,
  semanticFindResults,
}: {
  dedupedBrowserKeywords: string[];
  findMatchCount: number;
  findQuery: string;
  semanticFindResults: Array<{ term: string; confidence: number }>;
}) {
  const semanticRows = semanticFindResults.slice(0, 4);
  return (
    <div className="pointer-events-none absolute left-1/2 top-3 z-20 w-[min(74%,580px)] -translate-x-1/2 rounded-xl border border-black/15 bg-white/88 px-3 py-2 text-[#232327] shadow-[0_8px_22px_-16px_rgba(0,0,0,0.55)] backdrop-blur-sm">
      <div className="flex items-center justify-between gap-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#6e6e73]">
        <span>Find in page</span>
        <span>{findMatchCount ? `${Math.max(1, Math.round(findMatchCount))} matches` : "Scanning..."}</span>
      </div>
      <div className="mt-1.5 rounded-full border border-black/10 bg-white px-2.5 py-1 text-[12px] text-[#1f1f22]">
        {findQuery || dedupedBrowserKeywords.join(" ").slice(0, 90) || "Searching highlighted terms..."}
      </div>
      {dedupedBrowserKeywords.length ? (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {dedupedBrowserKeywords.slice(0, 6).map((term) => (
            <span
              key={`find-chip-${term}`}
              className="rounded-full border border-black/10 bg-white/90 px-2 py-0.5 text-[10px] text-[#4c4c50]"
            >
              {term}
            </span>
          ))}
        </div>
      ) : null}
      {semanticRows.length ? (
        <div className="mt-1.5 rounded-md border border-black/10 bg-white/92 px-2 py-1">
          <p className="text-[9px] font-semibold uppercase tracking-[0.08em] text-[#6e6e73]">Semantic ranking</p>
          <div className="mt-1 space-y-0.5">
            {semanticRows.map((item) => (
              <p key={`semantic-${item.term}`} className="line-clamp-1 text-[10px] text-[#3a3a3d]">
                <span className="font-medium">{item.term}</span>
                <span className="ml-1 text-[#66666c]">{Math.round(item.confidence * 100)}%</span>
              </p>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function CopyPulse({ copyPulseText, copyPulseVisible }: { copyPulseText: string; copyPulseVisible: boolean }) {
  if (!copyPulseVisible) {
    return null;
  }
  return (
    <div className="pointer-events-none absolute right-4 bottom-16 z-20 transition-all duration-300">
      <div className="rounded-full border border-[#ffdc80]/70 bg-[#fff5cf]/95 px-3 py-1.5 text-[11px] font-medium text-[#3a2d0d] shadow-[0_14px_30px_-22px_rgba(0,0,0,0.65)]">
        Copied: <span className="font-semibold">{copyPulseText}</span>
      </div>
    </div>
  );
}

function SceneFooter({
  activeDetail,
  activeTitle,
  sceneText,
}: {
  activeDetail: string;
  activeTitle: string;
  sceneText: string;
}) {
  return (
    <div className="pointer-events-none absolute left-3 right-3 bottom-3 rounded-lg border border-black/10 bg-white/78 px-3 py-1.5 text-[11px] text-[#3a3a3c] backdrop-blur-sm">
      {sceneText || activeDetail || activeTitle || "Inspecting website and gathering evidence."}
    </div>
  );
}

function ScrollMeter({ scrollPercent }: { scrollPercent: number | null }) {
  if (typeof scrollPercent !== "number") {
    return null;
  }
  return (
    <div className="pointer-events-none absolute right-2 top-20 bottom-6 flex flex-col items-center">
      <div className="h-full w-1.5 rounded-full bg-black/20">
        <div
          className="w-1.5 rounded-full bg-black/60 transition-all duration-300"
          style={{ height: "24px", marginTop: `calc(${scrollPercent}% - 12px)` }}
        />
      </div>
      <span className="mt-1 text-[10px] font-medium text-black/70">{Math.round(scrollPercent)}%</span>
    </div>
  );
}

function TargetFocusRing({ targetRegion }: { targetRegion: HighlightRegion | null }) {
  if (!targetRegion) {
    return null;
  }
  return (
    <div
      className="pointer-events-none absolute z-20 animate-pulse rounded-md border-2 border-[#6cb9ff]/90 shadow-[0_0_0_2px_rgba(108,185,255,0.25)]"
      style={{
        left: `${targetRegion.x}%`,
        top: `${targetRegion.y}%`,
        width: `${targetRegion.width}%`,
        height: `${targetRegion.height}%`,
      }}
    >
      <span className="absolute -top-5 left-0 rounded bg-[#6cb9ff]/90 px-1.5 py-0.5 text-[10px] font-semibold text-[#031325]">
        target
      </span>
    </div>
  );
}

function ZoomBadge({ zoomLevel, zoomReason }: { zoomLevel: number | null; zoomReason: string }) {
  if (zoomLevel === null && !zoomReason) {
    return null;
  }
  return (
    <div className="pointer-events-none absolute right-3 top-14 z-20 rounded-lg border border-white/25 bg-black/55 px-2 py-1 text-[10px] text-white/85 backdrop-blur-sm">
      <p className="font-semibold uppercase tracking-[0.08em] text-white/75">Zoom</p>
      <p className="mt-0.5">{zoomLevel !== null ? `${Math.round(zoomLevel * 100)}%` : "focused"}</p>
      {zoomReason ? <p className="mt-0.5 max-w-[180px] truncate text-white/70">{zoomReason}</p> : null}
    </div>
  );
}

function zoomActionLabel(action: ZoomHistoryEntry["action"]): string {
  if (action === "zoom_in") {
    return "Zoom in";
  }
  if (action === "zoom_out") {
    return "Zoom out";
  }
  if (action === "zoom_reset") {
    return "Reset";
  }
  return "Focus region";
}

function ZoomHistoryPanel({ zoomHistory }: { zoomHistory: ZoomHistoryEntry[] }) {
  if (!zoomHistory.length) {
    return null;
  }
  const rows = zoomHistory.slice(-3).reverse();
  return (
    <div className="pointer-events-none absolute left-3 top-14 z-20 w-[min(46%,340px)] rounded-xl border border-white/20 bg-black/56 px-2.5 py-2 text-[10px] text-white/85 backdrop-blur-sm">
      <p className="font-semibold uppercase tracking-[0.08em] text-white/70">Zoom history</p>
      <div className="mt-1.5 space-y-1">
        {rows.map((item) => (
          <div key={`zoom-history-${item.eventRef || item.timestamp}`} className="rounded-md border border-white/15 bg-white/5 px-2 py-1">
            <p className="font-semibold text-white/90">
              {zoomActionLabel(item.action)}
              {item.zoomLevel !== null ? ` ${Math.round(item.zoomLevel * 100)}%` : ""}
              {item.eventIndex !== null ? `  #${item.eventIndex}` : ""}
            </p>
            {item.zoomReason ? <p className="line-clamp-1 text-white/70">{item.zoomReason}</p> : null}
            {item.graphNodeId || item.sceneRef ? (
              <p className="line-clamp-1 text-white/55">
                {item.graphNodeId ? `node:${item.graphNodeId}` : ""}
                {item.graphNodeId && item.sceneRef ? "  " : ""}
                {item.sceneRef ? `scene:${item.sceneRef}` : ""}
              </p>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

function ComparePanel({
  compareLeft,
  compareRight,
  compareVerdict,
}: {
  compareLeft: string;
  compareRight: string;
  compareVerdict: string;
}) {
  if (!compareLeft || !compareRight) {
    return null;
  }
  return (
    <div className="pointer-events-none absolute left-3 bottom-16 z-20 w-[min(48%,420px)] rounded-xl border border-white/20 bg-black/56 px-2.5 py-2 text-[10px] text-white/85 backdrop-blur-sm">
      <p className="font-semibold uppercase tracking-[0.08em] text-white/70">Compare</p>
      <div className="mt-1 grid grid-cols-2 gap-1.5">
        <p className="line-clamp-3 rounded-md border border-white/15 bg-white/5 px-2 py-1 text-white/85">{compareLeft}</p>
        <p className="line-clamp-3 rounded-md border border-white/15 bg-white/5 px-2 py-1 text-white/85">{compareRight}</p>
      </div>
      {compareVerdict ? <p className="mt-1 line-clamp-2 text-white/70">{compareVerdict}</p> : null}
    </div>
  );
}

function VerifierConflictBadge({
  verifierConflict,
  verifierConflictReason,
  verifierRecheckRequired,
  zoomEscalationRequested,
}: {
  verifierConflict: boolean;
  verifierConflictReason: string;
  verifierRecheckRequired: boolean;
  zoomEscalationRequested: boolean;
}) {
  if (!verifierConflict) {
    return null;
  }
  return (
    <div className="pointer-events-none absolute left-3 top-3 z-20 w-[min(42%,360px)] rounded-xl border border-[#ffb46b]/45 bg-[#fff4e8]/92 px-2.5 py-2 text-[10px] text-[#7a430a]">
      <p className="font-semibold uppercase tracking-[0.08em]">Verifier conflict</p>
      <p className="mt-0.5 line-clamp-2">{verifierConflictReason || "Conflicting or weak evidence detected."}</p>
      <p className="mt-0.5 text-[#8a5d1a]">
        {verifierRecheckRequired ? "Re-check required" : ""}
        {verifierRecheckRequired && zoomEscalationRequested ? "  -  " : ""}
        {zoomEscalationRequested ? "Zoom escalation requested" : ""}
      </p>
    </div>
  );
}

function BrowserMiniMap({
  highlightRegions,
  scrollPercent,
}: {
  highlightRegions: HighlightRegion[];
  scrollPercent: number | null;
}) {
  const viewportTop =
    typeof scrollPercent === "number"
      ? Math.max(0, Math.min(86, Math.round(scrollPercent * 0.86)))
      : 6;
  return (
    <div className="pointer-events-none absolute bottom-16 right-3 z-20 h-28 w-20 rounded-lg border border-white/25 bg-black/45 p-1.5 backdrop-blur-sm">
      <p className="text-[9px] font-semibold uppercase tracking-[0.08em] text-white/70">Mini-map</p>
      <div className="relative mt-1 h-[88px] w-full rounded bg-white/10">
        <div
          className="absolute left-[2px] right-[2px] rounded border border-[#8ec3ff] bg-[#8ec3ff]/15"
          style={{ top: `${viewportTop}%`, height: "14%" }}
        />
        {highlightRegions.slice(0, 8).map((region, index) => (
          <span
            key={`mini-${region.keyword}-${index}`}
            className="absolute h-1.5 w-1.5 rounded-full bg-[#ffe08a]/95"
            style={{ left: `${Math.max(1, Math.min(94, region.x))}%`, top: `${Math.max(1, Math.min(94, region.y))}%` }}
          />
        ))}
      </div>
    </div>
  );
}

export {
  BrowserMiniMap,
  ComparePanel,
  CopyPulse,
  FindOverlay,
  HighlightOverlay,
  SceneFooter,
  ScrollMeter,
  TargetFocusRing,
  VerifierConflictBadge,
  ZoomBadge,
  ZoomHistoryPanel,
};
