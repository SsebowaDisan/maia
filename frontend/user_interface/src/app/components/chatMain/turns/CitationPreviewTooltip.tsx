type CitationPreview = {
  left: number;
  top: number;
  width: number;
  placeAbove: boolean;
  sourceName: string;
  page?: string;
  extract: string;
  strengthLabel?: string;
  citationRef?: string;
};

type CitationPreviewTooltipProps = {
  preview: CitationPreview | null;
};

function CitationPreviewTooltip({ preview }: CitationPreviewTooltipProps) {
  if (!preview) {
    return null;
  }

  return (
    <div
      role="tooltip"
      aria-live="polite"
      className="citation-peek-tooltip pointer-events-none fixed z-[130] rounded-xl border border-[#d4d9e4] bg-white/98 p-3 text-left shadow-[0_22px_46px_-26px_rgba(18,28,45,0.55)] backdrop-blur-[1px]"
      style={{
        left: preview.left,
        top: preview.top,
        width: preview.width,
        transform: preview.placeAbove ? "translate(-50%, -100%)" : "translate(-50%, 0)",
      }}
    >
      <div className="mb-1.5 flex items-center gap-2 text-[10px] text-[#5f6472]">
        {preview.citationRef ? (
          <span className="rounded-full border border-[#ccd3e2] bg-[#f5f7fb] px-2 py-0.5 font-semibold text-[#2f3a51]">
            {preview.citationRef}
          </span>
        ) : null}
        <span className="truncate" title={preview.sourceName}>
          {preview.sourceName}
        </span>
        {preview.page ? (
          <span className="shrink-0 rounded-full border border-black/[0.08] bg-white px-1.5 py-0.5 text-[#6e6e73]">
            p. {preview.page}
          </span>
        ) : null}
        {preview.strengthLabel ? (
          <span className="shrink-0 rounded-full border border-black/[0.08] bg-white px-1.5 py-0.5 text-[#6e6e73]">
            {preview.strengthLabel}
          </span>
        ) : null}
      </div>
      <p className="citation-peek-tooltip-text citation-peek-snippet text-[12px] leading-[1.45] text-[#1e2532]">
        {preview.extract}
      </p>
    </div>
  );
}

export type { CitationPreview };
export { CitationPreviewTooltip };
