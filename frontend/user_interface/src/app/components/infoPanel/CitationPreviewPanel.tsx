import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, ExternalLink, Loader2, X } from "lucide-react";
import { getPdfHighlightTargetCached } from "../../../api/client/uploads";
import type { CitationFocus } from "../../types";
import { CitationPdfPreview } from "../CitationPdfPreview";
import { WidgetRenderBoundary } from "../messages/WidgetRenderBoundary";
import { WebReviewViewer } from "./review/WebReviewViewer";
import type { WebReviewSource } from "./review/webReviewContent";

type CitationPreviewPanelProps = {
  citationFocus: CitationFocus;
  citationOpenUrl: string;
  citationRawUrl: string | null;
  citationUsesWebsite: boolean;
  citationWebsiteUrl: string;
  citationIsPdf: boolean;
  citationIsImage: boolean;
  citationViewerHeight: number;
  reviewQuery?: string;
  preferredPage?: string;
  webReviewSource?: WebReviewSource | null;
  hasPreviousEvidence: boolean;
  hasNextEvidence: boolean;
  onPreviousEvidence: () => void;
  onNextEvidence: () => void;
  pdfZoom: number;
  onPdfZoomChange: (next: number) => void;
  onPdfPageChange?: (nextPage: number) => void;
  onClear?: () => void;
  renderResizeHandle: () => React.ReactNode;
};

function CitationPreviewPanel({
  citationFocus,
  citationOpenUrl,
  citationRawUrl,
  citationUsesWebsite,
  citationWebsiteUrl,
  citationIsPdf,
  citationIsImage,
  citationViewerHeight,
  reviewQuery = "",
  preferredPage,
  webReviewSource = null,
  hasPreviousEvidence,
  hasNextEvidence,
  onPreviousEvidence,
  onNextEvidence,
  pdfZoom,
  onPdfZoomChange,
  onPdfPageChange,
  onClear,
  renderResizeHandle,
}: CitationPreviewPanelProps) {
  const hasInlineGeometry =
    Boolean(citationFocus.highlightBoxes?.length) || Boolean(citationFocus.evidenceUnits?.length);
  const backfillPage = preferredPage || citationFocus.page;
  const backfillText = citationFocus.extract || citationFocus.claimText || "";
  const [resolvedGeometry, setResolvedGeometry] = useState<{
    highlightBoxes: CitationFocus["highlightBoxes"];
    evidenceUnits: CitationFocus["evidenceUnits"];
    traceId?: string;
  } | null>(null);
  const [isResolvingGeometry, setIsResolvingGeometry] = useState(false);
  const [sourceUnavailableReason, setSourceUnavailableReason] = useState<string>("");

  useEffect(() => {
    setResolvedGeometry(null);
    setIsResolvingGeometry(false);
    setSourceUnavailableReason("");
  }, [citationFocus.evidenceId, citationFocus.fileId, citationFocus.page, preferredPage]);

  useEffect(() => {
    let cancelled = false;
    if (!citationIsPdf || !citationRawUrl || !citationFocus.fileId || !backfillPage || !backfillText || hasInlineGeometry) {
      return () => {
        cancelled = true;
      };
    }
    setIsResolvingGeometry(true);
    getPdfHighlightTargetCached(citationFocus.fileId, {
      page: backfillPage,
      text: citationFocus.extract || "",
      claim_text: citationFocus.claimText || "",
      chunk_id: citationFocus.chunkId || "",
    })
      .then((result) => {
        if (cancelled) {
          return;
        }
        const highlightBoxes = Array.isArray(result.highlight_boxes)
          ? result.highlight_boxes.map((item) => ({
              x: Number(item.x) || 0,
              y: Number(item.y) || 0,
              width: Number(item.width) || 0,
              height: Number(item.height) || 0,
            }))
          : [];
        const evidenceUnits = Array.isArray(result.evidence_units)
          ? result.evidence_units.map((unit) => ({
              text: String(unit.text || ""),
              charStart:
                typeof unit.char_start === "number" && Number.isFinite(unit.char_start)
                  ? unit.char_start
                  : undefined,
              charEnd:
                typeof unit.char_end === "number" && Number.isFinite(unit.char_end)
                  ? unit.char_end
                  : undefined,
              highlightBoxes: Array.isArray(unit.highlight_boxes)
                ? unit.highlight_boxes.map((item) => ({
                    x: Number(item.x) || 0,
                    y: Number(item.y) || 0,
                    width: Number(item.width) || 0,
                    height: Number(item.height) || 0,
                  }))
                : [],
            }))
          : [];
        setResolvedGeometry({
          highlightBoxes,
          evidenceUnits,
          traceId: String(result.trace_id || "").trim() || undefined,
        });
        setSourceUnavailableReason("");
        setIsResolvingGeometry(false);
      })
      .catch((error) => {
        if (!cancelled) {
          const message = String((error as Error | undefined)?.message || "").toLowerCase();
          if (message.includes("404") || message.includes("not found")) {
            setSourceUnavailableReason("Source file is no longer available for this citation.");
          }
          setResolvedGeometry({
            highlightBoxes: [],
            evidenceUnits: [],
            traceId: undefined,
          });
          setIsResolvingGeometry(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [
    backfillPage,
    backfillText,
    citationFocus.claimText,
    citationFocus.chunkId,
    citationFocus.extract,
    citationFocus.fileId,
    citationIsPdf,
    citationRawUrl,
    hasInlineGeometry,
  ]);

  const effectiveHighlightBoxes = useMemo(() => {
    if (citationFocus.highlightBoxes?.length) {
      return citationFocus.highlightBoxes;
    }
    return resolvedGeometry?.highlightBoxes || [];
  }, [citationFocus.highlightBoxes, resolvedGeometry?.highlightBoxes]);

  const effectiveEvidenceUnits = useMemo(() => {
    if (citationFocus.evidenceUnits?.length) {
      return citationFocus.evidenceUnits;
    }
    return resolvedGeometry?.evidenceUnits || [];
  }, [citationFocus.evidenceUnits, resolvedGeometry?.evidenceUnits]);

  const highlightTraceId = useMemo(
    () => String(resolvedGeometry?.traceId || "").trim(),
    [resolvedGeometry?.traceId],
  );

  return (
    <div className="overflow-hidden rounded-2xl border border-[#d2d2d7] bg-white shadow-sm">
      {/* Header: source name + nav + open */}
      <div className="flex items-center gap-2 border-b border-black/[0.06] bg-[#f8f8fb] px-3 py-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-[12px] font-medium text-[#1d1d1f]" title={citationFocus.sourceName}>
            {citationFocus.sourceName}
          </p>
          {citationFocus.page ? (
            <p className="text-[10px] text-[#8e8e93]">Page {citationFocus.page}</p>
          ) : null}
        </div>

        {/* Prev / Next */}
        <div className="flex items-center gap-0.5">
          <button
            type="button"
            onClick={onPreviousEvidence}
            disabled={!hasPreviousEvidence}
            title="Previous citation"
            className="rounded-md p-1 text-[#4c4c50] hover:bg-black/[0.06] disabled:opacity-30"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={onNextEvidence}
            disabled={!hasNextEvidence}
            title="Next citation"
            className="rounded-md p-1 text-[#4c4c50] hover:bg-black/[0.06] disabled:opacity-30"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Open in new tab (with text-fragment deep link) */}
        {citationOpenUrl ? (
          <a
            href={citationOpenUrl}
            target="_blank"
            rel="noopener noreferrer"
            title="Open source page at this passage"
            className="inline-flex shrink-0 items-center gap-1 rounded-lg bg-[#1d1d1f] px-2 py-1 text-[10px] text-white transition-colors hover:bg-[#3a3a3c]"
          >
            <ExternalLink className="h-3 w-3" />
            Open
          </a>
        ) : null}

        {/* Close */}
        {onClear ? (
          <button
            type="button"
            onClick={onClear}
            title="Close preview"
            className="rounded-md p-1 text-[#8e8e93] hover:bg-black/[0.06] hover:text-[#3a3a3c]"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        ) : null}
      </div>

      {/* Content */}
      <div className="p-3">
        {citationIsPdf && isResolvingGeometry && !hasInlineGeometry ? (
          <div className="mb-3 flex items-center gap-2 rounded-xl border border-[#eadfbe] bg-[#fff9eb] px-3 py-2 text-[12px] text-[#7a5a12]">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            <span>Locating the cited passage and preparing the highlight…</span>
          </div>
        ) : null}
        {highlightTraceId ? (
          <div className="mb-3 rounded-xl border border-black/[0.06] bg-[#f8f8fb] px-3 py-2 text-[11px] text-[#6b7280]">
            Highlight trace: <span className="font-mono text-[#111827]">{highlightTraceId}</span>
          </div>
        ) : null}
        {sourceUnavailableReason ? (
          <div className="rounded-xl border border-[#fecaca] bg-[#fff1f2] p-3 text-[12px] text-[#9f1239]">
            {sourceUnavailableReason}
          </div>
        ) : null}
        {citationRawUrl && citationIsPdf && !sourceUnavailableReason ? (
          <WidgetRenderBoundary
            fallback={
              <div className="rounded-xl border border-[#fecaca] bg-[#fff1f2] p-3 text-[12px] text-[#9f1239]">
                PDF preview failed to render. Use <span className="font-medium">Open</span> to inspect the source directly.
              </div>
            }
          >
            <CitationPdfPreview
              key={`${citationFocus.fileId || "file"}:${preferredPage || citationFocus.page || "1"}:${String(citationFocus.extract || "").slice(0, 64)}`}
              fileUrl={citationRawUrl}
              page={preferredPage || citationFocus.page}
              highlightText={citationFocus.extract || citationFocus.claimText || ""}
              highlightQuery={citationFocus.claimText || ""}
              charStart={citationFocus.charStart}
              charEnd={citationFocus.charEnd}
              highlightBoxes={effectiveHighlightBoxes}
              evidenceUnits={effectiveEvidenceUnits}
              viewerHeight={citationViewerHeight}
              initialZoom={pdfZoom}
              onZoomChange={onPdfZoomChange}
              onPageChange={onPdfPageChange}
            />
          </WidgetRenderBoundary>
        ) : null}

        {citationRawUrl && citationIsImage ? (
          <div
            className="flex w-full items-center justify-center overflow-hidden rounded-xl border border-black/[0.08] bg-[#f5f5f7]"
            style={{ height: `${Math.max(320, citationViewerHeight)}px` }}
          >
            <img
              src={citationRawUrl}
              alt={citationFocus.sourceName}
              className="max-h-full max-w-full object-contain"
            />
          </div>
        ) : null}

        {citationUsesWebsite ? (
          <WebReviewViewer
            sourceTitle={citationFocus.sourceName}
            sourceUrl={citationWebsiteUrl}
            reviewQuery={reviewQuery || citationFocus.claimText || ""}
            focusText={citationFocus.extract || citationFocus.claimText || ""}
            focusSelector={citationFocus.selector}
            reviewSource={webReviewSource}
            viewerHeight={citationViewerHeight}
          />
        ) : null}

        {!citationUsesWebsite && !citationRawUrl ? (
          <div className="rounded-xl border border-black/[0.06] bg-[#f5f5f7] p-3 text-[12px] text-[#6e6e73]">
            Source preview is unavailable for this citation.
          </div>
        ) : null}

        {citationIsPdf || citationIsImage || citationUsesWebsite ? renderResizeHandle() : null}

      </div>
    </div>
  );
}

export { CitationPreviewPanel };
