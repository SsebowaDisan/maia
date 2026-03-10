import { useEffect, useState } from "react";
import { InteractionOverlay } from "./InteractionOverlay";
import {
  PdfComparePanel,
  PdfMiniMap,
  PdfScrollRail,
  PdfTargetFocus,
  PdfVerifierConflictBadge,
  PdfZoomBadge,
  PdfZoomHistoryPanel,
} from "./document_scene_panels";
import type { DocumentHighlight, ZoomHistoryEntry } from "./types";
import { useTypewriterText } from "./useTypewriterText";

function highlightBackground(color: "yellow" | "green") {
  return color === "green" ? "rgba(112, 216, 123, 0.22)" : "rgba(255, 213, 79, 0.22)";
}

type DocumentPdfSceneProps = {
  activeDetail: string;
  activeEventType: string;
  action: string;
  actionPhase: string;
  actionStatus: string;
  actionTargetLabel: string;
  documentHighlights: DocumentHighlight[];
  pdfPage: number;
  pdfPageTotal: number;
  pdfScanRegion: string;
  pdfScrollDirection: "up" | "down" | "";
  pdfScrollPercent: number | null;
  pdfZoomLevel: number | null;
  pdfZoomReason: string;
  zoomHistory: ZoomHistoryEntry[];
  pdfTargetRegion: {
    keyword: string;
    color: "yellow" | "green";
    x: number;
    y: number;
    width: number;
    height: number;
  } | null;
  pdfCompareLeft: string;
  pdfCompareRight: string;
  pdfCompareVerdict: string;
  pdfFindQuery: string;
  pdfFindMatchCount: number;
  pdfSemanticFindResults: Array<{ term: string; confidence: number }>;
  verifierConflict: boolean;
  verifierConflictReason: string;
  verifierRecheckRequired: boolean;
  zoomEscalationRequested: boolean;
  sceneText: string;
  stageFileUrl: string;
};

function DocumentPdfScene({
  activeDetail,
  activeEventType,
  action,
  actionPhase,
  actionStatus,
  actionTargetLabel,
  documentHighlights,
  pdfPage,
  pdfPageTotal,
  pdfScanRegion,
  pdfScrollDirection,
  pdfScrollPercent,
  pdfZoomLevel,
  pdfZoomReason,
  zoomHistory,
  pdfTargetRegion,
  pdfCompareLeft,
  pdfCompareRight,
  pdfCompareVerdict,
  pdfFindQuery,
  pdfFindMatchCount,
  pdfSemanticFindResults,
  verifierConflict,
  verifierConflictReason,
  verifierRecheckRequired,
  zoomEscalationRequested,
  sceneText,
  stageFileUrl,
}: DocumentPdfSceneProps) {
  const page = Math.max(1, Math.round(pdfPage));
  const totalPages = Math.max(page, Math.round(pdfPageTotal));
  const frameUrl = `${stageFileUrl}#page=${page}&zoom=page-fit&toolbar=0&navpanes=0&scrollbar=0&view=FitH`;
  const normalizedEventType = String(activeEventType || "").trim().toLowerCase();
  const normalizedAction = String(action || "").trim().toLowerCase();
  const normalizedActionPhase = String(actionPhase || "").trim().toLowerCase();
  const normalizedStatus = String(actionStatus || "").trim().toLowerCase();
  const showScanFocus =
    normalizedAction === "extract" &&
    normalizedStatus !== "failed" &&
    (Boolean(pdfScanRegion) || normalizedEventType.startsWith("pdf_"));
  const showPageTurnBadge =
    normalizedAction === "navigate" &&
    normalizedActionPhase !== "failed" &&
    totalPages > 1;
  const showFindOverlay =
    normalizedAction === "find" ||
    normalizedEventType.startsWith("pdf_find") ||
    normalizedEventType.startsWith("pdf.find") ||
    Boolean(pdfFindQuery);
  const showScanSweep = showScanFocus && normalizedActionPhase === "active";
  return (
    <div className="absolute inset-0 bg-[radial-gradient(circle_at_12%_8%,rgba(168,216,255,0.92),rgba(122,176,244,0.72)_40%,rgba(98,148,232,0.9)_100%)] p-9 text-[#1d1d1f]">
      <div className="relative mx-auto flex h-full w-full max-w-[840px] flex-col overflow-hidden rounded-[20px] border border-black/[0.1] bg-[#fcfcfd] shadow-[0_26px_58px_-42px_rgba(0,0,0,0.52)]">
        <div className="relative z-30 flex items-center gap-2 border-b border-black/[0.08] px-5 py-3">
          <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#ffbd2e]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
          <p className="ml-2 text-[12px] font-semibold tracking-[0.01em] text-[#3a3a3c]">Document preview</p>
          <p className="ml-auto rounded-full border border-black/[0.1] bg-[#f7f8fb] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#5f6368]">
            Page {page}/{totalPages}
          </p>
        </div>
        <div className="relative min-h-0 flex-1 overflow-hidden bg-[#f5f7fb]">
          <iframe
            src={frameUrl}
            title="Agent PDF live preview"
            className="absolute inset-0 h-full w-full border-0 bg-white"
            style={{ transform: "translateZ(0)", backfaceVisibility: "hidden" }}
          />
          <PdfVerifierConflictBadge
            verifierConflict={verifierConflict}
            verifierConflictReason={verifierConflictReason}
            verifierRecheckRequired={verifierRecheckRequired}
            zoomEscalationRequested={zoomEscalationRequested}
          />
          <div className="pointer-events-none absolute left-3 right-3 top-3 rounded-xl border border-black/15 bg-white/90 px-3 py-2 text-[11px] text-[#1d1d1f]">
            <div className="flex items-center justify-between gap-2">
              <p className="font-semibold">Live PDF review</p>
              <p className="rounded-full border border-black/10 bg-white/95 px-2 py-0.5 text-[10px] font-medium">
                Page {page}/{totalPages}
              </p>
            </div>
            <p className="mt-1 text-[11px] text-[#3a3a3d]">
              {sceneText || activeDetail || "Scanning document pages and collecting evidence."}
            </p>
            {pdfScanRegion ? (
              <p className="mt-1.5 line-clamp-2 rounded-md border border-black/10 bg-white/95 px-2 py-1 text-[10px] text-[#2e2e31]">
                {pdfScanRegion}
              </p>
            ) : null}
            {showFindOverlay ? (
              <div className="mt-1 rounded-md border border-black/10 bg-white/95 px-2 py-1 text-[10px] text-[#2e2e31]">
                <p>
                  Find: {pdfFindQuery || "scanning terms"}{" "}
                  <span className="text-[#6b6b70]">({Math.max(1, pdfFindMatchCount || 1)} matches)</span>
                </p>
                {pdfSemanticFindResults.length ? (
                  <div className="mt-1 space-y-0.5">
                    {pdfSemanticFindResults.slice(0, 3).map((item) => (
                      <p key={`pdf-semantic-${item.term}`} className="line-clamp-1 text-[#4b4b50]">
                        <span className="font-medium">{item.term}</span>
                        <span className="ml-1 text-[#6b6b70]">{Math.round(item.confidence * 100)}%</span>
                      </p>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
            {pdfScrollDirection ? (
              <p className="mt-1 text-[10px] uppercase tracking-[0.06em] text-[#5b5b60]">
                Scroll {pdfScrollDirection}
              </p>
            ) : null}
          </div>
          <InteractionOverlay
            sceneSurface="document"
            activeEventType={activeEventType}
            activeDetail={activeDetail}
            scrollDirection={pdfScrollDirection}
            action={action}
            actionPhase={actionPhase}
            actionStatus={actionStatus}
            actionTargetLabel={actionTargetLabel}
          />
          {showScanFocus ? (
            <div className="pointer-events-none absolute left-1/2 top-1/2 z-20 h-[24%] w-[62%] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-xl border border-[#f8cd6f]/85 bg-[#f8cd6f]/12 shadow-[0_0_0_1px_rgba(248,205,111,0.4)]">
              {showScanSweep ? (
                <div
                  className="absolute left-0 right-0 h-[38%] animate-[pulse_1.2s_ease-in-out_infinite]"
                  style={{
                    top: `${Math.max(2, Math.min(62, Number(pdfScrollPercent ?? 40)))}%`,
                    transform: "translateY(-50%)",
                    transition: "top 220ms ease-out, opacity 220ms ease-out",
                    background:
                      "linear-gradient(180deg,rgba(248,205,111,0) 0%,rgba(248,205,111,0.38) 50%,rgba(248,205,111,0) 100%)",
                  }}
                />
              ) : null}
            </div>
          ) : null}
          <PdfTargetFocus pdfTargetRegion={pdfTargetRegion} />
          <PdfZoomBadge pdfZoomLevel={pdfZoomLevel} pdfZoomReason={pdfZoomReason} />
          <PdfZoomHistoryPanel zoomHistory={zoomHistory} />
          <PdfMiniMap
            pdfPage={page}
            pdfPageTotal={totalPages}
            pdfScrollPercent={pdfScrollPercent}
            pdfTargetRegion={pdfTargetRegion}
          />
          {showPageTurnBadge ? (
            <div className="pointer-events-none absolute right-4 top-16 z-20 rounded-full border border-black/15 bg-white/92 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#2d2d31]">
              Page turn
            </div>
          ) : null}
          <PdfComparePanel
            pdfCompareLeft={pdfCompareLeft}
            pdfCompareRight={pdfCompareRight}
            pdfCompareVerdict={pdfCompareVerdict}
          />
          {documentHighlights.length ? (
            <div className="pointer-events-none absolute left-3 right-3 bottom-3 rounded-xl border border-black/15 bg-white/90 px-3 py-2 text-[11px] text-[#1d1d1f]">
              <p className="text-[11px] font-semibold">Copied highlights</p>
              <div className="mt-1 space-y-1">
                {documentHighlights.map((item, index) => (
                  <p key={`${item.word}-${index}`} className="line-clamp-2">
                    <span
                      className="rounded px-1 py-0.5 font-semibold"
                      style={{ backgroundColor: highlightBackground(item.color) }}
                    >
                      {item.word || "highlight"}
                    </span>{" "}
                    {item.snippet}
                  </p>
                ))}
              </div>
            </div>
          ) : null}
          <PdfScrollRail pdfScrollPercent={pdfScrollPercent} />
        </div>
      </div>
    </div>
  );
}

type RoadmapStep = { toolId: string; title: string; whyThisStep: string };

type DocumentFallbackSceneProps = {
  activeEventType: string;
  activeDetail: string;
  action: string;
  actionPhase: string;
  actionStatus: string;
  actionTargetLabel: string;
  clipboardPreview: string;
  documentHighlights: DocumentHighlight[];
  sceneText: string;
  stageFileName: string;
  roadmapSteps?: RoadmapStep[];
  roadmapActiveIndex?: number;
};

function isPlannerNarrativeEventType(eventType: string): boolean {
  const normalized = String(eventType || "").trim().toLowerCase();
  if (!normalized) {
    return false;
  }
  return (
    normalized === "planning_started" ||
    normalized.startsWith("plan_") ||
    normalized.startsWith("planning_") ||
    normalized.startsWith("task_understanding_") ||
    normalized.startsWith("preflight_") ||
    normalized.startsWith("llm.task_") ||
    normalized.startsWith("llm.plan_") ||
    normalized === "llm.web_routing_decision" ||
    normalized === "llm.intent_tags"
  );
}

function DocumentFallbackScene({
  activeEventType,
  activeDetail,
  action,
  actionPhase,
  actionStatus,
  actionTargetLabel,
  clipboardPreview,
  documentHighlights,
  sceneText,
  stageFileName,
  roadmapSteps = [],
  roadmapActiveIndex = -1,
}: DocumentFallbackSceneProps) {
  const [reduceMotion, setReduceMotion] = useState(false);
  const suppressPlannerNarrative = isPlannerNarrativeEventType(activeEventType);
  const narrativeText = suppressPlannerNarrative
    ? "Preparing execution roadmap..."
    : sceneText || activeDetail || "Preparing and updating document blocks...";
  const hasRoadmap = roadmapSteps.length > 0;
  const totalSteps = hasRoadmap ? roadmapSteps.length : 4;
  const normalizedActiveIndex = hasRoadmap ? Math.max(0, Math.min(roadmapSteps.length - 1, roadmapActiveIndex)) : 1;
  const doneCount = hasRoadmap ? Math.max(0, Math.min(totalSteps, normalizedActiveIndex)) : 1;
  const progressPercent = Math.max(12, Math.round((doneCount / Math.max(1, totalSteps)) * 100));
  const activeRoadmapStep = hasRoadmap
    ? roadmapSteps[Math.max(0, Math.min(roadmapSteps.length - 1, normalizedActiveIndex))]
    : null;
  const statusText = activeRoadmapStep?.title || "Document workspace active";
  const { typedText: typedStatusText } = useTypewriterText(statusText, {
    charIntervalMs: 52,
  });
  const supportingLine = activeRoadmapStep?.whyThisStep || narrativeText;

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReduceMotion(mediaQuery.matches);
    sync();
    mediaQuery.addEventListener("change", sync);
    return () => mediaQuery.removeEventListener("change", sync);
  }, []);

  return (
    <div className="absolute inset-0 bg-[radial-gradient(circle_at_12%_8%,rgba(168,216,255,0.92),rgba(122,176,244,0.72)_40%,rgba(98,148,232,0.9)_100%)] p-9 text-[#111827]">
      <style>{`
        @keyframes doc-active-sweep {
          0% { transform: translateX(-130%); opacity: 0.08; }
          25% { opacity: 0.24; }
          75% { opacity: 0.2; }
          100% { transform: translateX(220%); opacity: 0.08; }
        }
        @keyframes doc-spinner {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
        @keyframes doc-progress-shimmer {
          0% { transform: translateX(-120%); }
          100% { transform: translateX(220%); }
        }
      `}</style>
      <div className="mx-auto flex h-full w-full max-w-[840px] flex-col overflow-hidden rounded-[14px] border border-black/10 bg-white shadow-[0_22px_48px_-34px_rgba(17,24,39,0.45)]">
        <div className="flex h-[44px] shrink-0 items-center justify-center border-b border-[#ebedf2] px-4">
          <p title={stageFileName || "Agent workspace"} className="max-w-[75%] truncate text-[13px] font-medium text-[#5b6472]">
            Agent workspace
          </p>
        </div>
        <div className="relative flex flex-1 flex-col px-8 pb-5 pt-6">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#7b8598]">Document activity</p>
          <p className="mt-2 max-w-[680px] text-[clamp(17px,2.05vw,24px)] font-semibold leading-[1.17] tracking-[-0.012em] text-[#4a5160]">
            {typedStatusText || "\u00A0"}
          </p>
          <p className="mt-1.5 max-w-[560px] text-[13px] leading-[1.5] text-[#697588]">{supportingLine}</p>
          {hasRoadmap ? (
            <div className="mt-4 w-full max-w-[560px] space-y-2">
              {roadmapSteps.slice(0, 5).map((step, index) => {
                const isDone = index < normalizedActiveIndex;
                const isActive = index === normalizedActiveIndex;
                const stepSummary = String(step.whyThisStep || "").trim() || (
                  isDone
                    ? "Completed."
                    : isActive
                      ? "In progress."
                      : "Pending."
                );
                return (
                  <div
                    key={`roadmap-compact-${index}`}
                    className={`relative overflow-hidden rounded-xl border px-3.5 py-2.5 ${
                      isActive
                        ? "border-[#c2cedf] bg-white shadow-[0_14px_26px_-24px_rgba(15,23,42,0.6)]"
                        : isDone
                          ? "border-[#d9e1ec] bg-[#f7f9fc]"
                          : "border-[#e6ebf4] bg-[#fbfcfe]"
                    }`}
                    style={
                      reduceMotion
                        ? undefined
                        : { transition: "background-color 220ms ease, border-color 220ms ease, box-shadow 220ms ease" }
                    }
                  >
                    {isActive && !reduceMotion ? (
                      <div
                        className="pointer-events-none absolute inset-y-0 left-0 w-[40%] bg-[linear-gradient(90deg,rgba(59,130,246,0),rgba(59,130,246,0.14),rgba(59,130,246,0))]"
                        style={{ animation: "doc-active-sweep 2.2s cubic-bezier(0.34,0,0.2,1) infinite" }}
                      />
                    ) : null}
                    <div className="relative z-10 flex items-start gap-3">
                      {isDone ? (
                        <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border border-[#4abf6a] bg-[#34c759] text-white">
                          <svg viewBox="0 0 12 12" className="h-3 w-3 fill-none stroke-current stroke-[2.2]">
                            <path d="M2 6.2 4.7 9 10 3.4" />
                          </svg>
                        </span>
                      ) : isActive ? (
                        <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border border-[#86a5df] bg-[#eef3ff]">
                          <span
                            className="h-3.5 w-3.5 rounded-full border border-[#4f7eff] border-t-transparent"
                            style={reduceMotion ? undefined : { animation: "doc-spinner 1s linear infinite" }}
                          />
                        </span>
                      ) : (
                        <span className="mt-0.5 h-5 w-5 shrink-0 rounded-md border border-[#cad3e2] bg-white" />
                      )}
                      <div className="min-w-0">
                        <p
                          className={`truncate text-[13px] ${
                            isDone
                              ? "text-[#98a2b3] line-through decoration-[#c8d1df] decoration-[1.5px]"
                              : isActive
                                ? "font-medium text-[#1f2a3d]"
                                : "text-[#3f4a5d]"
                          }`}
                        >
                          {step.title}
                        </p>
                        <p
                          className={`mt-0.5 line-clamp-2 text-[12px] leading-[1.35] ${
                            isDone ? "text-[#aab3c1]" : isActive ? "text-[#5a6881]" : "text-[#7b8699]"
                          }`}
                        >
                          {stepSummary}
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : null}
          <div className="flex-1" />
        </div>
        <div className="flex items-center gap-3 px-5 pb-4 pt-1">
          <div className="h-[4px] flex-1 overflow-hidden rounded-full bg-[#dde6f8]">
            <div className="relative h-full overflow-hidden rounded-full bg-[linear-gradient(90deg,#b9cdf3_0%,#93b2eb_100%)]" style={{ width: `${progressPercent}%` }}>
              {!reduceMotion ? (
                <div
                  className="absolute inset-y-0 left-0 w-[34%] bg-[linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,0.85),rgba(255,255,255,0))]"
                  style={{ animation: "doc-progress-shimmer 2.1s ease-in-out infinite" }}
                />
              ) : null}
            </div>
          </div>
          <p className="shrink-0 whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.08em] text-[#6379ad]">Running</p>
        </div>
      </div>
    </div>
  );
}

export { DocumentFallbackScene, DocumentPdfScene };
