import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import {
  listAgentApiRuns,
  listAgents,
  type AgentApiRunRecord,
  type AgentSummaryRecord,
} from "../../api/client";
import { LiveRunMonitor, type LiveRunMonitorRecord } from "../components/observability/LiveRunMonitor";
import { RunErrorLog, type RunErrorRecord } from "../components/observability/RunErrorLog";
import { BudgetSettings } from "../components/workspace/BudgetSettings";

type OperationsRunRecord = LiveRunMonitorRecord &
  RunErrorRecord & {
    llmCostUsd: number;
  };

function deriveDurationMs(startedAt: string, endedAt?: string | null, fallback?: number | null): number {
  if (typeof fallback === "number" && Number.isFinite(fallback) && fallback >= 0) {
    return fallback;
  }
  const start = new Date(startedAt).getTime();
  const end = endedAt ? new Date(endedAt).getTime() : Date.now();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) {
    return 0;
  }
  return end - start;
}

function normalizeApiRun(row: AgentApiRunRecord): OperationsRunRecord | null {
  const runId = String(row.run_id || row.id || "").trim();
  if (!runId) {
    return null;
  }
  const startedAt = String(row.started_at || row.date_created || new Date().toISOString());
  const endedAt = typeof row.ended_at === "string" ? row.ended_at : null;
  return {
    runId,
    agentId: String(row.agent_id || "unknown"),
    triggerType: String(row.trigger_type || "manual"),
    status: String(row.status || "unknown"),
    startedAt,
    durationMs: deriveDurationMs(startedAt, endedAt, row.duration_ms),
    llmCostUsd: Number(row.llm_cost_usd ?? row.cost_usd ?? 0) || 0,
    errorType: "",
    errorMessage: String(row.error || ""),
  };
}

export function OperationsDashboardPage() {
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [runs, setRuns] = useState<OperationsRunRecord[]>([]);
  const [agents, setAgents] = useState<AgentSummaryRecord[]>([]);

  const loadData = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const [runRows, agentRows] = await Promise.all([
        listAgentApiRuns({ limit: 200 }),
        listAgents(),
      ]);
      const normalizedRuns = (runRows || [])
        .map(normalizeApiRun)
        .filter((row): row is OperationsRunRecord => Boolean(row))
        .sort((left, right) => new Date(right.startedAt).getTime() - new Date(left.startedAt).getTime());
      setRuns(normalizedRuns);
      setAgents(agentRows || []);
    } catch (error) {
      setLoadError(`Failed to load operations telemetry: ${String(error)}`);
      setRuns([]);
      setAgents([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const successfulRuns = useMemo(
    () => runs.filter((run) => {
      const status = String(run.status || "").toLowerCase();
      return status === "success" || status === "completed";
    }).length,
    [runs],
  );
  const successRate = runs.length ? Math.round((successfulRuns / runs.length) * 100) : 0;
  const totalCost = useMemo(
    () => runs.reduce((total, run) => total + run.llmCostUsd, 0),
    [runs],
  );
  const activeRuns = useMemo(
    () =>
      runs.filter((run) => {
        const status = String(run.status || "").toLowerCase();
        return status === "running" || status === "queued" || status === "in_progress";
      }).length,
    [runs],
  );

  return (
    <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
      <div className="mx-auto max-w-[1300px] space-y-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5">
          <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">Operations</p>
          <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">Fleet reliability dashboard</h1>
        </section>

        {loadError ? (
          <section className="rounded-2xl border border-[#fca5a5] bg-[#fff1f2] p-4 text-[13px] text-[#9f1239]">
            {loadError}
          </section>
        ) : null}

        {loading ? (
          <section className="rounded-2xl border border-black/[0.08] bg-white p-4 text-[13px] text-[#667085]">
            Loading operations telemetry...
          </section>
        ) : null}

        <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <article className="rounded-2xl border border-black/[0.08] bg-white p-4">
            <p className="text-[12px] text-[#667085]">Runs tracked</p>
            <p className="mt-1 text-[26px] font-semibold text-[#111827]">{runs.length}</p>
          </article>
          <article className="rounded-2xl border border-black/[0.08] bg-white p-4">
            <p className="text-[12px] text-[#667085]">Success rate</p>
            <p className="mt-1 text-[26px] font-semibold text-[#111827]">{successRate}%</p>
          </article>
          <article className="rounded-2xl border border-black/[0.08] bg-white p-4">
            <p className="text-[12px] text-[#667085]">Cost today</p>
            <p className="mt-1 text-[26px] font-semibold text-[#111827]">${totalCost.toFixed(2)}</p>
          </article>
          <article className="rounded-2xl border border-black/[0.08] bg-white p-4">
            <p className="text-[12px] text-[#667085]">Active runs</p>
            <p className="mt-1 text-[26px] font-semibold text-[#111827]">{activeRuns}</p>
            <p className="mt-1 text-[11px] text-[#98a2b3]">{agents.length} registered agents</p>
          </article>
        </section>

        <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <LiveRunMonitor
            runs={runs}
            onOpenRun={(runId) => toast.message(`Opening run ${runId}`)}
          />
          <BudgetSettings currentCostUsd={totalCost} />
        </section>

        <RunErrorLog
          runs={runs}
          onOpenTheatre={(runId) => toast.message(`Opening theatre for ${runId}`)}
          onReplay={(runId) => toast.success(`Replaying ${runId}`)}
        />
      </div>
    </div>
  );
}
