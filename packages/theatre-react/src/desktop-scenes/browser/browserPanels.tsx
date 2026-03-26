import React from "react";

function clampPercent(value: number): number {
  return Math.max(0, Math.min(100, value));
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
      <div className="rounded-full border border-white/28 bg-black/62 px-3 py-1.5 text-[11px] font-medium text-white/92 shadow-[0_14px_30px_-22px_rgba(0,0,0,0.65)]">
        Copied: <span className="font-semibold">{copyPulseText}</span>
      </div>
    </div>
  );
}

function ScrollMeter({
  scrollPercent,
  onSelect,
}: {
  scrollPercent: number | null;
  onSelect?: (percent: number) => void;
}) {
  const interactive = typeof onSelect === "function";
  const hasPercent = typeof scrollPercent === "number";
  const normalizedPercent = hasPercent ? clampPercent(scrollPercent) : 0;
  const label = typeof scrollPercent === "number" ? `${Math.round(normalizedPercent)}%` : "--";
  const handleTrackClick = (event: React.MouseEvent<HTMLButtonElement>) => {
    if (!onSelect) {
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    if (!rect.height) {
      return;
    }
    const percent = ((event.clientY - rect.top) / rect.height) * 100;
    onSelect(clampPercent(percent));
  };
  return (
    <div className={`absolute right-2 top-20 bottom-6 z-20 flex flex-col items-center ${interactive ? "" : "pointer-events-none"}`}>
      <button
        type="button"
        onClick={handleTrackClick}
        disabled={!interactive}
        aria-label="Set scroll position"
        className={`relative h-full w-1.5 rounded-full bg-black/20 ${interactive ? "cursor-pointer" : ""}`}
      >
        {hasPercent ? (
          <div
            className="pointer-events-none absolute left-0 right-0 rounded-full bg-black/60 transition-all duration-300"
            style={{ height: "24px", top: `${normalizedPercent}%`, transform: "translateY(-50%)" }}
          />
        ) : null}
      </button>
      <span className="mt-1 text-[10px] font-medium text-black/70">{label}</span>
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
        <p className="line-clamp-3 rounded-md border border-white/15 bg-white/[0.05] px-2 py-1 text-white/85">{compareLeft}</p>
        <p className="line-clamp-3 rounded-md border border-white/15 bg-white/[0.05] px-2 py-1 text-white/85">{compareRight}</p>
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
    <div className="pointer-events-none absolute left-3 top-3 z-20 w-[min(42%,360px)] rounded-xl border border-white/26 bg-black/70 px-2.5 py-2 text-[10px] text-white/92">
      <p className="font-semibold tracking-[0.02em]">Verifier conflict</p>
      <p className="mt-0.5 line-clamp-2 text-white/82">
        {verifierConflictReason || "Conflicting or weak evidence detected."}
      </p>
      <p className="mt-0.5 text-white/70">
        {verifierRecheckRequired ? "Re-check required" : ""}
        {verifierRecheckRequired && zoomEscalationRequested ? "  -  " : ""}
        {zoomEscalationRequested ? "Zoom escalation requested" : ""}
      </p>
    </div>
  );
}

function ExecutionRoadmapOverlay({
  roadmapSteps,
  roadmapActiveIndex,
  visible = true,
}: {
  roadmapSteps: Array<{ toolId: string; title: string; whyThisStep: string }>;
  roadmapActiveIndex: number;
  visible?: boolean;
}) {
  if (!roadmapSteps.length) {
    return null;
  }
  const visibilityClass = visible
    ? "opacity-100 translate-y-0 scale-100"
    : "opacity-0 -translate-y-1 scale-[0.985]";
  return (
    <div className={`pointer-events-none absolute left-3 top-14 z-20 w-[min(44%,360px)] rounded-xl border border-white/18 bg-black/58 px-2.5 py-2 text-[10px] text-white/85 backdrop-blur-sm transition-all duration-300 ease-out ${visibilityClass}`}>
      <p className="font-semibold uppercase tracking-[0.08em] text-white/70">Execution plan</p>
      <div className="mt-1.5 space-y-1">
        {roadmapSteps.slice(0, 8).map((step, index) => {
          const isDone = roadmapActiveIndex > index;
          const isActive = roadmapActiveIndex === index;
          return (
            <div
              key={`roadmap-step-${index}-${step.toolId || step.title}`}
              className={`flex items-start gap-1.5 rounded-md border px-2 py-1 ${
                isDone
                  ? "border-white/15 bg-white/[0.07]"
                  : isActive
                    ? "border-white/30 bg-white/[0.12]"
                    : "border-white/10 bg-white/[0.05]"
              }`}
            >
              <span
                className={`mt-[2px] h-1.5 w-1.5 rounded-full ${
                  isDone ? "bg-[#34c759]" : isActive ? "animate-pulse bg-white/90" : "bg-white/30"
                }`}
              />
              <p
                className={`line-clamp-1 ${
                  isDone ? "text-white/45" : isActive ? "text-white/95" : "text-white/65"
                }`}
              >
                {step.title}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export {
  ComparePanel,
  CopyPulse,
  ExecutionRoadmapOverlay,
  FindOverlay,
  ScrollMeter,
  VerifierConflictBadge,
  ZoomBadge,
};
