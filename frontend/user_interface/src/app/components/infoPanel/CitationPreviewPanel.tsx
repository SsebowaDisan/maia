import { ChevronLeft, ChevronRight, ExternalLink, X } from "lucide-react";
import type { CitationFocus } from "../../types";
import type { EvidenceCard } from "../../utils/infoInsights";
import { CitationPdfPreview } from "../CitationPdfPreview";
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
        {citationRawUrl && citationIsPdf ? (
          <CitationPdfPreview
            key={`${citationFocus.fileId || "file"}:${preferredPage || citationFocus.page || "1"}:${String(citationFocus.extract || "").slice(0, 64)}`}
            fileUrl={citationRawUrl}
            page={preferredPage || citationFocus.page}
            highlightText={citationFocus.extract || citationFocus.claimText || ""}
            highlightQuery={reviewQuery || citationFocus.claimText}
            highlightBoxes={citationFocus.highlightBoxes}
            viewerHeight={citationViewerHeight}
            initialZoom={pdfZoom}
            onZoomChange={onPdfZoomChange}
            onPageChange={onPdfPageChange}
          />
        ) : null}

        {citationRawUrl && citationIsImage ? (
          <div
            className="flex w-full items-center justify-center overflow-hidden rounded-xl border border-black/[0.08] bg-[#f5f5f7]"
            style={{ height: `${Math.max(220, citationViewerHeight)}px` }}
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
