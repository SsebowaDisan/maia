import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

interface CitationPdfPreviewProps {
  fileUrl: string;
  page?: string;
  highlightText: string;
}

function escapeRegExp(input: string): string {
  return input.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function extractHighlightTerms(text: string): string[] {
  const tokens = text
    .toLowerCase()
    .split(/[^a-z0-9]+/i)
    .map((token) => token.trim())
    .filter((token) => token.length >= 4);
  return Array.from(new Set(tokens)).slice(0, 16);
}

export function CitationPdfPreview({ fileUrl, page, highlightText }: CitationPdfPreviewProps) {
  const requestedPage = Number.parseInt(String(page || "1"), 10);
  const [numPages, setNumPages] = useState(1);
  const [currentPage, setCurrentPage] = useState(
    Number.isFinite(requestedPage) && requestedPage > 0 ? requestedPage : 1,
  );
  const highlightTerms = useMemo(() => extractHighlightTerms(highlightText), [highlightText]);

  const customTextRenderer = ({ str }: { str: string }) => {
    if (!highlightTerms.length || !str) {
      return str;
    }
    let highlighted = str;
    for (const term of highlightTerms) {
      const regex = new RegExp(`(${escapeRegExp(term)})`, "gi");
      highlighted = highlighted.replace(
        regex,
        `<mark class="citation-pdf-hit">$1</mark>`,
      );
    }
    return highlighted;
  };

  return (
    <div className="citation-pdf rounded-xl border border-black/[0.08] bg-white overflow-hidden">
      <div className="h-8 px-2.5 flex items-center justify-between border-b border-black/[0.06] bg-[#f8f8fa]">
        <button
          type="button"
          onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
          disabled={currentPage <= 1}
          className="p-1 rounded-md text-[#6e6e73] hover:bg-black/[0.05] disabled:opacity-30"
          aria-label="Previous page"
        >
          <ChevronLeft className="w-3.5 h-3.5" />
        </button>
        <p className="text-[10px] text-[#6e6e73]">
          Page {currentPage} of {numPages}
        </p>
        <button
          type="button"
          onClick={() => setCurrentPage((prev) => Math.min(numPages, prev + 1))}
          disabled={currentPage >= numPages}
          className="p-1 rounded-md text-[#6e6e73] hover:bg-black/[0.05] disabled:opacity-30"
          aria-label="Next page"
        >
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="h-[260px] overflow-auto bg-[#f2f2f7] p-2">
        <Document
          file={fileUrl}
          onLoadSuccess={({ numPages: loadedPages }) => {
            const safePages = loadedPages > 0 ? loadedPages : 1;
            setNumPages(safePages);
            setCurrentPage((prev) => Math.min(Math.max(1, prev), safePages));
          }}
          loading={
            <div className="h-[240px] flex items-center justify-center text-[#6e6e73]">
              <Loader2 className="w-4 h-4 animate-spin" />
            </div>
          }
          error={
            <div className="h-[240px] flex items-center justify-center px-4 text-center text-[11px] text-[#6e6e73]">
              Unable to render PDF preview.
            </div>
          }
        >
          <Page
            pageNumber={currentPage}
            width={292}
            renderAnnotationLayer
            renderTextLayer
            customTextRenderer={customTextRenderer}
          />
        </Document>
      </div>
    </div>
  );
}
