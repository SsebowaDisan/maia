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
  const frameUrl = `${stageFileUrl}#page=${page}&zoom=page-width&toolbar=0&navpanes=0&scrollbar=0`;
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
    <div className="absolute inset-0">
      <iframe
        src={frameUrl}
        title="Agent PDF live preview"
        className="absolute inset-0 h-full w-full bg-white"
      />
      <PdfVerifierConflictBadge
        verifierConflict={verifierConflict}
        verifierConflictReason={verifierConflictReason}
        verifierRecheckRequired={verifierRecheckRequired}
        zoomEscalationRequested={zoomEscalationRequested}
      />
      <div className="pointer-events-none absolute left-3 right-3 top-3 rounded-xl border border-black/15 bg-white/86 px-3 py-2 text-[11px] text-[#1d1d1f] backdrop-blur-sm">
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
        <div className="pointer-events-none absolute left-3 right-3 bottom-3 rounded-xl border border-black/15 bg-white/85 px-3 py-2 text-[11px] text-[#1d1d1f] backdrop-blur-sm">
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
  );
}

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
}: DocumentFallbackSceneProps) {
  const suppressPlannerNarrative = isPlannerNarrativeEventType(activeEventType);
  const narrativeText = suppressPlannerNarrative
    ? "Preparing execution roadmap..."
    : sceneText || activeDetail || "Preparing and updating document blocks...";

  return (
    <div className="absolute inset-0 px-4 py-3 text-white/85">
      <InteractionOverlay
        sceneSurface="document"
        activeEventType={activeEventType}
        activeDetail={activeDetail}
        scrollDirection=""
        action={action}
        actionPhase={actionPhase}
        actionStatus={actionStatus}
        actionTargetLabel={actionTargetLabel}
      />
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[12px] font-medium">{stageFileName}</span>
        <span className="text-[10px] uppercase tracking-[0.08em] text-white/65">editing</span>
      </div>
      <p className="mb-3 text-[11px] text-white/85">{narrativeText}</p>
      {documentHighlights.length ? (
        <div className="mb-3 space-y-1.5 rounded-lg border border-white/20 bg-white/10 px-2.5 py-2">
          {documentHighlights.map((item, index) => (
            <p key={`${item.word}-inline-${index}`} className="line-clamp-2 text-[10px] text-white/90">
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
      ) : null}
      {clipboardPreview ? (
        <div className="mb-3 rounded-lg border border-white/20 bg-white/10 px-2.5 py-1.5 text-[10px] text-white/90">
          Clipboard: {clipboardPreview}
        </div>
      ) : null}
      <div className="space-y-2">
        <div className="h-2 w-[88%] rounded-full bg-white/15" />
        <div className="h-2 w-[74%] rounded-full bg-white/10" />
        <div className="h-2 w-[91%] rounded-full bg-white/15" />
        <div className="h-2 w-[82%] rounded-full bg-white/10" />
        <div className="h-2 w-[66%] rounded-full bg-white/15" />
      </div>
    </div>
  );
}

export { DocumentFallbackScene, DocumentPdfScene };
