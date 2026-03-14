import { useMemo, useState } from "react";

import type { AgentRunRecord } from "../../pages/agentOsData";

type RunErrorLogProps = {
  runs: AgentRunRecord[];
  onReplay?: (runId: string) => void;
  onOpenTheatre?: (runId: string) => void;
};

export function RunErrorLog({ runs, onReplay, onOpenTheatre }: RunErrorLogProps) {
  const [typeFilter, setTypeFilter] = useState("all");
  const errorRuns = runs.filter((run) => run.status === "failed");
  const types = useMemo(
    () => ["all", ...new Set(errorRuns.map((run) => run.errorType || "unknown"))],
    [errorRuns],
  );
  const visible = errorRuns.filter((run) =>
    typeFilter === "all" ? true : (run.errorType || "unknown") === typeFilter,
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
      <div className="space-y-2">
        {visible.map((run) => (
          <div key={run.id} className="rounded-xl border border-[#fecaca] bg-[#fff7f7] p-3">
            <p className="text-[13px] font-semibold text-[#7f1d1d]">{run.id}</p>
            <p className="mt-1 text-[12px] text-[#991b1b]">
              {(run.errorType || "unknown").replace(/_/g, " ")} - {run.errorMessage || "No error message"}
            </p>
            <div className="mt-2 flex gap-2">
              <button
                type="button"
                onClick={() => onOpenTheatre?.(run.id)}
                className="rounded-full border border-[#fecaca] bg-white px-3 py-1 text-[12px] font-semibold text-[#b42318]"
              >
                View in theatre
              </button>
              <button
                type="button"
                onClick={() => onReplay?.(run.id)}
                className="rounded-full bg-[#111827] px-3 py-1 text-[12px] font-semibold text-white"
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

