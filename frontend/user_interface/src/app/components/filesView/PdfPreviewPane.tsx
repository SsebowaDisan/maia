import type { RefObject } from "react";
import type { FileRecord } from "../../../api/client";

interface PdfPreviewPaneProps {
  selectedPdfPreviewUrl: string | null;
  selectedPdfFile: FileRecord | null;
  selectedCount: number;
  pdfPreviewRef: RefObject<HTMLDivElement | null>;
}

function PdfPreviewPane({
  selectedPdfPreviewUrl,
  selectedPdfFile,
  selectedCount,
  pdfPreviewRef,
}: PdfPreviewPaneProps) {
  if (selectedPdfPreviewUrl) {
    return (
      <div
        ref={pdfPreviewRef}
        className="flex min-h-[420px] flex-col overflow-hidden rounded-2xl border border-black/[0.08] bg-white shadow-sm xl:h-[calc(100vh-7.5rem)] xl:min-h-0"
      >
        <div className="border-b border-black/[0.06] bg-[#fafafa] px-4 py-3">
          <p className="text-[12px] text-[#6e6e73]">PDF Preview</p>
          <p className="truncate text-[13px] font-medium text-[#1d1d1f]">{selectedPdfFile?.name}</p>
        </div>
        <iframe title="Selected PDF preview" src={selectedPdfPreviewUrl} className="flex-1 w-full bg-white" />
      </div>
    );
  }

  if (selectedCount > 0) {
    return (
      <div
        ref={pdfPreviewRef}
        className="rounded-2xl border border-black/[0.08] bg-white p-5 text-[13px] text-[#6e6e73]"
      >
        PDF preview is available when the current selection includes at least one PDF.
      </div>
    );
  }

  return null;
}

export { PdfPreviewPane };
