import { toast } from "sonner";

import { LiveRunMonitor } from "../components/observability/LiveRunMonitor";
import { RunErrorLog } from "../components/observability/RunErrorLog";
import { BudgetSettings } from "../components/workspace/BudgetSettings";
import { AGENT_OS_AGENTS, AGENT_OS_RUNS } from "./agentOsData";

export function OperationsDashboardPage() {
  const successfulRuns = AGENT_OS_RUNS.filter((run) => run.status === "success").length;
  const successRate = AGENT_OS_RUNS.length ? Math.round((successfulRuns / AGENT_OS_RUNS.length) * 100) : 0;
  const totalCost = AGENT_OS_RUNS.reduce((total, run) => total + run.llmCostUsd, 0);

  return (
    <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
      <div className="mx-auto max-w-[1300px] space-y-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5">
          <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">Operations</p>
          <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">Fleet reliability dashboard</h1>
        </section>

        <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <article className="rounded-2xl border border-black/[0.08] bg-white p-4">
            <p className="text-[12px] text-[#667085]">Runs today</p>
            <p className="mt-1 text-[26px] font-semibold text-[#111827]">{AGENT_OS_RUNS.length}</p>
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
            <p className="text-[12px] text-[#667085]">Active agents</p>
            <p className="mt-1 text-[26px] font-semibold text-[#111827]">
              {AGENT_OS_AGENTS.filter((agent) => agent.status === "active").length}
            </p>
          </article>
        </section>

        <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <LiveRunMonitor onOpenRun={(runId) => toast.message(`Opening run ${runId}`)} />
          <BudgetSettings currentCostUsd={totalCost} />
        </section>

        <RunErrorLog
          runs={AGENT_OS_RUNS}
          onOpenTheatre={(runId) => toast.message(`Opening theatre for ${runId}`)}
          onReplay={(runId) => toast.success(`Replaying ${runId}`)}
        />
      </div>
    </div>
  );
}

