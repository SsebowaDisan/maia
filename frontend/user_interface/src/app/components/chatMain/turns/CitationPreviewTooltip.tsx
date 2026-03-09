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
      className="citation-peek-tooltip pointer-events-none fixed z-[130] text-left"
      style={{
        left: preview.left,
        top: preview.top,
        width: preview.width,
        transform: preview.placeAbove ? "translate(-50%, -100%)" : "translate(-50%, 0)",
      }}
    >
      <div className="citation-peek-meta">
        {preview.citationRef ? (
          <span className="citation-peek-pill citation-peek-pill--reference">
            {preview.citationRef}
          </span>
        ) : null}
        <span className="citation-peek-source truncate" title={preview.sourceName}>
          {preview.sourceName}
        </span>
        {preview.page ? (
          <span className="citation-peek-pill shrink-0">
            p. {preview.page}
          </span>
        ) : null}
        {preview.strengthLabel ? (
          <span className="citation-peek-pill shrink-0">
            {preview.strengthLabel}
          </span>
        ) : null}
      </div>
      <p className="citation-peek-tooltip-text citation-peek-snippet text-[12px] leading-[1.48]">
        {preview.extract}
      </p>
    </div>
  );
}

export type { CitationPreview };
export { CitationPreviewTooltip };
