import { useMemo } from "react";
import { ExternalLink, FileText } from "lucide-react";
import { buildRawFileUrl } from "../../api/client";
import type { CitationFocus } from "../types";
import { CitationPdfPreview } from "./CitationPdfPreview";

interface InfoPanelProps {
  citationFocus?: CitationFocus | null;
  indexId?: number | null;
  onClearCitationFocus?: () => void;
  width?: number;
}

export function InfoPanel({
  citationFocus = null,
  indexId = null,
  onClearCitationFocus,
  width = 340,
}: InfoPanelProps) {
  const citationRawUrl = useMemo(() => {
    if (!citationFocus?.fileId) return null;
    return buildRawFileUrl(citationFocus.fileId, {
      indexId: typeof indexId === "number" ? indexId : undefined,
    });
  }, [citationFocus, indexId]);

  const citationSourceLower = (citationFocus?.sourceName || "").toLowerCase();
  const citationIsImage = /\.(png|jpe?g|gif|bmp|webp|tiff?)$/i.test(citationSourceLower);
  const citationHasPageHint = Boolean(String(citationFocus?.page || "").trim());
  const citationIsPdf =
    Boolean(citationRawUrl) &&
    !citationIsImage &&
    (citationSourceLower.endsWith(".pdf") || citationHasPageHint || !citationSourceLower);

  return (
    <div
      className="min-h-0 bg-white/80 backdrop-blur-xl border-l border-black/[0.06] flex flex-col overflow-hidden"
      style={{ width: `${Math.round(width)}px` }}
    >
      <div className="px-5 py-4 border-b border-black/[0.06]">
        <h3 className="text-[15px] tracking-tight text-[#1d1d1f]">Information panel</h3>
      </div>

      <div id="html-info-panel" className="flex-1 overflow-y-auto px-5 py-6">
        {citationFocus ? (
          <div className="rounded-2xl border border-[#d2d2d7] bg-gradient-to-b from-white to-[#f6f7fa] p-3 shadow-sm">
            <div className="flex items-start justify-between gap-2 mb-2">
              <div className="flex items-center gap-2 min-w-0">
                <div className="w-8 h-8 rounded-lg bg-[#f2f2f7] border border-black/[0.06] flex items-center justify-center shrink-0">
                  <FileText className="w-4 h-4 text-[#3a3a3c]" />
                </div>
                <div className="min-w-0">
                  <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Citation preview</p>
                  <p className="text-[13px] text-[#1d1d1f] truncate" title={citationFocus.sourceName}>
                    {citationFocus.sourceName}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                {citationFocus.page ? (
                  <span className="text-[10px] px-2 py-1 rounded-full bg-white border border-black/[0.08] text-[#6e6e73]">
                    page {citationFocus.page}
                  </span>
                ) : null}
                {citationRawUrl ? (
                  <a
                    href={citationRawUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-[#1d1d1f] text-white text-[10px] hover:bg-[#3a3a3c] transition-colors"
                  >
                    <ExternalLink className="w-3 h-3" />
                    Open
                  </a>
                ) : null}
              </div>
            </div>

            {citationRawUrl && citationIsPdf ? (
              <CitationPdfPreview
                key={`${citationFocus?.fileId || "file"}:${citationFocus?.page || "1"}:${String(citationFocus?.extract || "").slice(0, 64)}`}
                fileUrl={citationRawUrl}
                page={citationFocus.page}
                highlightText={citationFocus.extract}
              />
            ) : null}

            {citationRawUrl && citationIsImage ? (
              <div className="w-full h-[220px] rounded-xl border border-black/[0.08] bg-white overflow-hidden flex items-center justify-center">
                <img src={citationRawUrl} alt={citationFocus.sourceName} className="max-w-full max-h-full object-contain" />
              </div>
            ) : null}

            {!citationRawUrl ? (
              <div className="rounded-xl border border-black/[0.06] bg-white p-3 text-[12px] text-[#6e6e73]">
                Source preview is unavailable for this citation.
              </div>
            ) : null}

            {onClearCitationFocus ? (
              <button
                type="button"
                onClick={onClearCitationFocus}
                className="mt-2 text-[11px] px-2.5 py-1.5 rounded-lg border border-black/[0.08] text-[#6e6e73] hover:bg-black/[0.03] transition-colors"
              >
                Close preview
              </button>
            ) : null}
          </div>
        ) : (
          <div className="rounded-xl bg-[#f5f5f7] p-4 text-[12px] text-[#6e6e73]">
            Click an inline citation in the response to preview evidence in the source file.
          </div>
        )}
      </div>
    </div>
  );
}

