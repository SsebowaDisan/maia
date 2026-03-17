import {
  AlertTriangle,
  ArrowRightFromLine,
  CheckCircle2,
  CircleDashed,
  Loader2,
  LogIn,
  OctagonAlert,
  PauseCircle,
  Zap,
} from "lucide-react";
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

// ── Run state styling ──────────────────────────────────────────────────────────

function runBorder(runState: WorkflowCanvasNodeRunState | undefined) {
  if (runState === "running")   return "border-[#2563eb]/40 ring-2 ring-[#2563eb]/20";
  if (runState === "completed") return "border-[#16a34a]/40 ring-2 ring-[#16a34a]/15";
  if (runState === "failed")    return "border-[#dc2626]/40 ring-2 ring-[#dc2626]/15";
  if (runState === "blocked")   return "border-[#f59e0b]/50 ring-2 ring-[#f59e0b]/15";
  if (runState === "skipped")   return "border-black/[0.08]";
  return "border-black/[0.1]";
}

function runHeaderBg(runState: WorkflowCanvasNodeRunState | undefined) {
  if (runState === "running")   return "from-[#eff6ff] to-[#dbeafe]";
  if (runState === "completed") return "from-[#ecfdf3] to-[#d1fae5]";
  if (runState === "failed")    return "from-[#fef2f2] to-[#fee2e2]";
  if (runState === "blocked")   return "from-[#fffbeb] to-[#fef3c7]";
  return "from-[#f0f4ff] to-[#e8eef8]";
}

function monogramColor(runState: WorkflowCanvasNodeRunState | undefined) {
  if (runState === "running")   return "text-[#1d4ed8]";
  if (runState === "completed") return "text-[#15803d]";
  if (runState === "failed")    return "text-[#dc2626]";
  if (runState === "blocked")   return "text-[#b45309]";
  return "text-[#344054]";
}

function RunBadge({ runState }: { runState?: WorkflowCanvasNodeRunState }) {
  if (runState === "running") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-[#2563eb] px-2 py-0.5 text-[10px] font-semibold text-white">
        <Loader2 size={9} className="animate-spin" />
        Running
      </span>
    );
  }
  if (runState === "completed") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-[#ecfdf3] px-2 py-0.5 text-[10px] font-semibold text-[#15803d]">
        <CheckCircle2 size={9} />
        Done
      </span>
    );
  }
  if (runState === "failed") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-[#fef2f2] px-2 py-0.5 text-[10px] font-semibold text-[#dc2626]">
        <OctagonAlert size={9} />
        Failed
      </span>
    );
  }
  if (runState === "blocked") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-[#fffbeb] px-2 py-0.5 text-[10px] font-semibold text-[#b45309]">
        <OctagonAlert size={9} />
        Waiting
      </span>
    );
  }
  if (runState === "skipped") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-[#f4f4f5] px-2 py-0.5 text-[10px] font-semibold text-[#71717a]">
        <PauseCircle size={9} />
        Skipped
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-[#f8fafc] px-2 py-0.5 text-[10px] font-medium text-[#98a2b3]">
      <CircleDashed size={9} />
      Idle
    </span>
  );
}

function nodeTypeLabel(type: WorkflowCanvasNodeType): string {
  if (type === "trigger")   return "Trigger";
  if (type === "condition") return "Condition";
  if (type === "output")    return "Output";
  return "Agent";
}

function agentMonogram(name: string): string {
  const t = String(name || "").trim();
  return t ? t.charAt(0).toUpperCase() : "A";
}

// ── Node ──────────────────────────────────────────────────────────────────────

function WorkflowNode({ data, selected }: NodeProps<WorkflowFlowNodeData>) {
  const agentName = String(data.agentName || data.agentId || "").trim();
  const agentDescription = String(data.agentDescription || "").trim();
  const agentTags = Array.isArray(data.agentTags)
    ? data.agentTags.map((t) => String(t || "").trim()).filter(Boolean)
    : [];
  const monogram = agentMonogram(agentName);
  const snippet = String(data.runOutput || "").trim();
  const validationWarning = String(data.validationWarning || "").trim();
  const isTrigger = data.nodeType === "trigger";
  const isOutput = data.nodeType === "output";
  const inputDesc = String(data.inputDescription || "").trim();
  const outputDesc = String(data.outputDescription || "").trim();

  return (
    <div
      className={`w-[320px] overflow-hidden rounded-2xl border bg-white shadow-[0_4px_16px_-6px_rgba(15,23,42,0.16)] transition-all duration-150 ${
        runBorder(data.runState)
      } ${validationWarning ? "!border-[#f59e0b]/60" : ""} ${
        selected ? "shadow-[0_8px_28px_-8px_rgba(37,99,235,0.35)]" : ""
      }`}
    >
      {/* Input handle */}
      {!isTrigger ? (
        <Handle
          type="target"
          position={Position.Left}
          className="!h-3 !w-3 !rounded-full !border-2 !border-white !bg-[#93c5fd] shadow-sm"
        />
      ) : null}

      {/* Coloured header band with monogram */}
      <div className={`bg-gradient-to-br px-3.5 pt-3.5 pb-3 ${runHeaderBg(data.runState)}`}>
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2.5">
            {/* Monogram */}
            <div
              className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/60 bg-white/70 text-[15px] font-bold shadow-sm backdrop-blur-sm ${monogramColor(data.runState)}`}
            >
              {monogram}
            </div>
            <div className="min-w-0">
              <p className="line-clamp-3 text-[13px] font-semibold leading-snug text-[#101828]">
                {data.label || agentName || "Untitled step"}
              </p>
              <div className="mt-0.5 flex items-center gap-1.5">
                <span className="inline-flex items-center gap-0.5 text-[10px] font-medium uppercase tracking-[0.1em] text-[#667085]">
                  {isTrigger ? <Zap size={9} className="text-[#f59e0b]" /> : null}
                  {nodeTypeLabel(data.nodeType)}
                </span>
              </div>
            </div>
          </div>
          <div className="shrink-0 pt-0.5">
            <RunBadge runState={data.runState} />
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="px-3.5 py-3">
        {/* Input description — shown on trigger (first) node */}
        {isTrigger && inputDesc ? (
          <div className="mb-2.5 flex items-start gap-1.5 rounded-lg border border-[#e0e7ff] bg-[#eef2ff] px-2.5 py-1.5">
            <LogIn size={11} className="mt-[1px] shrink-0 text-[#6366f1]" />
            <p className="text-[10px] leading-[1.5] text-[#4338ca]">{inputDesc}</p>
          </div>
        ) : null}

        {/* Output description — shown on output (last) node */}
        {isOutput && outputDesc ? (
          <div className="mb-2.5 flex items-start gap-1.5 rounded-lg border border-[#d1fae5] bg-[#ecfdf5] px-2.5 py-1.5">
            <ArrowRightFromLine size={11} className="mt-[1px] shrink-0 text-[#059669]" />
            <p className="text-[10px] leading-[1.5] text-[#065f46]">{outputDesc}</p>
          </div>
        ) : null}

        {/* Description */}
        {agentDescription ? (
          <p className="text-[11px] leading-[1.55] text-[#667085]">
            {agentDescription}
          </p>
        ) : null}

        {/* Tags */}
        {agentTags.length > 0 ? (
          <div className={`flex flex-wrap gap-1 ${agentDescription ? "mt-2" : ""}`}>
            {agentTags.slice(0, 3).map((tag) => (
              <span
                key={tag}
                className="rounded-full border border-black/[0.07] bg-[#f0f4ff] px-1.5 py-0.5 text-[9px] font-medium text-[#3b5bdb]"
              >
                {tag}
              </span>
            ))}
            {agentTags.length > 3 ? (
              <span className="rounded-full border border-black/[0.07] bg-[#f8fafc] px-1.5 py-0.5 text-[9px] font-medium text-[#667085]">
                +{agentTags.length - 3}
              </span>
            ) : null}
          </div>
        ) : null}

        {/* Run output snippet */}
        {snippet ? (
          <div className="mt-2.5 rounded-xl border border-black/[0.06] bg-[#f8fafc] px-2.5 py-2">
            <p className="line-clamp-3 font-mono text-[10px] leading-[1.6] text-[#475467]">
              {snippet}
            </p>
          </div>
        ) : null}

        {/* Validation warning */}
        {validationWarning ? (
          <div className="mt-2.5 flex items-start gap-1.5 rounded-xl border border-[#f59e0b]/40 bg-[#fffbeb] px-2.5 py-2">
            <AlertTriangle size={11} className="mt-[1px] shrink-0 text-[#d97706]" />
            <p className="line-clamp-2 text-[10px] leading-[1.5] text-[#92400e]">
              {validationWarning}
            </p>
          </div>
        ) : null}
      </div>

      {/* Output handle — hidden on output (last) node */}
      {!isOutput ? (
        <Handle
          type="source"
          position={Position.Right}
          className="!h-3 !w-3 !rounded-full !border-2 !border-white !bg-[#93c5fd] shadow-sm"
        />
      ) : null}
    </div>
  );
}

export { WorkflowNode };
export type { WorkflowFlowNodeData };
