import { FileText } from "lucide-react";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "../ui/sheet";
import { useCanvasStore } from "../../stores/canvasStore";

function CanvasPanel() {
  const isOpen = useCanvasStore((state) => state.isOpen);
  const activeDocumentId = useCanvasStore((state) => state.activeDocumentId);
  const documentsById = useCanvasStore((state) => state.documentsById);
  const closePanel = useCanvasStore((state) => state.closePanel);
  const updateDocumentContent = useCanvasStore((state) => state.updateDocumentContent);
  const activeDocument = activeDocumentId ? documentsById[activeDocumentId] || null : null;

  return (
    <Sheet open={isOpen} onOpenChange={(open) => !open && closePanel()}>
      <SheetContent
        side="right"
        className="w-[min(92vw,760px)] min-w-0 gap-0 border-l border-black/[0.08] bg-[#fbfbfd] p-0 sm:min-w-[380px] sm:max-w-[760px]"
      >
        <SheetHeader className="border-b border-black/[0.06] px-6 py-5">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#111827] text-white shadow-[0_10px_30px_rgba(17,24,39,0.18)]">
              <FileText className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <SheetTitle className="truncate text-[18px] font-semibold text-[#111827]">
                {activeDocument?.title || "Canvas draft"}
              </SheetTitle>
              <SheetDescription className="text-[12px] text-[#667085]">
                Draft in markdown. Changes remain local until a save flow is added.
              </SheetDescription>
            </div>
          </div>
        </SheetHeader>

        <div className="flex min-h-0 flex-1 flex-col px-6 py-5">
          {activeDocument ? (
            <textarea
              value={activeDocument.content}
              onChange={(event) => updateDocumentContent(activeDocument.id, event.target.value)}
              className="min-h-0 flex-1 resize-none rounded-[28px] border border-black/[0.08] bg-white px-5 py-4 font-[ui-monospace,SFMono-Regular,Menlo,monospace] text-[13px] leading-6 text-[#111827] shadow-[0_16px_40px_rgba(15,23,42,0.06)] outline-none transition focus:border-[#98a2b3] focus:ring-2 focus:ring-[#dbeafe]"
              spellCheck={false}
            />
          ) : (
            <div className="flex flex-1 items-center justify-center rounded-[28px] border border-dashed border-black/[0.08] bg-white/70 text-center text-[13px] text-[#667085]">
              Select a document action from the chat to open a draft here.
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

export { CanvasPanel };
