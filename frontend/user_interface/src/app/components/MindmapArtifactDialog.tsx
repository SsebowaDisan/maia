import { useEffect, useMemo, useRef, useState } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Sparkles, X } from "lucide-react";

import {
  Dialog,
  DialogClose,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
} from "./ui/dialog";
import { MindmapViewer } from "./MindmapViewer";
import { buildMindmapArtifactSummary, describeMindmapMapType } from "./mindmapViewer/presentation";
import { toMindmapPayload } from "./mindmapViewer/viewerHelpers";
import type { FocusNodePayload, MindmapPayload } from "./mindmapViewer/types";

type MindmapArtifactDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  payload: Record<string, unknown> | null;
  conversationId?: string | null;
  onAskNode?: (payload: FocusNodePayload) => void;
  onFocusNode?: (payload: FocusNodePayload) => void;
  onSaveMap?: (payload: MindmapPayload) => void;
  onShareMap?: (payload: MindmapPayload) => Promise<string | void> | string | void;
};

function isCountNoiseSummary(value: string): boolean {
  const text = String(value || "").trim().toLowerCase();
  if (!text) {
    return false;
  }
  if (text.includes("node(s)") || text.includes("source(s)")) {
    return true;
  }
  return /^\d+\s+nodes?\s*,\s*\d+\s+sources?$/.test(text);
}

export function MindmapArtifactDialog({
  open,
  onOpenChange,
  payload,
  conversationId = null,
  onAskNode,
  onFocusNode,
  onSaveMap,
  onShareMap,
}: MindmapArtifactDialogProps) {
  const [viewerHeight, setViewerHeight] = useState(520);
  const viewerHostRef = useRef<HTMLDivElement | null>(null);
  const typedPayload = useMemo(() => toMindmapPayload(payload), [payload]);
  const summary = useMemo(() => buildMindmapArtifactSummary(typedPayload), [typedPayload]);
  const dialogSummaryText = useMemo(() => {
    if (!summary) {
      return "Explore the knowledge map in a dedicated artifact surface.";
    }
    const rawSummary = String(summary.presentation.summary || "").trim();
    if (!rawSummary || isCountNoiseSummary(rawSummary)) {
      return describeMindmapMapType(summary.activeMapType).summary;
    }
    return rawSummary;
  }, [summary]);

  useEffect(() => {
    const host = viewerHostRef.current;
    if (!host) {
      return;
    }
    const updateHeight = () => {
      const measured = Math.round(host.clientHeight || 0);
      if (measured <= 0) {
        return;
      }
      setViewerHeight(Math.max(320, measured));
    };
    updateHeight();
    const observer = new ResizeObserver(() => updateHeight());
    observer.observe(host);
    window.addEventListener("resize", updateHeight);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", updateHeight);
    };
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogPortal>
        <DialogOverlay className="bg-[#0f1014]/26 backdrop-blur-[10px]" />
        <DialogPrimitive.Content className="fixed left-1/2 top-1/2 z-50 w-[min(1180px,calc(100vw-2.5rem))] max-w-[calc(100vw-2.5rem)] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-[34px] border border-black/[0.06] bg-[#fbfbf8] shadow-[0_40px_140px_rgba(15,23,42,0.22)] duration-200 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-[0.985]">
          <div className="relative flex max-h-[calc(100vh-2rem)] min-h-[560px] flex-col overflow-hidden">
            <div className="shrink-0 border-b border-black/[0.05] bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(247,247,243,0.95))] px-6 pb-4 pt-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.88)] md:px-8 md:pb-5 md:pt-7">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="inline-flex items-center gap-2 rounded-full border border-black/[0.06] bg-white/86 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#7b8598]">
                    <Sparkles className="h-3.5 w-3.5" />
                    {summary?.presentation.eyebrow || "Research artifact"}
                  </div>
                  <DialogTitle className="mt-4 text-[30px] font-semibold tracking-[-0.05em] text-[#17171b] md:text-[36px]">
                    {summary?.title || "Knowledge map"}
                  </DialogTitle>
                  <DialogDescription className="mt-2 max-w-[52rem] text-[15px] leading-7 text-[#5e5e64]">
                    {dialogSummaryText}
                  </DialogDescription>
                </div>
                <DialogClose className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-black/[0.06] bg-white/92 text-[#4b5563] shadow-sm backdrop-blur transition-colors hover:bg-white hover:text-[#17171b]">
                  <X className="h-4.5 w-4.5" />
                  <span className="sr-only">Close</span>
                </DialogClose>
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-hidden bg-[#eef2f7]">
              <div className="h-full p-0">
                <div ref={viewerHostRef} className="h-full bg-[#eef2f7] p-0">
                  <MindmapViewer
                    payload={payload}
                    conversationId={conversationId}
                    viewerHeight={viewerHeight}
                    onAskNode={onAskNode}
                    onFocusNode={onFocusNode}
                    onSaveMap={onSaveMap}
                    onShareMap={onShareMap}
                  />
                </div>
              </div>
            </div>
          </div>
        </DialogPrimitive.Content>
      </DialogPortal>
    </Dialog>
  );
}
