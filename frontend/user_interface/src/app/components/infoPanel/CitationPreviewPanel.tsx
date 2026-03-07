import { ExternalLink, FileText } from "lucide-react";
import type { CitationFocus } from "../../types";
import { CitationPdfPreview } from "../CitationPdfPreview";

type CitationPreviewPanelProps = {
  citationFocus: CitationFocus;
  citationOpenUrl: string;
  citationRawUrl: string | null;
  citationUsesWebsite: boolean;
  citationWebsiteUrl: string;
  citationIsPdf: boolean;
  citationIsImage: boolean;
  citationViewerHeight: number;
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
  onClear,
  renderResizeHandle,
}: CitationPreviewPanelProps) {
  return (
    <div className="rounded-2xl border border-[#d2d2d7] bg-gradient-to-b from-white to-[#f6f7fa] p-3 shadow-sm">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-black/[0.06] bg-[#f2f2f7]">
            <FileText className="h-4 w-4 text-[#3a3a3c]" />
          </div>
          <div className="min-w-0">
            <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">
              {citationUsesWebsite ? "Website citation" : "Citation preview"}
            </p>
            <p className="truncate text-[13px] text-[#1d1d1f]" title={citationFocus.sourceName}>
              {citationFocus.sourceName}
            </p>
          </div>
        </div>
        {citationOpenUrl ? (
          <a
            href={citationOpenUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex shrink-0 items-center gap-1 rounded-lg bg-[#1d1d1f] px-2.5 py-1.5 text-[10px] text-white transition-colors hover:bg-[#3a3a3c]"
          >
            <ExternalLink className="h-3 w-3" />
            Open
          </a>
        ) : null}
      </div>

      {citationRawUrl && citationIsPdf ? (
        <CitationPdfPreview
          key={`${citationFocus.fileId || "file"}:${citationFocus.page || "1"}:${String(citationFocus.extract || "").slice(0, 64)}`}
          fileUrl={citationRawUrl}
          page={citationFocus.page}
          highlightText={citationFocus.extract || citationFocus.claimText || ""}
          highlightQuery={citationFocus.claimText}
          highlightBoxes={citationFocus.highlightBoxes}
          viewerHeight={citationViewerHeight}
        />
      ) : null}

      {citationRawUrl && citationIsImage ? (
        <div
          className="flex w-full items-center justify-center overflow-hidden rounded-xl border border-black/[0.08] bg-white"
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
        <div className="space-y-2 rounded-xl border border-black/[0.06] bg-white p-3 text-[12px] text-[#3a3a3c]">
          <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Website extract</p>
          <p className="leading-[1.45]">
            {String(citationFocus.extract || citationFocus.claimText || "Website citation selected.")
              .replace(/\s+/g, " ")
              .trim()}
          </p>
          {citationWebsiteUrl ? (
            <a
              href={citationWebsiteUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-[11px] text-[#0a66d9] hover:text-[#0750ab]"
            >
              <ExternalLink className="h-3 w-3" />
              Open website source
            </a>
          ) : null}
        </div>
      ) : null}

      {!citationUsesWebsite && !citationRawUrl ? (
        <div className="rounded-xl border border-black/[0.06] bg-white p-3 text-[12px] text-[#6e6e73]">
          Source preview is unavailable for this citation.
        </div>
      ) : null}

      {citationIsPdf || citationIsImage ? renderResizeHandle() : null}

      {onClear ? (
        <button
          type="button"
          onClick={onClear}
          className="mt-2 rounded-lg border border-black/[0.08] px-2.5 py-1.5 text-[11px] text-[#6e6e73] transition-colors hover:bg-black/[0.03]"
        >
          Close preview
        </button>
      ) : null}
    </div>
  );
}

export { CitationPreviewPanel };
