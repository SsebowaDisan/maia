import { CheckCircle2, CircleDashed, Loader2, OctagonAlert, PauseCircle } from "lucide-react";
import { Handle, Position, type NodeProps } from "@xyflow/react";

import type {
  WorkflowCanvasNodeData,
  WorkflowCanvasNodeRunState,
  WorkflowCanvasNodeType,
} from "../../stores/workflowStore";

type WorkflowFlowNodeData = WorkflowCanvasNodeData & {
  nodeType: WorkflowCanvasNodeType;
  runState?: WorkflowCanvasNodeRunState;
  runOutput?: string;
};

function runTone(runState: WorkflowCanvasNodeRunState | undefined) {
  if (runState === "running") {
    return "border-[#2563eb]/35 bg-[#eff6ff]";
  }
  if (runState === "completed") {
    return "border-[#16a34a]/35 bg-[#ecfdf3]";
  }
  if (runState === "failed") {
    return "border-[#dc2626]/35 bg-[#fef2f2]";
  }
  if (runState === "skipped") {
    return "border-[#a1a1aa]/45 bg-[#fafafa]";
  }
  return "border-black/[0.12] bg-white";
}

function RunIcon({ runState }: { runState?: WorkflowCanvasNodeRunState }) {
  if (runState === "running") {
    return <Loader2 size={13} className="animate-spin text-[#2563eb]" />;
  }
  if (runState === "completed") {
    return <CheckCircle2 size={13} className="text-[#16a34a]" />;
  }
  if (runState === "failed") {
    return <OctagonAlert size={13} className="text-[#dc2626]" />;
  }
  if (runState === "skipped") {
    return <PauseCircle size={13} className="text-[#71717a]" />;
  }
  return <CircleDashed size={13} className="text-[#6b7280]" />;
}

function typeBadgeLabel(type: WorkflowCanvasNodeType): string {
  if (type === "trigger") {
    return "Trigger";
  }
  if (type === "condition") {
    return "Condition";
  }
  if (type === "output") {
    return "Output";
  }
  return "Agent";
}

function WorkflowNode({ data, selected }: NodeProps<WorkflowFlowNodeData>) {
  const snippet = String(data.runOutput || "").trim();
  const hasSnippet = snippet.length > 0;

  return (
    <div
      className={`w-[290px] rounded-2xl border px-4 py-3 shadow-sm transition ${
        runTone(data.runState)
      } ${selected ? "ring-2 ring-[#2563eb]/35" : ""}`}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="size-2.5 border border-white bg-[#93c5fd]"
      />
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-[15px] font-semibold text-[#101828]">{data.label || "Untitled step"}</p>
          <p className="mt-0.5 text-[11px] uppercase tracking-[0.12em] text-[#667085]">
            {typeBadgeLabel(data.nodeType)}
          </p>
        </div>
        <div className="mt-0.5 shrink-0">
          <RunIcon runState={data.runState} />
        </div>
      </div>

      <div className="mt-2 flex items-center gap-1.5 text-[12px] text-[#475467]">
        <span className="font-medium">Agent:</span>
        <span className="truncate">{data.agentId || "Unassigned"}</span>
      </div>

      {Array.isArray(data.toolIds) && data.toolIds.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {data.toolIds.slice(0, 4).map((toolId) => (
            <span
              key={toolId}
              className="rounded-full border border-black/[0.08] bg-white/80 px-2 py-0.5 text-[11px] text-[#344054]"
            >
              {toolId}
            </span>
          ))}
          {data.toolIds.length > 4 ? (
            <span className="rounded-full border border-black/[0.08] bg-white/80 px-2 py-0.5 text-[11px] text-[#667085]">
              +{data.toolIds.length - 4}
            </span>
          ) : null}
        </div>
      ) : null}

      {hasSnippet ? (
        <p className="mt-2 line-clamp-2 text-[11px] text-[#667085]">
          {snippet}
        </p>
      ) : null}

      <Handle
        type="source"
        position={Position.Right}
        className="size-2.5 border border-white bg-[#93c5fd]"
      />
    </div>
  );
}

export { WorkflowNode };
export type { WorkflowFlowNodeData };
