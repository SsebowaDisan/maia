import { ChevronLeft, ChevronRight } from "lucide-react";
import { Handle, Position, type NodeProps } from "@xyflow/react";

import type { MindNodeData } from "./utils";

function MindNodeCard({ id, data }: NodeProps<MindNodeData>) {
  const isRoot = Boolean(data.isRoot);
  const isBranch = isRoot || data.hasChildren;

  return (
    <div className="relative">
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2 !w-2 !border-0 !bg-transparent !shadow-none"
        style={{ opacity: 0, pointerEvents: "none" }}
      />
      <Handle
        type="source"
        position={Position.Right}
        className="!h-2 !w-2 !border-0 !bg-transparent !shadow-none"
        style={{ opacity: 0, pointerEvents: "none" }}
      />
      <div
        role={data.onAsk ? "button" : undefined}
        tabIndex={data.onAsk ? 0 : -1}
        onClick={() => data.onAsk?.(id)}
        onKeyDown={(event) => {
          if (!data.onAsk) {
            return;
          }
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            data.onAsk(id);
          }
        }}
        title={data.onAsk ? "Ask about this node" : undefined}
        className={`min-w-[180px] max-w-[270px] rounded-2xl px-3.5 py-2.5 font-serif text-[#0f1926] transition-colors ${
          isBranch
            ? "border border-[#8ca6da] bg-[#cad8f2]"
            : "border border-[#7fbab2] bg-[#a9ddd7]"
        } ${data.onAsk ? "cursor-pointer" : "cursor-default"} ${data.isSelected ? "ring-2 ring-[#7ea6ff]/85" : ""}`}
      >
        <p className="truncate text-[13px] leading-[1.2]" title={data.title}>
          {data.title}
        </p>
        {data.subtitle ? (
          <p className="mt-1 truncate text-[10px] text-[#1c2d44]/75" title={data.subtitle}>
            {data.subtitle}
          </p>
        ) : null}
      </div>

      {data.hasChildren ? (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            data.onToggle(id);
          }}
          className="absolute -right-3 top-1/2 inline-flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-full border border-[#8ea4cf] bg-[#c1d2f0] text-[#243b62] shadow-[0_3px_10px_rgba(0,0,0,0.18)] hover:bg-[#ccdafa]"
          title={data.collapsed ? "Expand branch" : "Collapse branch"}
        >
          {data.collapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronLeft className="h-3.5 w-3.5" />}
        </button>
      ) : null}
    </div>
  );
}

export { MindNodeCard };
