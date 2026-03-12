import { useEffect, useMemo, useState } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { GitBranch, Layers3, Sparkles, X } from "lucide-react";

import {
  Dialog,
  DialogClose,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
} from "./ui/dialog";
import { MindmapViewer } from "./MindmapViewer";
import { buildMindmapArtifactSummary } from "./mindmapViewer/presentation";
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
  const [viewerHeight, setViewerHeight] = useState(720);
  const typedPayload = useMemo(() => toMindmapPayload(payload), [payload]);
  const summary = useMemo(() => buildMindmapArtifactSummary(typedPayload), [typedPayload]);
  const mapTypePills = summary?.availableMapTypes || [];
  const compactMeta = [summary?.nodeCount ? `${summary.nodeCount} nodes` : null]
    .filter(Boolean)
    .join(" • ");

  useEffect(() => {
    const updateHeight = () => {
      const next = Math.max(520, Math.min(860, Math.round(window.innerHeight * 0.66)));
      setViewerHeight(next);
    };
    updateHeight();
    window.addEventListener("resize", updateHeight);
    return () => window.removeEventListener("resize", updateHeight);
  }, []);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogPortal>
        <DialogOverlay className="bg-[#0f1014]/26 backdrop-blur-[18px]" />
        <DialogPrimitive.Content className="fixed left-1/2 top-1/2 z-50 w-[min(1180px,calc(100vw-2.5rem))] max-w-[calc(100vw-2.5rem)] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-[34px] border border-black/[0.06] bg-[#fbfbf8] shadow-[0_40px_140px_rgba(15,23,42,0.22)] duration-200 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-[0.985]">
          <div className="relative max-h-[calc(100vh-2rem)] overflow-hidden">
            <div className="max-h-[calc(100vh-2rem)] overflow-y-auto">
              <div className="border-b border-black/[0.05] bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(247,247,243,0.95))] px-6 pb-4 pt-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.88)] md:px-8 md:pb-5 md:pt-7">
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
                      {summary?.presentation.summary || "Explore the knowledge map in a dedicated artifact surface."}
                    </DialogDescription>
                    {(mapTypePills.length > 0 || compactMeta) ? (
                      <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] font-medium text-[#747a86]">
                        {mapTypePills.map((mapType) => (
                          <span key={mapType} className="inline-flex items-center gap-1.5 rounded-full border border-black/[0.05] bg-white/72 px-2.5 py-1">
                            <Layers3 className="h-3.5 w-3.5 text-[#8b93a2]" />
                            {mapType === "context_mindmap"
                              ? "Sources"
                              : mapType === "work_graph"
                                ? "Execution"
                                : mapType === "evidence"
                                  ? "Evidence"
                                  : "Concept"}
                          </span>
                        ))}
                        {compactMeta ? (
                          <span className="inline-flex items-center gap-1.5 rounded-full border border-black/[0.05] bg-white/72 px-2.5 py-1">
                            <GitBranch className="h-3.5 w-3.5 text-[#8b93a2]" />
                            {compactMeta}
                          </span>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                  <DialogClose className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-black/[0.06] bg-white/92 text-[#4b5563] shadow-sm backdrop-blur transition-colors hover:bg-white hover:text-[#17171b]">
                    <X className="h-4.5 w-4.5" />
                    <span className="sr-only">Close</span>
                  </DialogClose>
                </div>
              </div>

              <div className="px-5 pb-5 pt-4 md:px-6 md:pb-6 md:pt-5">
                <div className="rounded-[30px] border border-black/[0.05] bg-[#f3f4ef] p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] md:p-4">
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
