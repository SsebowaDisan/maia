import { ChevronRight } from "lucide-react";
import { Handle, Position, type NodeProps } from "@xyflow/react";

import type { MindNodeData } from "./utils";

function cardWidthByDepth(depth: number): string {
  if (depth <= 0) {
    return "w-[400px]";
  }
  if (depth === 1) {
    return "w-[320px]";
  }
  return "w-[280px]";
}

function baseHandles() {
  return (
    <>
      <Handle type="source" position={Position.Right} className="!pointer-events-none !opacity-0" />
      <Handle type="source" position={Position.Left} className="!pointer-events-none !opacity-0" />
      <Handle type="source" position={Position.Top} className="!pointer-events-none !opacity-0" />
      <Handle type="source" position={Position.Bottom} className="!pointer-events-none !opacity-0" />
      <Handle type="target" position={Position.Left} className="!pointer-events-none !opacity-0" />
      <Handle type="target" position={Position.Right} className="!pointer-events-none !opacity-0" />
      <Handle type="target" position={Position.Top} className="!pointer-events-none !opacity-0" />
      <Handle type="target" position={Position.Bottom} className="!pointer-events-none !opacity-0" />
    </>
  );
}

function MindNodeCard({ id, data }: NodeProps<MindNodeData>) {
  const isRoot = Boolean(data.isRoot);
  const depth = Math.max(0, Number(data.depth || 0));

  const surface = isRoot
    ? {
        bg: "#b8bef0",
        border: "#a5aedf",
        text: "#1a2540",
      }
    : {
        bg: depth === 1 ? "#b7cfe9" : "#bed8ee",
        border: depth === 1 ? "#a5bfdc" : "#adc8df",
        text: "#20334a",
      };

  return (
    <div className="relative">
      {baseHandles()}

      <div
        title={data.title}
        style={{
          backgroundColor: surface.bg,
          borderColor: surface.border,
          color: surface.text,
          boxShadow: data.isSelected ? "0 0 0 3px rgba(88,132,199,0.32)" : "0 2px 8px rgba(15,23,42,0.08)",
        }}
        className={`rounded-[16px] border px-5 py-4 transition-all ${
          data.isInteractive ? "cursor-pointer hover:brightness-[0.98]" : "cursor-default"
        } ${cardWidthByDepth(depth)}`}
      >
        <p className={`${isRoot ? "text-[22px]" : depth === 1 ? "text-[20px]" : "text-[17px]"} font-medium leading-[1.25] tracking-[-0.01em]`}>
          {data.title}
        </p>
        {data.subtitle ? (
          <p className="mt-2 truncate text-[13px] leading-5 opacity-85" title={data.subtitle}>
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
          title={data.collapsed ? "Expand" : "Collapse"}
          className="absolute -right-7 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full border border-[#a8c1df] bg-[#b9d2ed] text-[#1f3552] shadow-sm transition-transform hover:scale-105"
        >
          <ChevronRight className={`h-5 w-5 transition-transform ${data.collapsed ? "" : "rotate-90"}`} />
        </button>
      ) : null}
    </div>
  );
}

export { MindNodeCard };
