import { FileText, X } from "lucide-react";
import { useEffect } from "react";
import type { FileRecord } from "../../../api/client";

interface PdfPreviewModalProps {
  isOpen: boolean;
  selectedPdfPreviewUrl: string | null;
  selectedPdfFile: FileRecord | null;
  onClose: () => void;
}

function PdfPreviewModal({
  isOpen,
  selectedPdfPreviewUrl,
  selectedPdfFile,
  onClose,
}: PdfPreviewModalProps) {
  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !selectedPdfPreviewUrl) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-[180] flex items-center justify-center bg-black/30 p-4 backdrop-blur-[10px] sm:p-6" onClick={onClose}>
      <div
        className="flex h-[min(92vh,960px)] w-full max-w-[1180px] min-h-[520px] flex-col overflow-hidden rounded-[28px] border border-white/75 bg-white shadow-[0_36px_112px_-40px_rgba(0,0,0,0.68)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-black/[0.08] bg-[#f8f8fa] px-5 py-3">
          <div className="min-w-0">
            <p className="text-[12px] text-[#6e6e73]">PDF Preview</p>
            <div className="mt-1 flex min-w-0 items-center gap-2">
              <FileText className="h-4 w-4 shrink-0 text-[#5a5a60]" />
              <p className="truncate text-[13px] font-medium text-[#1d1d1f]">{selectedPdfFile?.name}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-black/[0.08] text-[#6e6e73] transition-colors hover:bg-white hover:text-[#1d1d1f]"
            aria-label="Close PDF preview"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <iframe title="Selected PDF preview" src={selectedPdfPreviewUrl} className="h-full w-full flex-1 bg-white" />
      </div>
    </div>
  );
}

export { PdfPreviewModal };
