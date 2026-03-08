import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import type { GraphNodeData } from "./graphTypes";

function GraphNode({ data }: NodeProps<Node<GraphNodeData>>) {
  const isRoot = data.kind === "root";
  const isSection = data.kind === "section";
  const isClaim = data.kind === "claim";
  const isEvidence = data.kind === "evidence";
  const isPlaceholder = data.kind === "placeholder";
  const usageClaimCount = Number(data.usageClaimCount || 0);
  const usageEvidenceCount = Number(data.usageEvidenceCount || 0);
  const hasUsageMeta = usageClaimCount > 0 || usageEvidenceCount > 0;
  const isUsed = Boolean(data.active) || hasUsageMeta;
  const borderColor = isRoot
    ? "rgba(17, 17, 19, 1)"
    : isUsed
      ? "rgba(17, 17, 19, 0.26)"
      : isSection
        ? "rgba(0, 0, 0, 0.08)"
        : "transparent";
  const dotColor = data.branchColor || "#7a7a86";
  const bgColor = isRoot
    ? "#111113"
    : isSection
      ? "rgba(255, 255, 255, 0.9)"
      : isUsed
        ? "rgba(255, 246, 202, 0.52)"
        : isClaim
          ? "rgba(255, 255, 255, 0.7)"
          : "transparent";
  const textColor = isRoot ? "#ffffff" : "#1d1d1f";
  const showTargetLeft = !isRoot && data.side === "right";
  const showTargetRight = !isRoot && data.side === "left";
  const showSourceLeft = isRoot || data.side === "left";
  const showSourceRight = isRoot || data.side === "right";
  const collapseLabel = data.collapsed ? `+${Math.max(1, data.hiddenChildrenCount)}` : "-";

  return (
    <div
      className={`${isRoot ? "min-w-[188px] max-w-[320px] rounded-2xl border px-3 py-2.5 shadow-[0_12px_32px_rgba(0,0,0,0.24)]" : isSection ? "min-w-[180px] max-w-[360px] rounded-xl border px-2 py-1.5 shadow-[0_1px_6px_rgba(0,0,0,0.05)]" : "min-w-[150px] max-w-[350px] rounded-lg border px-1.5 py-1"} transition-colors`}
      style={{ borderColor, background: bgColor }}
    >
      <Handle
        type="target"
        id="target-left"
        position={Position.Left}
        className="!h-2 !w-2 !border-0 !bg-transparent !shadow-none"
        style={{ opacity: 0, pointerEvents: "none", display: showTargetLeft ? "block" : "none" }}
      />
      <Handle
        type="target"
        id="target-right"
        position={Position.Right}
        className="!h-2 !w-2 !border-0 !bg-transparent !shadow-none"
        style={{ opacity: 0, pointerEvents: "none", display: showTargetRight ? "block" : "none" }}
      />
      <Handle
        type="source"
        id="source-left"
        position={Position.Left}
        className="!h-2 !w-2 !border-0 !bg-transparent !shadow-none"
        style={{ opacity: 0, pointerEvents: "none", display: showSourceLeft ? "block" : "none" }}
      />
      <Handle
        type="source"
        id="source-right"
        position={Position.Right}
        className="!h-2 !w-2 !border-0 !bg-transparent !shadow-none"
        style={{ opacity: 0, pointerEvents: "none", display: showSourceRight ? "block" : "none" }}
      />

      <div className="flex items-start gap-2" style={{ color: textColor }}>
        {!isRoot ? (
          <span
            className="mt-[6px] h-2.5 w-2.5 shrink-0 rounded-full border border-white/90 shadow-[0_0_0_1px_rgba(0,0,0,0.08)]"
            style={{ background: dotColor }}
          />
        ) : null}
        <div className="min-w-0 flex-1">
          <p
            className={`${isRoot ? "text-[12px] font-semibold tracking-[0.01em]" : isSection ? "text-[13px] font-semibold" : isEvidence ? "text-[12px] font-medium" : "text-[12.5px] font-medium"} truncate`}
          >
            {data.title}
          </p>
          {data.subtitle ? (
            <p className="mt-0.5 text-[11px] leading-tight" style={{ color: isRoot ? "rgba(255,255,255,0.72)" : "#6e6e73" }}>
              {data.subtitle}
            </p>
          ) : null}
          {hasUsageMeta && !isRoot ? (
            <p className="mt-1 text-[10px] text-[#6e6e73]">
              {usageClaimCount > 0 ? `${usageClaimCount} claim${usageClaimCount > 1 ? "s" : ""}` : "0 claims"}
              {" | "}
              {usageEvidenceCount} cite{usageEvidenceCount > 1 ? "s" : ""}
            </p>
          ) : null}
        </div>

        {data.collapsible ? (
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              data.onToggleCollapse?.(data.nodeId);
            }}
            className={`${isRoot ? "border-white/25 bg-white/10 text-white hover:bg-white/20" : "border-black/[0.14] bg-white/85 text-[#3a3a3c] hover:bg-white"} mt-[1px] inline-flex h-5 min-w-[20px] items-center justify-center rounded-full border px-1.5 text-[10px] font-semibold`}
            title={data.collapsed ? "Expand branch" : "Collapse branch"}
          >
            {collapseLabel}
          </button>
        ) : null}
      </div>

      {!isRoot ? (
        <div
          className="mt-1 h-[1.5px] rounded-full"
          style={{
            background: dotColor,
            opacity: isEvidence ? 0.54 : isUsed ? 0.58 : 0.22,
          }}
        />
      ) : null}

      {isPlaceholder ? (
        <div className="mt-1.5 text-[10px] text-[#6e6e73]">Run a cited answer to populate this branch.</div>
      ) : null}
    </div>
  );
}

const nodeTypes = { graphNode: GraphNode };

export { nodeTypes };
