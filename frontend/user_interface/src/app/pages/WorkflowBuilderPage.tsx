import { useMemo, useState } from "react";
import { toast } from "sonner";

import { MultiAgentTheatre } from "../components/agentActivityPanel/MultiAgentTheatre";
import { AGENT_OS_AGENTS } from "./agentOsData";

type WorkflowStep = {
  stepId: string;
  agentId: string;
  condition: string;
};

export function WorkflowBuilderPage() {
  const [steps, setSteps] = useState<WorkflowStep[]>([
    { stepId: "step_1", agentId: AGENT_OS_AGENTS[0]?.id || "proposal-writer", condition: "always" },
    { stepId: "step_2", agentId: AGENT_OS_AGENTS[1]?.id || "deal-summary", condition: "output.status == success" },
  ]);

  const addStep = () => {
    const next = AGENT_OS_AGENTS[steps.length % AGENT_OS_AGENTS.length];
    setSteps((previous) => [
      ...previous,
      {
        stepId: `step_${previous.length + 1}`,
        agentId: next.id,
        condition: "always",
      },
    ]);
  };

  const theatreColumns = useMemo(
    () =>
      steps.map((step, index) => {
        const agent = AGENT_OS_AGENTS.find((item) => item.id === step.agentId);
        return {
          agentId: step.agentId,
          agentName: agent?.name || step.agentId,
          status: (index === 0 ? "done" : index === steps.length - 1 ? "running" : "pending") as
            | "pending"
            | "running"
            | "done"
            | "blocked",
          events: [
            `Condition: ${step.condition}`,
            "Input mapping ready",
            "Output key assigned",
          ],
        };
      }),
    [steps],
  );

  return (
    <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
      <div className="mx-auto max-w-[1320px] space-y-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5">
          <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">Workflow builder</p>
          <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">Compose multi-agent workflows</h1>
          <div className="mt-4 flex gap-2">
            <button
              type="button"
              onClick={addStep}
              className="rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[12px] font-semibold text-[#344054]"
            >
              Add step
            </button>
            <button
              type="button"
              onClick={() => toast.success("Workflow run started. Opening theatre...")}
              className="rounded-full bg-[#111827] px-4 py-2 text-[12px] font-semibold text-white"
            >
              Run workflow
            </button>
          </div>
        </section>

        <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
          <h2 className="text-[18px] font-semibold text-[#111827]">Workflow steps</h2>
          <div className="mt-3 space-y-2">
            {steps.map((step, index) => (
              <div key={step.stepId} className="grid grid-cols-1 gap-2 rounded-xl border border-black/[0.06] bg-[#fcfcfd] p-3 md:grid-cols-[1fr_1fr_1.2fr_auto]">
                <p className="text-[13px] font-semibold text-[#111827]">{step.stepId}</p>
                <select
                  value={step.agentId}
                  onChange={(event) =>
                    setSteps((previous) =>
                      previous.map((row, rowIndex) =>
                        rowIndex === index ? { ...row, agentId: event.target.value } : row,
                      ),
                    )
                  }
                  className="rounded-lg border border-black/[0.12] px-2 py-1 text-[12px]"
                >
                  {AGENT_OS_AGENTS.map((agent) => (
                    <option key={agent.id} value={agent.id}>
                      {agent.name}
                    </option>
                  ))}
                </select>
                <input
                  value={step.condition}
                  onChange={(event) =>
                    setSteps((previous) =>
                      previous.map((row, rowIndex) =>
                        rowIndex === index ? { ...row, condition: event.target.value } : row,
                      ),
                    )
                  }
                  className="rounded-lg border border-black/[0.12] px-2 py-1 text-[12px]"
                />
                <button
                  type="button"
                  onClick={() =>
                    setSteps((previous) => previous.filter((row) => row.stepId !== step.stepId))
                  }
                  className="rounded-lg border border-[#fecaca] bg-[#fff1f2] px-2 py-1 text-[12px] font-semibold text-[#b42318]"
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        </section>

        <MultiAgentTheatre columns={theatreColumns} />
      </div>
    </div>
  );
}

