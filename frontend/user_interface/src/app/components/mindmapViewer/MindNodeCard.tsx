import type { NodeProps } from "@xyflow/react";

import type { MindNodeData } from "./utils";

function MindNodeCard({ id, data }: NodeProps<MindNodeData>) {
  return (
    <div
      className="rounded-2xl border border-black/[0.08] bg-white/95 px-3 py-2 shadow-[0_8px_24px_-18px_rgba(0,0,0,0.35)] min-w-[168px] max-w-[280px] transition-all duration-200 ease-in-out"
      onDoubleClick={() => data.onAsk?.(id)}
      title={data.onAsk ? "Double-click to ask about this node" : undefined}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[12px] font-medium text-[#1d1d1f] truncate" title={data.title}>
            {data.title}
          </p>
          {data.subtitle ? (
            <p className="text-[10px] text-[#6e6e73] truncate" title={data.subtitle}>
              {data.subtitle}
            </p>
          ) : null}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {data.onAsk ? (
            <button
              type="button"
              onClick={() => data.onAsk?.(id)}
              className="h-5 px-1.5 rounded-md border border-black/[0.08] text-[9px] text-[#1d1d1f] hover:bg-[#f5f5f7]"
            >
              Ask
            </button>
          ) : null}
          {data.onFocus ? (
            <button
              type="button"
              onClick={() => data.onFocus?.(id)}
              className="h-5 px-1.5 rounded-md border border-black/[0.08] text-[9px] text-[#1d1d1f] hover:bg-[#f5f5f7]"
              title="Focus this branch"
            >
              Focus
            </button>
          ) : null}
          {data.hasChildren ? (
            <button
              type="button"
              onClick={() => data.onToggle(id)}
              className="h-5 w-5 rounded-md border border-black/[0.08] text-[10px] text-[#1d1d1f] hover:bg-[#f5f5f7]"
            >
              {data.collapsed ? "+" : "-"}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export { MindNodeCard };
