import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Clock3, Loader2, RefreshCw, X, XCircle } from "lucide-react";

import type { WorkflowRunRecord } from "../../../api/client/types";
import type { WorkflowCanvasNode } from "../../stores/workflowStore";

type WorkflowRunHistoryProps = {
  open: boolean;
  loading: boolean;
  loadingMore?: boolean;
  hasMore?: boolean;
  runs: WorkflowRunRecord[];
  nodes: WorkflowCanvasNode[];
  onClose: () => void;
  onRefresh: () => void;
  onLoadMore?: () => void;
  onLoadOutputs: (run: WorkflowRunRecord) => void;
};

type StepInspection = {
  runId: string;
  stepId: string;
  title: string;
  status: string;
  durationMs: number;
  outputText: string;
  error: string;
  skipReason: string;
};

function formatTimestamp(epochSeconds?: number) {
  if (!epochSeconds || !Number.isFinite(epochSeconds)) {
    return "n/a";
  }
  return new Date(epochSeconds * 1000).toLocaleString();
}

function normalizeStatus(value: string): "completed" | "failed" | "skipped" | "running" | "unknown" {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "completed") return "completed";
  if (normalized === "failed") return "failed";
  if (normalized === "skipped") return "skipped";
  if (normalized === "running") return "running";
  return "unknown";
}

function statusBadgeClasses(status: "completed" | "failed" | "skipped" | "running" | "unknown") {
  if (status === "completed") return "border-[#bbf7d0] bg-[#f0fdf4] text-[#166534]";
  if (status === "failed") return "border-[#fecaca] bg-[#fff1f2] text-[#b42318]";
  if (status === "skipped") return "border-[#fde68a] bg-[#fffbeb] text-[#92400e]";
  if (status === "running") return "border-[#c4b5fd] bg-[#f5f3ff] text-[#7c3aed]";
  return "border-[#d0d5dd] bg-[#f8fafc] text-[#344054]";
}

function statusIcon(status: "completed" | "failed" | "skipped" | "running" | "unknown") {
  if (status === "completed") return <CheckCircle2 size={14} className="text-[#15803d]" />;
  if (status === "failed") return <XCircle size={14} className="text-[#b42318]" />;
  if (status === "skipped") return <AlertTriangle size={14} className="text-[#b45309]" />;
  if (status === "running") return <Clock3 size={14} className="text-[#7c3aed]" />;
  return <Clock3 size={14} className="text-[#667085]" />;
}

function cleanPreviewText(value: string) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .replace(/^["'`\-–•]+/g, "")
    .trim();
}

function WorkflowRunHistory({
  open,
  loading,
  loadingMore = false,
  hasMore = false,
  runs,
  nodes,
  onClose,
  onRefresh,
  onLoadMore,
  onLoadOutputs,
}: WorkflowRunHistoryProps) {
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
  const [inspection, setInspection] = useState<StepInspection | null>(null);

  const nodeLookup = useMemo(() => {
    const map = new Map<string, WorkflowCanvasNode>();
    for (const node of nodes) {
      map.set(node.id, node);
    }
    return map;
  }, [nodes]);

  if (!open) {
    return null;
  }

  return (
    <section className="absolute inset-x-4 bottom-4 z-20 max-h-[420px] overflow-hidden rounded-2xl border border-black/[0.08] bg-white shadow-xl">
      <div className="flex items-center justify-between border-b border-black/[0.06] px-4 py-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#667085]">
            Run history
          </p>
          <p className="text-[14px] font-semibold text-[#101828]">Previous workflow runs</p>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onRefresh}
            className="rounded-full border border-black/[0.08] p-1.5 text-[#475467] hover:bg-[#f8fafc]"
            aria-label="Refresh run history"
          >
            <RefreshCw size={13} />
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-black/[0.08] p-1.5 text-[#475467] hover:bg-[#f8fafc]"
            aria-label="Close run history"
          >
            <X size={13} />
          </button>
        </div>
      </div>

      <div className="relative max-h-[360px] overflow-y-auto p-3">
        {loading ? (
          <div className="flex items-center gap-2 rounded-xl border border-black/[0.06] bg-[#fcfcfd] p-3 text-[12px] text-[#475467]">
            <Loader2 size={13} className="animate-spin" />
            Loading runs...
          </div>
        ) : null}

        {!loading && runs.length === 0 ? (
          <p className="rounded-xl border border-black/[0.06] bg-[#fcfcfd] p-3 text-[12px] text-[#667085]">
            No runs yet for this workflow.
          </p>
        ) : null}

        <div className="space-y-2">
          {runs.map((run) => (
            <article
              key={run.run_id}
              className="rounded-xl border border-black/[0.08] bg-white p-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[12px] font-semibold text-[#101828]">{String(run.status || "unknown")}</p>
                <p className="text-[11px] text-[#667085]">{formatTimestamp(run.started_at)}</p>
              </div>
              <p className="mt-1 text-[11px] text-[#667085]">
                Duration: {Math.max(0, Number(run.duration_ms || 0))} ms
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => onLoadOutputs(run)}
                  className="rounded-full border border-black/[0.12] px-3 py-1 text-[11px] font-semibold text-[#344054] hover:bg-[#f8fafc]"
                >
                  Load outputs on canvas
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setExpandedRunId((current) => (current === run.run_id ? null : run.run_id))
                  }
                  className="rounded-full border border-black/[0.12] px-3 py-1 text-[11px] font-semibold text-[#344054] hover:bg-[#f8fafc]"
                >
                  {expandedRunId === run.run_id ? "Hide steps" : "View steps"}
                </button>
              </div>
              {expandedRunId === run.run_id ? (
                <div className="mt-3 space-y-2 rounded-lg border border-black/[0.06] bg-[#fcfcfd] p-2">
                  {(run.step_results || []).length === 0 ? (
                    <p className="rounded-md bg-white px-2.5 py-2 text-[11px] text-[#667085]">
                      No step details were recorded for this run.
                    </p>
                  ) : null}
                  {(run.step_results || []).map((step) => {
                    const stepId = String(step.step_id || "").trim();
                    const node = nodeLookup.get(stepId);
                    const status = normalizeStatus(String(step.status || ""));
                    const title = String(
                      node?.data?.label || node?.data?.description || stepId || "Unnamed step",
                    ).trim();
                    const output = cleanPreviewText(
                      String(
                        step.output_preview ||
                          run.final_outputs?.[String(node?.data?.outputKey || "").trim()] ||
                          "",
                      ),
                    );
                    const errorText = cleanPreviewText(String(step.error || ""));
                    const skipReason =
                      status === "skipped"
                        ? cleanPreviewText(String(step.reason || "").trim()) ||
                          "Skip reason unavailable for this run."
                        : "";
                    return (
                      <div
                        key={`${run.run_id}-${stepId}-${status}`}
                        className="rounded-md border border-black/[0.06] bg-white px-2.5 py-2"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex min-w-0 items-center gap-1.5">
                            {statusIcon(status)}
                            <p className="truncate text-[12px] font-semibold text-[#101828]">{title}</p>
                          </div>
                          <span
                            className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] ${statusBadgeClasses(
                              status,
                            )}`}
                          >
                            {status}
                          </span>
                        </div>
                        <p className="mt-1 text-[11px] text-[#667085]">
                          {Math.max(0, Number(step.duration_ms || 0))} ms
                        </p>
                        {status === "failed" && errorText ? (
                          <p className="mt-1 line-clamp-2 text-[11px] text-[#b42318]">{errorText}</p>
                        ) : null}
                        {status === "skipped" ? (
                          <p className="mt-1 line-clamp-2 text-[11px] text-[#92400e]">{skipReason}</p>
                        ) : null}
                        {status === "completed" && output ? (
                          <p className="mt-1 line-clamp-2 text-[11px] text-[#475467]">{output}</p>
                        ) : null}
                        <button
                          type="button"
                          onClick={() =>
                            setInspection({
                              runId: run.run_id,
                              stepId,
                              title,
                              status,
                              durationMs: Math.max(0, Number(step.duration_ms || 0)),
                              outputText: output,
                              error: errorText,
                              skipReason,
                            })
                          }
                          className="mt-2 rounded-full border border-black/[0.12] px-2.5 py-0.5 text-[10px] font-semibold text-[#344054] hover:bg-[#f8fafc]"
                        >
                          View details
                        </button>
                      </div>
                    );
                  })}
                </div>
              ) : null}
            </article>
          ))}
        </div>

        {!loading && runs.length > 0 && hasMore ? (
          <div className="mt-3 flex justify-center">
            <button
              type="button"
              onClick={() => onLoadMore?.()}
              disabled={loadingMore}
              className="inline-flex items-center gap-1.5 rounded-full border border-black/[0.12] bg-white px-3 py-1.5 text-[11px] font-semibold text-[#344054] hover:bg-[#f8fafc] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loadingMore ? <Loader2 size={12} className="animate-spin" /> : null}
              {loadingMore ? "Loading..." : "Load more runs"}
            </button>
          </div>
        ) : null}

        {inspection ? (
          <div className="absolute inset-y-3 right-3 z-30 w-[320px] overflow-hidden rounded-xl border border-black/[0.1] bg-white shadow-2xl">
            <div className="flex items-start justify-between border-b border-black/[0.06] px-3 py-2">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#667085]">Step details</p>
                <p className="text-[13px] font-semibold text-[#101828]">{inspection.title}</p>
              </div>
              <button
                type="button"
                onClick={() => setInspection(null)}
                className="rounded-full border border-black/[0.1] p-1 text-[#667085] hover:bg-[#f8fafc]"
                aria-label="Close step details"
              >
                <X size={12} />
              </button>
            </div>
            <div className="max-h-[280px] overflow-y-auto space-y-2 px-3 py-3">
              <p className="text-[11px] text-[#667085]">
                Run {inspection.runId} · Step {inspection.stepId}
              </p>
              <span
                className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] ${statusBadgeClasses(
                  normalizeStatus(inspection.status),
                )}`}
              >
                {inspection.status}
              </span>
              <p className="text-[11px] text-[#667085]">Duration: {inspection.durationMs} ms</p>
              {inspection.skipReason ? (
                <div className="rounded-lg border border-[#fde68a] bg-[#fffbeb] p-2 text-[11px] text-[#92400e]">
                  {inspection.skipReason}
                </div>
              ) : null}
              {inspection.error ? (
                <div className="rounded-lg border border-[#fecaca] bg-[#fff1f2] p-2 text-[11px] text-[#b42318]">
                  {inspection.error}
                </div>
              ) : null}
              <div className="rounded-lg border border-black/[0.08] bg-[#fcfcfd] p-2">
                <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#667085]">Output</p>
                <p className="mt-1 whitespace-pre-wrap text-[11px] text-[#344054]">
                  {inspection.outputText || "No output was recorded for this step."}
                </p>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}

export { WorkflowRunHistory };
export type { WorkflowRunHistoryProps };
