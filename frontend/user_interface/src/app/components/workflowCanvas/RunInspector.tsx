/**
 * RunInspector — step-by-step debug view of a workflow run.
 * Shows each step's status, output, timing, retry info, and dead letters.
 */
import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Loader2,
  RefreshCw,
  SkipForward,
  XCircle,
} from "lucide-react";
import { useWorkflowStore } from "../../stores/workflowStore";
import type { WorkflowCanvasNodeRunState } from "../../stores/workflowStore";
import { request } from "../../../api/client/core";

type DeadLetterEntry = {
  id: string;
  run_id: string;
  step_id: string;
  step_type: string;
  error: string;
  inputs: Record<string, string>;
  attempt: number;
  date_created: string;
};

const STATE_ICONS: Record<WorkflowCanvasNodeRunState, React.ReactNode> = {
  idle: <Clock size={13} className="text-[#98a2b3]" />,
  running: <Loader2 size={13} className="animate-spin text-[#6366f1]" />,
  completed: <CheckCircle2 size={13} className="text-[#17b26a]" />,
  failed: <XCircle size={13} className="text-[#f04438]" />,
  skipped: <SkipForward size={13} className="text-[#d97706]" />,
  blocked: <AlertTriangle size={13} className="text-[#98a2b3]" />,
};

const STATE_COLORS: Record<WorkflowCanvasNodeRunState, string> = {
  idle: "border-[#e5e7eb]",
  running: "border-[#c7d2fe] bg-[#eef2ff]",
  completed: "border-[#a7f3d0] bg-[#ecfdf5]",
  failed: "border-[#fecaca] bg-[#fff1f2]",
  skipped: "border-[#fde68a] bg-[#fffbeb]",
  blocked: "border-[#e5e7eb] bg-[#f9fafb]",
};

type RunInspectorProps = {
  workflowId: string;
  onClose: () => void;
};

function RunInspector({ workflowId, onClose }: RunInspectorProps) {
  const { nodes, run } = useWorkflowStore();
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set());
  const [deadLetters, setDeadLetters] = useState<DeadLetterEntry[]>([]);
  const [showDeadLetters, setShowDeadLetters] = useState(false);

  useEffect(() => {
    if (showDeadLetters && workflowId) {
      request<DeadLetterEntry[]>(`/api/workflows/${workflowId}/dead-letters`)
        .then(setDeadLetters)
        .catch(() => setDeadLetters([]));
    }
  }, [showDeadLetters, workflowId]);

  const toggleStep = (stepId: string) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(stepId)) next.delete(stepId);
      else next.add(stepId);
      return next;
    });
  };

  const statusLabel =
    run.status === "running" ? "Running…" :
    run.status === "completed" ? "Completed" :
    run.status === "failed" ? "Failed" : "Idle";

  const statusColor =
    run.status === "running" ? "text-[#6366f1]" :
    run.status === "completed" ? "text-[#17b26a]" :
    run.status === "failed" ? "text-[#f04438]" : "text-[#98a2b3]";

  return (
    <aside className="flex h-full w-[360px] shrink-0 flex-col overflow-hidden rounded-2xl border border-black/[0.08] bg-white shadow-[0_8px_32px_-12px_rgba(15,23,42,0.18)]">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-black/[0.06] bg-[#fcfcfd] px-4 py-3">
        <div>
          <p className="text-[13px] font-semibold text-[#101828]">Run Inspector</p>
          <p className={`text-[11px] font-medium ${statusColor}`}>{statusLabel}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-full border border-black/[0.08] px-3 py-1.5 text-[12px] font-medium text-[#475467] hover:bg-[#f2f4f7]"
        >
          Close
        </button>
      </div>

      {/* Step list */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="space-y-1.5 px-3 py-3">
          {nodes.map((node) => {
            const state = node.runState || "idle";
            const expanded = expandedSteps.has(node.id);
            const result = run.stepResults[node.id];
            const hasOutput = Boolean(node.runOutput || result?.output);

            return (
              <div key={node.id} className={`rounded-xl border ${STATE_COLORS[state]} transition-colors`}>
                <button
                  type="button"
                  onClick={() => hasOutput && toggleStep(node.id)}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left"
                >
                  {STATE_ICONS[state]}
                  <span className="flex-1 truncate text-[12px] font-medium text-[#101828]">
                    {node.data.label || node.id}
                  </span>
                  {result?.duration_ms ? (
                    <span className="shrink-0 text-[10px] text-[#98a2b3]">
                      {result.duration_ms}ms
                    </span>
                  ) : null}
                  {hasOutput ? (
                    expanded ? <ChevronDown size={12} className="shrink-0 text-[#98a2b3]" /> : <ChevronRight size={12} className="shrink-0 text-[#98a2b3]" />
                  ) : null}
                </button>
                {expanded && hasOutput ? (
                  <div className="border-t border-black/[0.06] px-3 py-2">
                    <pre className="max-h-[200px] overflow-auto whitespace-pre-wrap break-all font-mono text-[11px] text-[#475467]">
                      {node.runOutput || result?.output || "—"}
                    </pre>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>

        {/* Dead letters section */}
        <div className="border-t border-black/[0.06] px-3 py-3">
          <button
            type="button"
            onClick={() => setShowDeadLetters((o) => !o)}
            className="flex w-full items-center gap-2 text-left text-[12px] font-semibold text-[#667085]"
          >
            <RefreshCw size={12} />
            <span className="flex-1">Dead Letters</span>
            {showDeadLetters ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </button>
          {showDeadLetters ? (
            <div className="mt-2 space-y-2">
              {deadLetters.length === 0 ? (
                <p className="text-[11px] text-[#98a2b3]">No dead-letter entries.</p>
              ) : (
                deadLetters.map((dl) => (
                  <div key={dl.id} className="rounded-lg border border-[#fecaca] bg-[#fff1f2] p-2">
                    <div className="flex items-center gap-2 text-[11px]">
                      <XCircle size={11} className="text-[#f04438]" />
                      <span className="font-medium text-[#b42318]">{dl.step_id}</span>
                      <span className="ml-auto text-[10px] text-[#98a2b3]">attempt {dl.attempt}</span>
                    </div>
                    <p className="mt-1 text-[10px] text-[#667085]">{dl.error}</p>
                    <p className="mt-0.5 text-[10px] text-[#98a2b3]">{dl.date_created}</p>
                  </div>
                ))
              )}
            </div>
          ) : null}
        </div>
      </div>
    </aside>
  );
}

export { RunInspector };
