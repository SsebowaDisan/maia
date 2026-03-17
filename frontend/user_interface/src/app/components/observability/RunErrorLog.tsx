import { useMemo, useState } from "react";

type RunErrorRecord = {
  runId: string;
  status: string;
  errorType?: string;
  errorMessage?: string;
};

type RunErrorLogProps = {
  runs: RunErrorRecord[];
  onReplay?: (runId: string) => void;
  onOpenTheatre?: (runId: string) => void;
};

function inferErrorType(run: RunErrorRecord): string {
  if (run.errorType) {
    return run.errorType;
  }
  const text = String(run.errorMessage || "").toLowerCase();
  if (!text) {
    return "unknown";
  }
  if (text.includes("timeout")) {
    return "tool_timeout";
  }
  if (text.includes("credential") || text.includes("token") || text.includes("unauthorized")) {
    return "credential_expired";
  }
  if (text.includes("gate")) {
    return "gate_rejected";
  }
  if (text.includes("context")) {
    return "context_overflow";
  }
  return "runtime_error";
}

export function RunErrorLog({ runs, onReplay, onOpenTheatre }: RunErrorLogProps) {
  const [typeFilter, setTypeFilter] = useState("all");
  const errorRuns = useMemo(
    () =>
      runs.filter((run) => {
        const status = String(run.status || "").toLowerCase();
        return status === "failed" || status === "error" || Boolean(run.errorMessage);
      }),
    [runs],
  );
  const typedErrorRuns = useMemo(
    () =>
      errorRuns.map((run) => ({
        ...run,
        inferredType: inferErrorType(run),
      })),
    [errorRuns],
  );
  const types = useMemo(
    () => ["all", ...new Set(typedErrorRuns.map((run) => run.inferredType))],
    [typedErrorRuns],
  );
  const visible = typedErrorRuns.filter((run) =>
    typeFilter === "all" ? true : run.inferredType === typeFilter,
  );

  return (
    <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-[18px] font-semibold text-[#111827]">Run error log</h3>
        <select
          value={typeFilter}
          onChange={(event) => setTypeFilter(event.target.value)}
          className="rounded-full border border-black/[0.12] px-3 py-1.5 text-[12px]"
        >
          {types.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </div>
      {visible.length === 0 ? (
        <p className="rounded-xl border border-black/[0.06] bg-[#fcfcfd] p-3 text-[12px] text-[#667085]">
          No errors in current run history.
        </p>
      ) : null}
      <div className="space-y-2">
        {visible.map((run) => (
          <div key={run.runId} className="rounded-xl border border-[#fecaca] bg-[#fff7f7] p-3">
            <p className="text-[13px] font-semibold text-[#7f1d1d]">{run.runId}</p>
            <p className="mt-1 text-[12px] text-[#991b1b]">
              {run.inferredType.replace(/_/g, " ")} - {run.errorMessage || "No error message"}
            </p>
            <div className="mt-2 flex gap-2">
              <button
                type="button"
                onClick={() => onOpenTheatre?.(run.runId)}
                className="rounded-full border border-[#fecaca] bg-white px-3 py-1 text-[12px] font-semibold text-[#b42318]"
              >
                View in theatre
              </button>
              <button
                type="button"
                onClick={() => onReplay?.(run.runId)}
                className="rounded-full bg-[#7c3aed] hover:bg-[#6d28d9] transition-colors px-3 py-1 text-[12px] font-semibold text-white"
              >
                Replay run
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

export type { RunErrorRecord };
