import {
  Download,
  Expand,
  FileDown,
  Focus,
  Maximize2,
  Minimize2,
  RotateCcw,
  Share2,
} from "lucide-react";

type MindMapToolbarProps = {
  title: string;
  mapType: string;
  kind: string;
  activeMapType: "structure" | "evidence";
  hasVariants: boolean;
  onSwitchMapType: (mapType: "structure" | "evidence") => void;
  onExpand: () => void;
  onCollapse: () => void;
  onToggleLayout: () => void;
  layoutMode: "balanced" | "horizontal";
  onResetFocus: () => void;
  onAutoTidy: () => void;
  onFitView: () => void;
  onExportPng: () => void;
  onExportJson: () => void;
  onExportMarkdown: () => void;
  onSave: () => void;
  onShare: () => void | Promise<void>;
};

function MindMapToolbar({
  title,
  mapType,
  kind,
  activeMapType,
  hasVariants,
  onSwitchMapType,
  onExpand,
  onCollapse,
  onToggleLayout,
  layoutMode,
  onResetFocus,
  onAutoTidy,
  onFitView,
  onExportPng,
  onExportJson,
  onExportMarkdown,
  onSave,
  onShare,
}: MindMapToolbarProps) {
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="min-w-0">
        <p className="text-[12px] font-semibold text-[#1d1d1f] truncate">{title}</p>
        <p className="text-[10px] text-[#6e6e73] uppercase tracking-[0.08em]">
          {mapType} - {kind}
        </p>
      </div>
      <div className="flex items-center gap-1.5">
        <div className="inline-flex items-center rounded-full border border-black/[0.08] bg-white p-0.5">
          <button
            type="button"
            onClick={() => onSwitchMapType("structure")}
            className={`h-6 px-2.5 rounded-full text-[10px] transition-colors ${
              activeMapType === "structure" ? "bg-[#1d1d1f] text-white" : "text-[#1d1d1f] hover:bg-[#f5f5f7]"
            }`}
          >
            Structure
          </button>
          <button
            type="button"
            onClick={() => onSwitchMapType("evidence")}
            disabled={!hasVariants}
            className={`h-6 px-2.5 rounded-full text-[10px] transition-colors ${
              activeMapType === "evidence" ? "bg-[#1d1d1f] text-white" : "text-[#1d1d1f] hover:bg-[#f5f5f7]"
            } disabled:opacity-40`}
          >
            Evidence
          </button>
        </div>
        <button
          type="button"
          onClick={onExpand}
          className="h-7 px-2 rounded-full border border-black/[0.08] bg-white text-[11px] hover:bg-[#f5f5f7]"
        >
          <Expand className="w-3.5 h-3.5 inline mr-1" />
          Expand
        </button>
        <button
          type="button"
          onClick={onCollapse}
          className="h-7 px-2 rounded-full border border-black/[0.08] bg-white text-[11px] hover:bg-[#f5f5f7]"
        >
          <Minimize2 className="w-3.5 h-3.5 inline mr-1" />
          Collapse
        </button>
        <button
          type="button"
          onClick={onToggleLayout}
          className="h-7 px-2 rounded-full border border-black/[0.08] bg-white text-[11px] hover:bg-[#f5f5f7]"
        >
          {layoutMode === "balanced" ? "Horizontal" : "Balanced"}
        </button>
        <button
          type="button"
          onClick={onResetFocus}
          className="h-7 w-7 rounded-full border border-black/[0.08] bg-white text-[#1d1d1f] hover:bg-[#f5f5f7]"
          title="Reset focus"
        >
          <Focus className="w-3.5 h-3.5 mx-auto" />
        </button>
        <button
          type="button"
          onClick={onAutoTidy}
          className="h-7 w-7 rounded-full border border-black/[0.08] bg-white text-[#1d1d1f] hover:bg-[#f5f5f7]"
          title="Auto tidy"
        >
          <RotateCcw className="w-3.5 h-3.5 mx-auto" />
        </button>
        <button
          type="button"
          onClick={onFitView}
          className="h-7 w-7 rounded-full border border-black/[0.08] bg-white text-[#1d1d1f] hover:bg-[#f5f5f7]"
          title="Fit view"
        >
          <Maximize2 className="w-3.5 h-3.5 mx-auto" />
        </button>
        <button
          type="button"
          onClick={onExportPng}
          className="h-7 w-7 rounded-full border border-black/[0.08] bg-white text-[#1d1d1f] hover:bg-[#f5f5f7]"
          title="Export PNG"
        >
          <Download className="w-3.5 h-3.5 mx-auto" />
        </button>
        <button
          type="button"
          onClick={onExportJson}
          className="h-7 px-2 rounded-full border border-black/[0.08] bg-white text-[11px] hover:bg-[#f5f5f7]"
          title="Export JSON"
        >
          JSON
        </button>
        <button
          type="button"
          onClick={onExportMarkdown}
          className="h-7 px-2 rounded-full border border-black/[0.08] bg-white text-[11px] hover:bg-[#f5f5f7]"
          title="Export Markdown"
        >
          <FileDown className="w-3.5 h-3.5 inline mr-1" />
          Markdown
        </button>
        <button
          type="button"
          onClick={onSave}
          className="h-7 px-2 rounded-full border border-black/[0.08] bg-white text-[11px] hover:bg-[#f5f5f7]"
        >
          Save
        </button>
        <button
          type="button"
          onClick={onShare}
          className="h-7 w-7 rounded-full border border-black/[0.08] bg-white text-[#1d1d1f] hover:bg-[#f5f5f7]"
          title="Share map"
        >
          <Share2 className="w-3.5 h-3.5 mx-auto" />
        </button>
      </div>
    </div>
  );
}

export { MindMapToolbar };

