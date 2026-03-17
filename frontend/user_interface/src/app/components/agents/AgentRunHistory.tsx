import { useState } from "react";

type AgentRunHistoryRecord = {
  runId: string;
  agentId: string;
  triggerType: string;
  status: string;
  durationMs: number;
  llmCostUsd: number;
  startedAt: string;
  outputSummary: string;
  errorMessage?: string;
};

type FeedbackType = "approval" | "rejection" | "correction";

type AgentRunHistoryProps = {
  runs: AgentRunHistoryRecord[];
  onOpenReplay?: (runId: string) => void;
  onSubmitFeedback?: (payload: {
    runId: string;
    feedbackType: FeedbackType;
    originalOutput: string;
    correctedOutput: string;
  }) => Promise<void> | void;
};

function statusBadge(status: string): string {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "success" || normalized === "completed") {
    return "border-[#bbf7d0] bg-[#ecfdf3] text-[#166534]";
  }
  if (normalized === "failed" || normalized === "error") {
    return "border-[#fecaca] bg-[#fff1f2] text-[#b91c1c]";
  }
  if (normalized === "running" || normalized === "queued") {
    return "border-[#c4b5fd] bg-[#f5f3ff] text-[#7c3aed]";
  }
  return "border-[#e4e7ec] bg-[#f8fafc] text-[#475467]";
}

function formatRelativeTime(isoLike: string): string {
  const date = new Date(isoLike);
  if (Number.isNaN(date.getTime())) {
    return "Unknown";
  }
  const diffMs = Date.now() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) {
    return "just now";
  }
  if (diffMins < 60) {
    return `${diffMins}m ago`;
  }
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) {
    return `${diffHours}h ago`;
  }
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

export function AgentRunHistory({
  runs,
  onOpenReplay,
  onSubmitFeedback,
}: AgentRunHistoryProps) {
  const [correctionsByRunId, setCorrectionsByRunId] = useState<Record<string, string>>({});
  const [submittingRunId, setSubmittingRunId] = useState("");

  const submitFeedback = async (
    run: AgentRunHistoryRecord,
    feedbackType: FeedbackType,
    correctedOutput: string,
  ) => {
    if (!onSubmitFeedback || submittingRunId) {
      return;
    }
    setSubmittingRunId(run.runId);
    try {
      await onSubmitFeedback({
        runId: run.runId,
        feedbackType,
        originalOutput: run.outputSummary || run.errorMessage || "",
        correctedOutput,
      });
      if (feedbackType === "correction") {
        setCorrectionsByRunId((previous) => ({ ...previous, [run.runId]: "" }));
      }
    } finally {
      setSubmittingRunId("");
    }
  };

  return (
    <div className="rounded-2xl border border-black/[0.08] bg-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-[18px] font-semibold tracking-[-0.01em] text-[#101828]">Run history</h3>
        <span className="text-[12px] text-[#667085]">{runs.length} runs</span>
      </div>
      {runs.length === 0 ? (
        <p className="rounded-xl border border-black/[0.06] bg-[#fcfcfd] p-3 text-[12px] text-[#667085]">
          No runs recorded yet.
        </p>
      ) : null}
      <div className="space-y-2">
        {runs.map((run) => {
          const correction = correctionsByRunId[run.runId] || "";
          const isSubmitting = submittingRunId === run.runId;
          return (
            <div
              key={run.runId}
              className="rounded-xl border border-black/[0.06] bg-[#fcfcfd] p-3 hover:border-black/[0.14]"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[13px] font-semibold text-[#111827]">{run.runId}</p>
                <div className="flex items-center gap-2">
                  <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${statusBadge(run.status)}`}>
                    {run.status}
                  </span>
                  <button
                    type="button"
                    onClick={() => onOpenReplay?.(run.runId)}
                    className="rounded-full border border-black/[0.12] bg-white px-2.5 py-0.5 text-[11px] font-semibold text-[#344054]"
                  >
                    Replay
                  </button>
                </div>
              </div>
              <p className="mt-1 text-[12px] text-[#667085]">
                {run.triggerType} · {formatRelativeTime(run.startedAt)} · {(run.durationMs / 1000).toFixed(1)}s · $
                {run.llmCostUsd.toFixed(2)}
              </p>
              <p className="mt-1 text-[12px] text-[#475467]">
                {run.outputSummary || run.errorMessage || "No summary available."}
              </p>
              {onSubmitFeedback ? (
                <div className="mt-3 rounded-lg border border-black/[0.06] bg-white p-2">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[#667085]">
                    Feedback
                  </p>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      disabled={isSubmitting}
                      onClick={() => {
                        void submitFeedback(
                          run,
                          "approval",
                          run.outputSummary || run.errorMessage || "Approved output.",
                        );
                      }}
                      className="rounded-full border border-[#bbf7d0] bg-[#ecfdf3] px-2.5 py-1 text-[11px] font-semibold text-[#166534] disabled:opacity-50"
                    >
                      👍 Approve
                    </button>
                    <button
                      type="button"
                      disabled={isSubmitting}
                      onClick={() => {
                        void submitFeedback(
                          run,
                          "rejection",
                          correction.trim() || "Rejected. Needs revision.",
                        );
                      }}
                      className="rounded-full border border-[#fecaca] bg-[#fff1f2] px-2.5 py-1 text-[11px] font-semibold text-[#b42318] disabled:opacity-50"
                    >
                      👎 Reject
                    </button>
                    <button
                      type="button"
                      disabled={isSubmitting || !correction.trim()}
                      onClick={() => {
                        void submitFeedback(run, "correction", correction.trim());
                      }}
                      className="rounded-full border border-black/[0.12] bg-white px-2.5 py-1 text-[11px] font-semibold text-[#344054] disabled:opacity-40"
                    >
                      Submit correction
                    </button>
                  </div>
                  <textarea
                    value={correction}
                    onChange={(event) =>
                      setCorrectionsByRunId((previous) => ({
                        ...previous,
                        [run.runId]: event.target.value,
                      }))
                    }
                    rows={2}
                    placeholder="Provide corrected output or concise improvement note..."
                    className="mt-2 w-full resize-y rounded-lg border border-black/[0.12] px-2 py-1.5 text-[12px] text-[#344054] outline-none transition focus:border-[#98a2b3]"
                  />
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export type { AgentRunHistoryRecord };
