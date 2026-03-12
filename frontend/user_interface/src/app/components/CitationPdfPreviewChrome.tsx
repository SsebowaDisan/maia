import { ChevronLeft, ChevronRight, ExternalLink, Loader2 } from "lucide-react";

export function buildPdfPageUrl(fileUrl: string, pageNumber: number): string {
  try {
    const base = typeof window !== "undefined" ? window.location.origin : "http://127.0.0.1";
    const resolved = new URL(fileUrl, base);
    resolved.hash = `page=${Math.max(1, Math.round(pageNumber))}`;
    return resolved.toString();
  } catch {
    return fileUrl;
  }
}

export function PageLoadingState() {
  return (
    <div className="flex min-h-[440px] w-full min-w-[240px] items-center justify-center rounded-[14px] bg-[#fbfbfd] text-[#6e6e73]">
      <div className="flex flex-col items-center gap-2">
        <Loader2 className="h-4 w-4 animate-spin" />
        <p className="text-[11px] font-medium">Rendering page preview</p>
      </div>
    </div>
  );
}

export function PageFallbackState({
  fileUrl,
  pageNumber,
  stalled = false,
}: {
  fileUrl: string;
  pageNumber: number;
  stalled?: boolean;
}) {
  return (
    <div className="flex min-h-[440px] w-full min-w-[240px] items-center justify-center rounded-[14px] bg-[#fbfbfd] px-6 text-center">
      <div className="max-w-[280px] space-y-3">
        <p className="text-[12px] font-medium text-[#1d1d1f]">
          {stalled ? "Page preview is taking too long." : "Unable to render this PDF page."}
        </p>
        <p className="text-[11px] leading-5 text-[#6e6e73]">
          Open the document directly if you need the full page immediately.
        </p>
        <a
          href={buildPdfPageUrl(fileUrl, pageNumber)}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 rounded-full border border-black/[0.08] bg-white px-3 py-1.5 text-[11px] font-medium text-[#1d1d1f] transition-colors hover:bg-[#f3f3f5]"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          Open document
        </a>
      </div>
    </div>
  );
}

type PdfPreviewToolbarProps = {
  currentPage: number;
  numPages: number;
  zoomLevel: number;
  onPreviousPage: () => void;
  onNextPage: () => void;
  onZoomOut: () => void;
  onZoomIn: () => void;
  onResetZoom: () => void;
};

export function PdfPreviewToolbar({
  currentPage,
  numPages,
  zoomLevel,
  onPreviousPage,
  onNextPage,
  onZoomOut,
  onZoomIn,
  onResetZoom,
}: PdfPreviewToolbarProps) {
  return (
    <div className="flex h-8 items-center justify-between border-b border-black/[0.06] bg-[#f8f8fa] px-2.5">
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={onPreviousPage}
          disabled={currentPage <= 1}
          className="rounded-md p-1 text-[#6e6e73] hover:bg-black/[0.05] disabled:opacity-30"
          aria-label="Previous page"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          onClick={onZoomOut}
          className="rounded-md border border-black/[0.08] px-1.5 py-0.5 text-[10px] text-[#4c4c50] hover:bg-black/[0.03]"
          aria-label="Zoom out"
        >
          -
        </button>
      </div>
      <p className="text-[10px] text-[#6e6e73]">
        Page {currentPage} of {numPages} | {Math.round(zoomLevel * 100)}%
      </p>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={onZoomIn}
          className="rounded-md border border-black/[0.08] px-1.5 py-0.5 text-[10px] text-[#4c4c50] hover:bg-black/[0.03]"
          aria-label="Zoom in"
        >
          +
        </button>
        <button
          type="button"
          onClick={onResetZoom}
          className="rounded-md border border-black/[0.08] px-1.5 py-0.5 text-[10px] text-[#4c4c50] hover:bg-black/[0.03]"
          aria-label="Reset zoom"
        >
          1x
        </button>
        <button
          type="button"
          onClick={onNextPage}
          disabled={currentPage >= numPages}
          className="rounded-md p-1 text-[#6e6e73] hover:bg-black/[0.05] disabled:opacity-30"
          aria-label="Next page"
        >
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
