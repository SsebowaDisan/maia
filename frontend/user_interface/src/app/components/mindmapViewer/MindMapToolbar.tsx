import { Expand, FileDown, Maximize2, Minimize2, Share2 } from "lucide-react";

import type { MindmapMapType } from "./types";

type MindMapToolbarProps = {
  activeMapType: MindmapMapType;
  availableMapTypes: MindmapMapType[];
  maxDepth: number;
  showReasoningMap: boolean;
  hasReasoningMap: boolean;
  focusNodeId: string | null;
  onSwitchMapType: (mapType: MindmapMapType) => void;
  onExpand: () => void;
  onCollapse: () => void;
  onFitView: () => void;
  onMaxDepthChange: (depth: number) => void;
  onToggleReasoningMap: () => void;
  onClearFocus: () => void;
  onExportPng: () => void;
  onExportJson: () => void;
  onExportMarkdown: () => void;
  onSave: () => void;
  onShare: () => void | Promise<void>;
};

const MAP_TYPE_LABELS: Record<MindmapMapType, string> = {
  structure: "Concept",
  evidence: "Evidence",
  work_graph: "Execution",
  context_mindmap: "Sources",
};

export function MindMapToolbar({
  activeMapType,
  availableMapTypes,
  maxDepth,
  showReasoningMap,
  hasReasoningMap,
  focusNodeId,
  onSwitchMapType,
  onExpand,
  onCollapse,
  onFitView,
  onMaxDepthChange,
  onToggleReasoningMap,
  onClearFocus,
  onExportPng,
  onExportJson,
  onExportMarkdown,
  onSave,
  onShare,
}: MindMapToolbarProps) {
  const availableTypes = availableMapTypes.length > 0 ? availableMapTypes : [activeMapType];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-3">
        <div className="inline-flex flex-wrap items-center rounded-full border border-black/[0.06] bg-white/96 p-1 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
          {availableTypes.map((mapType) => (
            <button
              key={mapType}
              type="button"
              onClick={() => onSwitchMapType(mapType)}
              className={`h-8 rounded-full px-3.5 text-[12px] font-medium transition-colors ${
                activeMapType === mapType
                  ? "bg-[#17171b] text-white"
                  : "text-[#3a3a40] hover:bg-[#f4f4f6]"
              }`}
            >
              {MAP_TYPE_LABELS[mapType]}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {focusNodeId ? (
            <button
              type="button"
              onClick={onClearFocus}
              className="inline-flex h-9 items-center rounded-full border border-[#bfdbfe] bg-[#eff6ff] px-3.5 text-[12px] font-medium text-[#1d4ed8] hover:bg-[#dbeafe]"
            >
              Back to full map
            </button>
          ) : null}
          <div className="inline-flex h-9 items-center rounded-full border border-[#d7d9e0] bg-[#f8f8f6] px-3.5 text-[12px] font-medium text-[#5c6370]">
            Horizontal tree
          </div>
          <div className="inline-flex items-center gap-2 rounded-full border border-black/[0.06] bg-white px-3 py-1.5 text-[12px] font-medium text-[#3a3a40]">
            <span>Depth {maxDepth}</span>
            <button
              type="button"
              onClick={() => onMaxDepthChange(maxDepth - 1)}
              className="flex h-5 w-5 items-center justify-center rounded-full border border-black/[0.06] hover:bg-[#f4f4f6]"
              aria-label="Decrease depth"
            >
              -
            </button>
            <button
              type="button"
              onClick={() => onMaxDepthChange(maxDepth + 1)}
              className="flex h-5 w-5 items-center justify-center rounded-full border border-black/[0.06] hover:bg-[#f4f4f6]"
              aria-label="Increase depth"
            >
              +
            </button>
          </div>
          {hasReasoningMap ? (
            <button
              type="button"
              onClick={onToggleReasoningMap}
              className={`inline-flex h-9 items-center rounded-full border px-3.5 text-[12px] font-medium transition-colors ${
                showReasoningMap
                  ? "border-[#c4b5fd] bg-[#f5f3ff] text-[#6d28d9] hover:bg-[#ede9fe]"
                  : "border-black/[0.06] bg-white text-[#3a3a40] hover:bg-[#f4f4f6]"
              }`}
            >
              Show reasoning
            </button>
          ) : null}
          <button
            type="button"
            onClick={onExpand}
            className="inline-flex h-9 items-center rounded-full border border-black/[0.06] bg-white px-3.5 text-[12px] font-medium text-[#3a3a40] hover:bg-[#f4f4f6]"
          >
            <Expand className="mr-1.5 h-3.5 w-3.5" />
            Expand
          </button>
          <button
            type="button"
            onClick={onCollapse}
            className="inline-flex h-9 items-center rounded-full border border-black/[0.06] bg-white px-3.5 text-[12px] font-medium text-[#3a3a40] hover:bg-[#f4f4f6]"
          >
            <Minimize2 className="mr-1.5 h-3.5 w-3.5" />
            Collapse
          </button>
          <button
            type="button"
            onClick={onFitView}
            className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-black/[0.06] bg-white text-[#3a3a40] hover:bg-[#f4f4f6]"
            title="Fit view"
          >
            <Maximize2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-2 border-t border-black/[0.05] pt-3 md:flex-row md:items-center md:justify-between">
        <p className="text-[11px] font-medium text-[#7d818c]">
          Switch map intent, then expand only the branch you need.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onExportPng}
            className="inline-flex h-8 items-center rounded-full border border-black/[0.06] bg-transparent px-3 text-[11px] font-medium text-[#575b66] hover:bg-white"
          >
            PNG
          </button>
          <button
            type="button"
            onClick={onExportJson}
            className="inline-flex h-8 items-center rounded-full border border-black/[0.06] bg-transparent px-3 text-[11px] font-medium text-[#575b66] hover:bg-white"
          >
            JSON
          </button>
          <button
            type="button"
            onClick={onExportMarkdown}
            className="inline-flex h-8 items-center rounded-full border border-black/[0.06] bg-transparent px-3 text-[11px] font-medium text-[#575b66] hover:bg-white"
          >
            <FileDown className="mr-1.5 h-3.5 w-3.5" />
            Markdown
          </button>
          <button
            type="button"
            onClick={onSave}
            className="inline-flex h-8 items-center rounded-full border border-black/[0.06] bg-transparent px-3 text-[11px] font-medium text-[#575b66] hover:bg-white"
          >
            Save
          </button>
          <button
            type="button"
            onClick={onShare}
            className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-black/[0.06] bg-transparent text-[#575b66] hover:bg-white"
            title="Share map"
          >
            <Share2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
