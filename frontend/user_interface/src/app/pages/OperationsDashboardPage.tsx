import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getBudget,
  getCostSummary,
  listAgentApiRuns,
  listAgents,
  type AgentApiRunRecord,
  type AgentSummaryRecord,
  type BudgetResponse,
  type CostSummaryResponse,
} from "../../api/client";
import { InsightsFeedPanel } from "../components/agentActivityPanel/InsightsFeedPanel";
import { DashboardWidgetsTab } from "../components/operations/DashboardWidgetsTab";
import { ScheduledReviewsPanel } from "../components/agentActivityPanel/ScheduledReviewsPanel";
import { ROIDashboard } from "../components/canvas/ROIDashboard";
import { LiveRunMonitor, type LiveRunMonitorRecord } from "../components/observability/LiveRunMonitor";
import { RunErrorLog, type RunErrorRecord } from "../components/observability/RunErrorLog";
import { BudgetSettings } from "../components/workspace/BudgetSettings";
import { RunTimelinePage } from "./RunTimelinePage";

type OperationsRunRecord = LiveRunMonitorRecord &
  RunErrorRecord & {
    agentId: string;
    llmCostUsd: number;
  };

type OperationsTab = "overview" | "dashboard" | "reviews" | "roi" | "insights" | "timeline";

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
  const [activeTab, setActiveTab] = useState<OperationsTab>(() => {
    if (typeof window === "undefined") {
      return "overview";
    }
    const tab = new URLSearchParams(window.location.search).get("tab");
    if (
      tab === "reviews" ||
      tab === "roi" ||
      tab === "overview" ||
      tab === "dashboard" ||
      tab === "insights" ||
      tab === "timeline"
    ) {
      return tab;
    }
    return "overview";
  });
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [runs, setRuns] = useState<OperationsRunRecord[]>([]);
  const [agents, setAgents] = useState<AgentSummaryRecord[]>([]);
  const [budgetData, setBudgetData] = useState<BudgetResponse | null>(null);
  const [costData, setCostData] = useState<CostSummaryResponse | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const [runRows, agentRows, budget, cost] = await Promise.all([
        listAgentApiRuns({ limit: 200 }),
        listAgents(),
        getBudget().catch(() => null),
        getCostSummary(7).catch(() => null),
      ]);
      const normalizedRuns = (runRows || [])
        .map(normalizeApiRun)
        .filter((row): row is OperationsRunRecord => Boolean(row))
        .sort((left, right) => new Date(right.startedAt).getTime() - new Date(left.startedAt).getTime());
      setRuns(normalizedRuns);
      setAgents(agentRows || []);
      setBudgetData(budget);
      setCostData(cost);
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
  const todayCostUsdFromRuns = useMemo(
    () => runs.reduce((total, run) => total + run.llmCostUsd, 0),
    [runs],
  );
  // Prefer backend cost data (tracks all LLM + Computer Use spend); fall back to run-level sum
  const todayCostUsd = budgetData?.today_cost_usd ?? todayCostUsdFromRuns;
  const weekCosts = costData?.daily_costs ?? [];
  const activeRuns = useMemo(
    () =>
      runs.filter((run) => {
        const status = String(run.status || "").toLowerCase();
        return status === "running" || status === "queued" || status === "in_progress";
      }).length,
    [runs],
  );

  return (
    <div className="h-full overflow-y-auto bg-[#f6f6f7] p-5">
      <div className="mx-auto max-w-[1300px] space-y-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5">
          <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">Operations</p>
          <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">Fleet reliability dashboard</h1>
          <div className="mt-4 flex items-center gap-2">
            {([
              { key: "overview", label: "Overview" },
              { key: "dashboard", label: "Dashboard" },
              { key: "insights", label: "Insights" },
              { key: "timeline", label: "Timeline" },
              { key: "reviews", label: "Business Reviews" },
              { key: "roi", label: "ROI" },
            ] as const).map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setActiveTab(tab.key)}
                className={`rounded-full px-3.5 py-2 text-[12px] font-semibold transition ${
                  activeTab === tab.key
                    ? "bg-[#7c3aed] text-white shadow-[0_1px_3px_rgba(124,58,237,0.3)]"
                    : "border border-black/[0.12] bg-white text-[#344054]"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </section>

        {activeTab === "overview" && loadError ? (
          <section className="rounded-2xl border border-[#fca5a5] bg-[#fff1f2] p-4 text-[13px] text-[#9f1239]">
            {loadError}
          </section>
        ) : null}

        {activeTab === "overview" && loading ? (
          <section className="rounded-2xl border border-black/[0.08] bg-white p-4 text-[13px] text-[#667085]">
            Loading operations telemetry...
          </section>
        ) : null}

        {activeTab === "overview" ? (
          <>
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
            <p className="mt-1 text-[26px] font-semibold text-[#111827]">${todayCostUsd.toFixed(2)}</p>
          </article>
          <article className="rounded-2xl border border-black/[0.08] bg-white p-4">
            <p className="text-[12px] text-[#667085]">Active runs</p>
            <p className="mt-1 text-[26px] font-semibold text-[#111827]">{activeRuns}</p>
            <p className="mt-1 text-[11px] text-[#98a2b3]">{agents.length} registered agents</p>
          </article>
        </section>

        <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <LiveRunMonitor runs={runs} />
          <BudgetSettings currentCostUsd={todayCostUsd} />
        </section>

        {weekCosts.length > 0 ? (
          <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
            <h3 className="text-[18px] font-semibold text-[#111827]">7-day cost trend</h3>
            <p className="mt-1 text-[13px] text-[#667085]">Daily LLM + Computer Use spend.</p>
            <div className="mt-3 flex items-end gap-1" style={{ height: 80 }}>
              {weekCosts
                .slice()
                .reverse()
                .map((day) => {
                  const maxCost = Math.max(...weekCosts.map((d) => d.total_cost_usd), 0.01);
                  const pct = Math.max(4, (day.total_cost_usd / maxCost) * 100);
                  return (
                    <div key={day.date_key} className="flex flex-1 flex-col items-center gap-1">
                      <div
                        className="w-full rounded-t-md bg-[#7c3aed]"
                        style={{ height: `${pct}%` }}
                        title={`$${day.total_cost_usd.toFixed(4)} on ${day.date_key}`}
                      />
                      <span className="text-[10px] text-[#98a2b3]">
                        {day.date_key.slice(5)}
                      </span>
                    </div>
                  );
                })}
            </div>
          </section>
        ) : null}

        <RunErrorLog runs={runs} />
          </>
        ) : null}

        {activeTab === "reviews" ? (
          <section className="rounded-2xl border border-black/[0.08] bg-white p-0">
            <div className="h-[720px] min-h-0">
              <ScheduledReviewsPanel />
            </div>
          </section>
        ) : null}

        {activeTab === "roi" ? (
          <section className="rounded-2xl border border-black/[0.08] bg-white p-0">
            <ROIDashboard className="h-[720px] overflow-y-auto" />
          </section>
        ) : null}

        {activeTab === "insights" ? (
          <section className="rounded-2xl border border-black/[0.08] bg-white p-0">
            <div className="h-[720px] min-h-0">
              <InsightsFeedPanel className="h-full" />
            </div>
          </section>
        ) : null}

        {activeTab === "dashboard" ? (
          <DashboardWidgetsTab agents={agents} />
        ) : null}

        {activeTab === "timeline" ? (
          <section className="rounded-2xl border border-black/[0.08] bg-white p-0">
            <div className="h-[720px] min-h-0 overflow-y-auto">
              <RunTimelinePage />
            </div>
          </section>
        ) : null}
      </div>
    </div>
  );
}
