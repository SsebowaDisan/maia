import type { MouseEvent } from "react";
import type { ZoomHistoryEntry } from "./types";

type PdfTargetRegion = {
  keyword: string;
  color: "yellow" | "green";
  x: number;
  y: number;
  width: number;
  height: number;
} | null;

function clampPercent(value: number): number {
  return Math.max(0, Math.min(100, value));
}

function readPercentFromClick(event: MouseEvent<HTMLElement>): number | null {
  const rect = event.currentTarget.getBoundingClientRect();
  if (!rect.height) {
    return null;
  }
  return clampPercent(((event.clientY - rect.top) / rect.height) * 100);
}

function PdfScrollRail({
  pdfScrollPercent,
  onSelect,
}: {
  pdfScrollPercent: number | null;
  onSelect?: (percent: number) => void;
}) {
  if (typeof pdfScrollPercent !== "number") {
    return null;
  }
  const interactive = typeof onSelect === "function";
  return (
    <div className={`absolute right-2 top-14 bottom-4 flex flex-col items-center ${interactive ? "" : "pointer-events-none"}`}>
      <button
        type="button"
        disabled={!interactive}
        aria-label="Set document scroll position"
        onClick={(event) => {
          if (!onSelect) {
            return;
          }
          const percent = readPercentFromClick(event);
          if (percent === null) {
            return;
          }
          onSelect(percent);
        }}
        className={`relative h-full w-1.5 rounded-full bg-black/20 ${interactive ? "cursor-pointer" : ""}`}
      >
        <div
          className="pointer-events-none w-1.5 rounded-full bg-black/60 transition-all duration-300"
          style={{ height: "24px", marginTop: `calc(${pdfScrollPercent}% - 12px)` }}
        />
      </button>
      <span className="mt-1 text-[10px] font-medium text-black/70">{Math.round(pdfScrollPercent)}%</span>
    </div>
  );
}

function PdfZoomBadge({
  pdfZoomLevel,
  pdfZoomReason,
}: {
  pdfZoomLevel: number | null;
  pdfZoomReason: string;
}) {
  if (pdfZoomLevel === null && !pdfZoomReason) {
    return null;
  }
  return (
    <div className="pointer-events-none absolute right-4 top-16 z-20 rounded-lg border border-black/15 bg-white/92 px-2 py-1 text-[10px] text-[#2d2d31]">
      <p className="font-semibold uppercase tracking-[0.08em] text-[#4c4c50]">Zoom</p>
      <p className="mt-0.5">{pdfZoomLevel !== null ? `${Math.round(pdfZoomLevel * 100)}%` : "focused"}</p>
      {pdfZoomReason ? <p className="mt-0.5 max-w-[200px] truncate text-[#5b5b60]">{pdfZoomReason}</p> : null}
    </div>
  );
}

function PdfTargetFocus({ pdfTargetRegion }: { pdfTargetRegion: PdfTargetRegion }) {
  if (!pdfTargetRegion) {
    return null;
  }
  return (
    <div
      className="pointer-events-none absolute z-20 animate-pulse rounded-md border-2 border-[#f5b942]/90 shadow-[0_0_0_2px_rgba(245,185,66,0.3)]"
      style={{
        left: `${pdfTargetRegion.x}%`,
        top: `${pdfTargetRegion.y}%`,
        width: `${pdfTargetRegion.width}%`,
        height: `${pdfTargetRegion.height}%`,
      }}
    >
      <span className="absolute -top-5 left-0 rounded bg-[#f5b942]/95 px-1.5 py-0.5 text-[10px] font-semibold text-[#2f2508]">
        {pdfTargetRegion.keyword || "focus"}
      </span>
    </div>
  );
}

function PdfMiniMap({
  pdfPage,
  pdfPageTotal,
  pdfScrollPercent,
  pdfTargetRegion,
  onSelect,
}: {
  pdfPage: number;
  pdfPageTotal: number;
  pdfScrollPercent: number | null;
  pdfTargetRegion: PdfTargetRegion;
  onSelect?: (percent: number) => void;
}) {
  const pageProgress =
    pdfPageTotal <= 1 ? 0 : Math.max(0, Math.min(100, ((pdfPage - 1) / Math.max(1, pdfPageTotal - 1)) * 100));
  const viewportTop =
    typeof pdfScrollPercent === "number"
      ? Math.max(0, Math.min(86, Math.round(pdfScrollPercent * 0.86)))
      : Math.round(pageProgress * 0.86);
  const interactive = typeof onSelect === "function";
  return (
    <button
      type="button"
      disabled={!interactive}
      aria-label="Set document mini-map position"
      onClick={(event) => {
        if (!onSelect) {
          return;
        }
        const percent = readPercentFromClick(event);
        if (percent === null) {
          return;
        }
        onSelect(percent);
      }}
      className={`absolute bottom-20 right-4 z-20 h-28 w-20 rounded-lg border border-black/20 bg-white/88 p-1.5 text-[9px] backdrop-blur-sm ${
        interactive ? "cursor-pointer" : "pointer-events-none"
      }`}
    >
      <p className="font-semibold uppercase tracking-[0.08em] text-[#4c4c50]">Mini-map</p>
      <div className="relative mt-1 h-[88px] w-full rounded bg-black/8">
        <div
          className="absolute left-[2px] right-[2px] rounded border border-[#7ea6ff] bg-[#7ea6ff]/15"
          style={{ top: `${viewportTop}%`, height: "14%" }}
        />
        {pdfTargetRegion ? (
          <span
            className="absolute h-1.5 w-1.5 rounded-full bg-[#f5b942]/95"
            style={{ left: `${Math.max(1, Math.min(94, pdfTargetRegion.x))}%`, top: `${Math.max(1, Math.min(94, pdfTargetRegion.y))}%` }}
          />
        ) : null}
      </div>
    </button>
  );
}

function PdfComparePanel({
  pdfCompareLeft,
  pdfCompareRight,
  pdfCompareVerdict,
}: {
  pdfCompareLeft: string;
  pdfCompareRight: string;
  pdfCompareVerdict: string;
}) {
  if (!pdfCompareLeft || !pdfCompareRight) {
    return null;
  }
  return (
    <div className="pointer-events-none absolute left-3 right-3 bottom-24 z-20 rounded-xl border border-black/15 bg-white/90 px-3 py-2 text-[10px] text-[#1d1d1f] backdrop-blur-sm">
      <p className="font-semibold uppercase tracking-[0.08em] text-[#4c4c50]">Compare regions</p>
      <div className="mt-1 grid grid-cols-2 gap-2">
        <div className="rounded-md border border-black/10 bg-white/95 px-2 py-1">
          <p className="font-semibold text-[#3b3b40]">Region A</p>
          <p className="mt-0.5 line-clamp-3 text-[#2e2e31]">{pdfCompareLeft}</p>
        </div>
        <div className="rounded-md border border-black/10 bg-white/95 px-2 py-1">
          <p className="font-semibold text-[#3b3b40]">Region B</p>
          <p className="mt-0.5 line-clamp-3 text-[#2e2e31]">{pdfCompareRight}</p>
        </div>
      </div>
      {pdfCompareVerdict ? <p className="mt-1 line-clamp-2 text-[#55555a]">{pdfCompareVerdict}</p> : null}
    </div>
  );
}

function pdfZoomActionLabel(action: ZoomHistoryEntry["action"]): string {
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

function PdfZoomHistoryPanel({ zoomHistory }: { zoomHistory: ZoomHistoryEntry[] }) {
  if (!zoomHistory.length) {
    return null;
  }
  const rows = zoomHistory.slice(-3).reverse();
  return (
    <div className="pointer-events-none absolute left-3 top-20 z-20 w-[min(48%,360px)] rounded-xl border border-black/15 bg-white/90 px-2.5 py-2 text-[10px] text-[#252528] backdrop-blur-sm">
      <p className="font-semibold uppercase tracking-[0.08em] text-[#4c4c50]">Zoom history</p>
      <div className="mt-1.5 space-y-1">
        {rows.map((item) => (
          <div
            key={`pdf-zoom-history-${item.eventRef || item.timestamp}`}
            className="rounded-md border border-black/10 bg-white/95 px-2 py-1"
          >
            <p className="font-semibold text-[#202024]">
              {pdfZoomActionLabel(item.action)}
              {item.zoomLevel !== null ? ` ${Math.round(item.zoomLevel * 100)}%` : ""}
              {item.eventIndex !== null ? `  #${item.eventIndex}` : ""}
            </p>
            {item.zoomReason ? <p className="line-clamp-1 text-[#4a4a4f]">{item.zoomReason}</p> : null}
            {item.graphNodeId || item.sceneRef ? (
              <p className="line-clamp-1 text-[#66666c]">
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

function PdfVerifierConflictBadge({
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
    <div className="pointer-events-none absolute left-3 top-3 z-20 w-[min(46%,380px)] rounded-xl border border-[#f2b05b]/45 bg-[#fff5e9]/94 px-2.5 py-2 text-[10px] text-[#7a430a]">
      <p className="font-semibold uppercase tracking-[0.08em]">Verifier conflict</p>
      <p className="mt-0.5 line-clamp-2">
        {verifierConflictReason || "Conflicting evidence detected during verification."}
      </p>
      <p className="mt-0.5 text-[#8a5d1a]">
        {verifierRecheckRequired ? "Re-check required" : ""}
        {verifierRecheckRequired && zoomEscalationRequested ? "  -  " : ""}
        {zoomEscalationRequested ? "Zoom escalation requested" : ""}
      </p>
    </div>
  );
}

export {
  PdfComparePanel,
  PdfMiniMap,
  PdfScrollRail,
  PdfTargetFocus,
  PdfVerifierConflictBadge,
  PdfZoomBadge,
  PdfZoomHistoryPanel,
};
