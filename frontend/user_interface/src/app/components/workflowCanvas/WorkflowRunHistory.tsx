import { Loader2, RefreshCw, X } from "lucide-react";

import type { WorkflowRunRecord } from "../../../api/client/types";

type WorkflowRunHistoryProps = {
  open: boolean;
  loading: boolean;
  runs: WorkflowRunRecord[];
  onClose: () => void;
  onRefresh: () => void;
  onLoadOutputs: (run: WorkflowRunRecord) => void;
};

function formatTimestamp(epochSeconds?: number) {
  if (!epochSeconds || !Number.isFinite(epochSeconds)) {
    return "n/a";
  }
  return new Date(epochSeconds * 1000).toLocaleString();
}

function WorkflowRunHistory({
  open,
  loading,
  runs,
  onClose,
  onRefresh,
  onLoadOutputs,
}: WorkflowRunHistoryProps) {
  if (!open) {
    return null;
  }

  return (
    <section className="absolute inset-x-4 bottom-4 z-20 max-h-[300px] overflow-hidden rounded-2xl border border-black/[0.08] bg-white shadow-xl">
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

      <div className="max-h-[240px] overflow-y-auto p-3">
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
                <p className="text-[12px] font-semibold text-[#101828]">{run.status}</p>
                <p className="text-[11px] text-[#667085]">{formatTimestamp(run.started_at)}</p>
              </div>
              <p className="mt-1 text-[11px] text-[#667085]">
                Duration: {Math.max(0, Number(run.duration_ms || 0))} ms
              </p>
              <button
                type="button"
                onClick={() => onLoadOutputs(run)}
                className="mt-2 rounded-full border border-black/[0.12] px-3 py-1 text-[11px] font-semibold text-[#344054] hover:bg-[#f8fafc]"
              >
                Load outputs on canvas
              </button>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

export { WorkflowRunHistory };
export type { WorkflowRunHistoryProps };
