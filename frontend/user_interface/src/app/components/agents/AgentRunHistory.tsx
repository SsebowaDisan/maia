import { formatRelativeTime, type AgentRunRecord } from "../../pages/agentOsData";

type AgentRunHistoryProps = {
  runs: AgentRunRecord[];
  onOpenReplay?: (runId: string) => void;
};

function statusBadge(status: AgentRunRecord["status"]): string {
  if (status === "success") {
    return "border-[#bbf7d0] bg-[#ecfdf3] text-[#166534]";
  }
  if (status === "failed") {
    return "border-[#fecaca] bg-[#fff1f2] text-[#b91c1c]";
  }
  return "border-[#e4e7ec] bg-[#f8fafc] text-[#475467]";
}

export function AgentRunHistory({ runs, onOpenReplay }: AgentRunHistoryProps) {
  return (
    <div className="rounded-2xl border border-black/[0.08] bg-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-[18px] font-semibold tracking-[-0.01em] text-[#101828]">Run history</h3>
        <span className="text-[12px] text-[#667085]">{runs.length} runs</span>
      </div>
      <div className="space-y-2">
        {runs.map((run) => (
          <button
            key={run.id}
            type="button"
            onClick={() => onOpenReplay?.(run.id)}
            className="w-full rounded-xl border border-black/[0.06] bg-[#fcfcfd] p-3 text-left hover:border-black/[0.14]"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-[13px] font-semibold text-[#111827]">{run.id}</p>
              <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${statusBadge(run.status)}`}>
                {run.status}
              </span>
            </div>
            <p className="mt-1 text-[12px] text-[#667085]">
              {run.triggerType} · {formatRelativeTime(run.startedAt)} · {(run.durationMs / 1000).toFixed(1)}s · $
              {run.llmCostUsd.toFixed(2)}
            </p>
            <p className="mt-1 text-[12px] text-[#475467]">{run.outputSummary}</p>
          </button>
        ))}
      </div>
    </div>
  );
}

