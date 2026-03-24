import { FileText } from "lucide-react";

import { Sheet, SheetContent } from "../ui/sheet";
import { useCanvasStore } from "../../stores/canvasStore";
import type { CitationFocus } from "../../types";
import { CanvasWorkspaceSurface } from "./CanvasWorkspaceSurface";

type CanvasPanelProps = {
  onSelectCitationFocus?: (citation: CitationFocus) => void;
};

function CanvasPanel({ onSelectCitationFocus }: CanvasPanelProps) {
  const isOpen = useCanvasStore((state) => state.isOpen);
  const activeDocumentId = useCanvasStore((state) => state.activeDocumentId);
  const closePanel = useCanvasStore((state) => state.closePanel);

  return (
    <Sheet open={isOpen} onOpenChange={(open) => !open && closePanel()}>
      <SheetContent
        side="right"
        className="w-[min(92vw,820px)] min-w-0 gap-0 border-l border-black/[0.08] bg-[#fbfbfd] p-0 sm:min-w-[420px] sm:max-w-[820px]"
      >
        <div className="flex min-h-0 flex-1 flex-col p-6">
          {activeDocumentId ? (
            <CanvasWorkspaceSurface
              documentId={activeDocumentId}
              onSelectCitationFocus={onSelectCitationFocus}
            />
          ) : (
            <div className="flex flex-1 items-center justify-center rounded-[28px] border border-dashed border-black/[0.08] bg-white/70 px-6 text-center text-[13px] text-[#667085]">
              <div className="space-y-2">
                <span className="mx-auto flex h-10 w-10 items-center justify-center rounded-2xl bg-[#111827] text-white shadow-[0_10px_30px_rgba(17,24,39,0.18)]">
                  <FileText className="h-4 w-4" />
                </span>
                <p>Select a document action from the chat to open a draft here.</p>
              </div>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

export { CanvasPanel };
