import { useEffect, useMemo, useState } from "react";

import { AGENT_OS_RUNS, formatRelativeTime } from "../../pages/agentOsData";

type LiveRunMonitorProps = {
  onOpenRun?: (runId: string) => void;
};

export function LiveRunMonitor({ onOpenRun }: LiveRunMonitorProps) {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => setTick((value) => value + 1), 5000);
    return () => window.clearInterval(timer);
  }, []);

  const activeRuns = useMemo(
    () =>
      AGENT_OS_RUNS.filter((run) => run.status === "success").slice(0, 2).map((run, index) => ({
        ...run,
        elapsedSeconds: Math.round(run.durationMs / 1000 + (tick % (index + 3))),
        stage: index % 2 === 0 ? "execution" : "verification",
      })),
    [tick],
  );

  return (
    <div className="rounded-2xl border border-black/[0.08] bg-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-[18px] font-semibold text-[#111827]">Live run monitor</h3>
        <span className="text-[12px] text-[#667085]">{activeRuns.length} active</span>
      </div>
      <div className="space-y-2">
        {activeRuns.map((run) => (
          <button
            key={run.id}
            type="button"
            onClick={() => onOpenRun?.(run.id)}
            className="w-full rounded-xl border border-black/[0.06] bg-[#fcfcfd] px-3 py-2 text-left hover:border-black/[0.14]"
          >
            <p className="text-[13px] font-semibold text-[#111827]">{run.id}</p>
            <p className="text-[12px] text-[#667085]">
              {run.triggerType} · {run.stage} · {run.elapsedSeconds}s · started {formatRelativeTime(run.startedAt)}
            </p>
          </button>
        ))}
      </div>
    </div>
  );
}

