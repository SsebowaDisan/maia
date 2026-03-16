import { useEffect, useMemo, useState } from "react";
import { useAgentRunStore } from "../../stores/agentRunStore";

type LiveRunMonitorRecord = {
  runId: string;
  triggerType: string;
  status: string;
  startedAt: string;
  durationMs: number;
};

type LiveRunMonitorProps = {
  runs: LiveRunMonitorRecord[];
  onOpenRun?: (runId: string) => void;
};

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

function statusStage(status: string): string {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "running" || normalized === "in_progress") {
    return "execution";
  }
  if (normalized === "queued") {
    return "queue";
  }
  if (normalized === "completed" || normalized === "success") {
    return "verification";
  }
  if (normalized === "failed" || normalized === "error") {
    return "failed";
  }
  return normalized || "unknown";
}

export function LiveRunMonitor({ runs, onOpenRun }: LiveRunMonitorProps) {
  const [tick, setTick] = useState(0);
  const activeRunId = useAgentRunStore((state) => state.runId);
  const activeStage = useAgentRunStore((state) => state.stage);
  const activeToolId = useAgentRunStore((state) => state.toolId);

  useEffect(() => {
    const timer = window.setInterval(() => setTick((value) => value + 1), 5000);
    return () => window.clearInterval(timer);
  }, []);

  const activeRuns = useMemo(() => {
    const running = runs.filter((run) => {
      const status = String(run.status || "").toLowerCase();
      return status === "running" || status === "in_progress" || status === "queued";
    });
    return running.slice(0, 6).map((run) => {
      const startedAtMs = new Date(run.startedAt).getTime();
      const elapsedSeconds = Number.isNaN(startedAtMs)
        ? Math.max(0, Math.round(run.durationMs / 1000))
        : Math.max(0, Math.round((Date.now() - startedAtMs) / 1000));
      return {
      ...run,
      elapsedSeconds,
      stage: statusStage(run.status),
      };
    });
  }, [runs, tick]);

  return (
    <div className="rounded-2xl border border-black/[0.08] bg-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-[18px] font-semibold text-[#111827]">Live run monitor</h3>
        <span className="text-[12px] text-[#667085]">{activeRuns.length} active</span>
      </div>
      {activeRunId ? (
        <p className="mb-2 rounded-xl border border-black/[0.06] bg-[#f8fafc] px-3 py-2 text-[12px] text-[#475467]">
          Tracking run <span className="font-semibold text-[#111827]">{activeRunId}</span>
          {activeStage ? ` · ${activeStage}` : ""}
          {activeToolId ? ` · ${activeToolId}` : ""}
        </p>
      ) : null}
      {activeRuns.length === 0 ? (
        <p className="rounded-xl border border-black/[0.06] bg-[#fcfcfd] px-3 py-2 text-[12px] text-[#667085]">
          No active runs right now.
        </p>
      ) : null}
      <div className="space-y-2">
        {activeRuns.map((run) => (
          <button
            key={run.runId}
            type="button"
            onClick={() => onOpenRun?.(run.runId)}
            className={`w-full rounded-xl border bg-[#fcfcfd] px-3 py-2 text-left hover:border-black/[0.14] ${
              activeRunId && run.runId === activeRunId ? "border-[#c7d7fe] shadow-[0_0_0_1px_rgba(59,130,246,0.25)]" : "border-black/[0.06]"
            }`}
          >
            <p className="text-[13px] font-semibold text-[#111827]">{run.runId}</p>
            <p className="text-[12px] text-[#667085]">
              {run.triggerType} · {run.stage} · {run.elapsedSeconds}s · started {formatRelativeTime(run.startedAt)}
            </p>
          </button>
        ))}
      </div>
    </div>
  );
}

export type { LiveRunMonitorRecord };
