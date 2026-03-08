import { ChevronRight } from "lucide-react";
import { Handle, Position, type NodeProps } from "@xyflow/react";

import type { MindNodeData } from "./utils";

// Six branch color families — cycling for > 6 top-level branches
const BRANCH_PALETTES = [
  { bg: "#FFF1EC", border: "#F97316", text: "#7C2D12" },  // orange
  { bg: "#ECFEFF", border: "#06B6D4", text: "#0C4A6E" },  // cyan
  { bg: "#F5F3FF", border: "#8B5CF6", text: "#3B0764" },  // purple
  { bg: "#F0FDF4", border: "#22C55E", text: "#14532D" },  // green
  { bg: "#FFFBEB", border: "#F59E0B", text: "#78350F" },  // amber
  { bg: "#FDF2F8", border: "#EC4899", text: "#831843" },  // pink
] as const;

function MindNodeCard({ id, data }: NodeProps<MindNodeData>) {
  const isRoot = Boolean(data.isRoot);
  const ci = (data.branchColorIndex ?? -1);
  const palette = ci >= 0 ? BRANCH_PALETTES[ci % BRANCH_PALETTES.length] : null;

  if (isRoot) {
    return (
      <div className="relative" style={{ animation: "mind-node-in 280ms cubic-bezier(0.34,1.56,0.64,1) both" }}>
        <Handle type="source" position={Position.Right} className="!opacity-0 !pointer-events-none" />
        <Handle type="source" position={Position.Left}  className="!opacity-0 !pointer-events-none" />
        <Handle type="source" position={Position.Top}   className="!opacity-0 !pointer-events-none" />
        <Handle type="source" position={Position.Bottom} className="!opacity-0 !pointer-events-none" />
        <div
          className={`rounded-2xl border-2 border-[#d2d2d7] bg-white px-4 py-3 shadow-[0_4px_20px_rgba(0,0,0,0.10)] ${
            data.isSelected ? "ring-2 ring-[#3B82F6]/50 ring-offset-2" : ""
          }`}
          style={{ minWidth: 130, maxWidth: 220 }}
        >
          <p className="text-[14px] font-semibold leading-[1.35] text-[#1d1d1f]" title={data.title}>
            {data.title}
          </p>
        </div>
        <style>{`
          @keyframes mind-node-in {
            from { opacity: 0; transform: scale(0.72); }
            to   { opacity: 1; transform: scale(1); }
          }
        `}</style>
      </div>
    );
  }

  const isDepth1 = (data.depth ?? 1) === 1;

  return (
    <div className="relative" style={{ animation: "mind-node-in 280ms cubic-bezier(0.34,1.56,0.64,1) both" }}>
      {/* Handles on all 4 sides so ReactFlow accepts edges from any direction */}
      <Handle type="target" position={Position.Left}   className="!opacity-0 !pointer-events-none" />
      <Handle type="target" position={Position.Right}  className="!opacity-0 !pointer-events-none" />
      <Handle type="target" position={Position.Top}    className="!opacity-0 !pointer-events-none" />
      <Handle type="target" position={Position.Bottom} className="!opacity-0 !pointer-events-none" />
      <Handle type="source" position={Position.Right}  className="!opacity-0 !pointer-events-none" />
      <Handle type="source" position={Position.Left}   className="!opacity-0 !pointer-events-none" />
      <Handle type="source" position={Position.Top}    className="!opacity-0 !pointer-events-none" />
      <Handle type="source" position={Position.Bottom} className="!opacity-0 !pointer-events-none" />

      {/* Node pill */}
      <div
        role={data.onAsk ? "button" : undefined}
        tabIndex={data.onAsk ? 0 : -1}
        onClick={() => data.onAsk?.(id)}
        onKeyDown={(event) => {
          if (!data.onAsk) return;
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            data.onAsk(id);
          }
        }}
        title={data.title}
        style={{
          backgroundColor: palette ? palette.bg : "#F5F5F7",
          borderColor: palette ? palette.border : "#C7C7CC",
          color: palette ? palette.text : "#3A3A3C",
          maxWidth: isDepth1 ? 200 : 180,
          boxShadow: data.isSelected
            ? `0 0 0 3px ${palette ? palette.border + "55" : "#3B82F655"}`
            : undefined,
        }}
        className={`rounded-full border ${isDepth1 ? "px-3.5 py-2 text-[13px] font-semibold" : "px-3 py-1.5 text-[12px] font-medium"} leading-[1.35] transition-all ${
          data.onAsk ? "cursor-pointer hover:brightness-95" : "cursor-default"
        }`}
      >
        <p className="truncate" title={data.title}>
          {data.title}
        </p>
        {data.subtitle ? (
          <p className="mt-0.5 truncate text-[10px] opacity-60" title={data.subtitle}>
            {data.subtitle}
          </p>
        ) : null}
      </div>

      {/* Expand / collapse button */}
      {data.hasChildren ? (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            data.onToggle(id);
          }}
          title={data.collapsed ? "Expand" : "Collapse"}
          style={{
            backgroundColor: palette ? palette.border : "#8E8E93",
          }}
          className="absolute -right-2.5 top-1/2 flex h-5 w-5 -translate-y-1/2 items-center justify-center rounded-full text-white shadow-sm transition-transform hover:scale-110"
        >
          {data.collapsed ? (
            <ChevronRight className="h-3 w-3" />
          ) : (
            <span className="text-[10px] font-bold leading-none">−</span>
          )}
        </button>
      ) : null}
    </div>
  );
}

export { MindNodeCard };
