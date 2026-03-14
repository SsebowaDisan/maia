import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import {
  createWorkflow,
  listAgents,
  listPlaybooks,
  listSchedules,
  listWorkflows,
  runWorkflow,
  updateWorkflow,
  type AgentPlaybookRecord,
  type AgentScheduleRecord,
  type AgentSummaryRecord,
  type WorkflowDefinitionInput,
  type WorkflowRunEvent,
  type WorkflowSummaryRecord,
} from "../../api/client";
import { MultiAgentTheatre } from "../components/agentActivityPanel/MultiAgentTheatre";

type WorkflowStep = {
  stepId: string;
  agentId: string;
  condition: string;
};

type StepStatus = "pending" | "running" | "done" | "blocked";

function defaultSteps(agents: AgentSummaryRecord[]): WorkflowStep[] {
  if (!agents.length) {
    return [];
  }
  if (agents.length === 1) {
    return [{ stepId: "step_1", agentId: agents[0].agent_id, condition: "always" }];
  }
  return [
    { stepId: "step_1", agentId: agents[0].agent_id, condition: "always" },
    { stepId: "step_2", agentId: agents[1].agent_id, condition: "output.status == success" },
  ];
}

function createWorkflowDefinition(
  workflowId: string,
  workflowName: string,
  steps: WorkflowStep[],
): WorkflowDefinitionInput {
  const normalizedId = String(workflowId || "").trim() || `wf_${Date.now()}`;
  const normalizedName = String(workflowName || "").trim() || "Untitled workflow";
  const definitionSteps = steps.map((step, index) => {
    const outputKey = `${step.stepId}_output`;
    const previousOutputKey = index > 0 ? `${steps[index - 1].stepId}_output` : "";
    const inputMapping =
      index === 0
        ? { message: "literal:Execute the initial workflow step with the user request." }
        : { message: previousOutputKey };
    return {
      step_id: step.stepId,
      agent_id: step.agentId,
      input_mapping: inputMapping,
      output_key: outputKey,
    };
  });
  const definitionEdges = steps.slice(1).map((step, index) => {
    const condition = String(step.condition || "").trim();
    return {
      from_step: steps[index].stepId,
      to_step: step.stepId,
      condition: !condition || condition.toLowerCase() === "always" ? undefined : condition,
    };
  });
  return {
    workflow_id: normalizedId,
    name: normalizedName,
    steps: definitionSteps,
    edges: definitionEdges,
  };
}

function initialStepStatuses(steps: WorkflowStep[]): Record<string, StepStatus> {
  const statuses: Record<string, StepStatus> = {};
  for (const [index, step] of steps.entries()) {
    statuses[step.stepId] = index === 0 ? "running" : "pending";
  }
  return statuses;
}

export function WorkflowBuilderPage() {
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [agents, setAgents] = useState<AgentSummaryRecord[]>([]);
  const [playbooks, setPlaybooks] = useState<AgentPlaybookRecord[]>([]);
  const [schedules, setSchedules] = useState<AgentScheduleRecord[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowSummaryRecord[]>([]);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState("");
  const [workflowName, setWorkflowName] = useState("New workflow");
  const [steps, setSteps] = useState<WorkflowStep[]>([]);
  const [savingWorkflow, setSavingWorkflow] = useState(false);
  const [runningWorkflow, setRunningWorkflow] = useState(false);
  const [stepStatuses, setStepStatuses] = useState<Record<string, StepStatus>>({});
  const [stepLogs, setStepLogs] = useState<Record<string, string[]>>({});

  const loadWorkflowData = async () => {
    setLoading(true);
    setLoadError("");
    try {
      const [agentRows, playbookRows, scheduleRows, workflowRows] = await Promise.all([
        listAgents(),
        listPlaybooks({ limit: 50 }),
        listSchedules(),
        listWorkflows().catch(() => [] as WorkflowSummaryRecord[]),
      ]);
      setAgents(agentRows || []);
      setPlaybooks(playbookRows || []);
      setSchedules(scheduleRows || []);
      setWorkflows(workflowRows || []);
      setSteps((previous) => (previous.length ? previous : defaultSteps(agentRows || [])));
    } catch (error) {
      setLoadError(`Failed to load workflow data: ${String(error)}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadWorkflowData();
  }, []);

  useEffect(() => {
    if (!selectedWorkflowId) {
      return;
    }
    const selected = workflows.find((row) => row.workflow_id === selectedWorkflowId);
    if (selected?.name) {
      setWorkflowName(selected.name);
    }
  }, [selectedWorkflowId, workflows]);

  const addStep = () => {
    if (!agents.length) {
      toast.error("No agents available. Create an agent first.");
      return;
    }
    const nextAgent = agents[steps.length % agents.length];
    setSteps((previous) => [
      ...previous,
      {
        stepId: `step_${previous.length + 1}`,
        agentId: nextAgent.agent_id,
        condition: "always",
      },
    ]);
  };

  const saveWorkflowDefinition = async (): Promise<string | null> => {
    if (!steps.length) {
      toast.error("Add at least one step before saving.");
      return null;
    }
    const definition = createWorkflowDefinition(selectedWorkflowId, workflowName, steps);
    setSavingWorkflow(true);
    try {
      const response = selectedWorkflowId
        ? await updateWorkflow(selectedWorkflowId, definition)
        : await createWorkflow(definition);
      const nextWorkflowId = String(
        response?.workflow_id || definition.workflow_id || selectedWorkflowId,
      ).trim();
      if (!nextWorkflowId) {
        toast.error("Workflow saved but no id was returned.");
        return null;
      }
      setSelectedWorkflowId(nextWorkflowId);
      setWorkflowName(String(response?.name || definition.name || workflowName));
      toast.success("Workflow saved.");
      const rows = await listWorkflows().catch(() => [] as WorkflowSummaryRecord[]);
      setWorkflows(rows || []);
      return nextWorkflowId;
    } catch (error) {
      toast.error(`Failed to save workflow: ${String(error)}`);
      return null;
    } finally {
      setSavingWorkflow(false);
    }
  };

  const appendStepLog = (stepId: string, message: string) => {
    const normalizedStepId = String(stepId || "").trim();
    if (!normalizedStepId) {
      return;
    }
    const text = String(message || "").trim();
    if (!text) {
      return;
    }
    setStepLogs((previous) => {
      const current = previous[normalizedStepId] || [];
      const next = [...current, text];
      return { ...previous, [normalizedStepId]: next.slice(-8) };
    });
  };

  const handleWorkflowRunEvent = (event: WorkflowRunEvent) => {
    const eventType = String(event.event_type || "").trim().toLowerCase();
    const stepId = String(event.step_id || "").trim();
    if (!eventType) {
      return;
    }
    if (eventType === "workflow_step_started" && stepId) {
      setStepStatuses((previous) => ({ ...previous, [stepId]: "running" }));
      appendStepLog(stepId, "Step started");
      return;
    }
    if (eventType === "workflow_step_completed" && stepId) {
      setStepStatuses((previous) => ({ ...previous, [stepId]: "done" }));
      appendStepLog(stepId, String(event.result_preview || "Step completed"));
      return;
    }
    if (eventType === "workflow_step_failed" && stepId) {
      setStepStatuses((previous) => ({ ...previous, [stepId]: "blocked" }));
      appendStepLog(stepId, String(event.error || "Step failed"));
      return;
    }
    if (eventType === "workflow_step_skipped" && stepId) {
      setStepStatuses((previous) => ({ ...previous, [stepId]: "pending" }));
      appendStepLog(stepId, "Step skipped");
      return;
    }
    if (eventType === "workflow_completed") {
      setStepStatuses((previous) => {
        const next: Record<string, StepStatus> = { ...previous };
        for (const step of steps) {
          if (next[step.stepId] !== "blocked") {
            next[step.stepId] = "done";
          }
        }
        return next;
      });
      return;
    }
    if (stepId && event.detail) {
      appendStepLog(stepId, String(event.detail));
    }
  };

  const runSelectedWorkflow = async () => {
    let workflowId = selectedWorkflowId;
    if (!workflowId) {
      const savedWorkflowId = await saveWorkflowDefinition();
      if (!savedWorkflowId) {
        return;
      }
      workflowId = savedWorkflowId;
    }
    setRunningWorkflow(true);
    setStepStatuses(initialStepStatuses(steps));
    setStepLogs({});
    toast.info("Workflow run started.");
    try {
      await runWorkflow(workflowId, {
        onEvent: handleWorkflowRunEvent,
        onDone: () => {
          toast.success("Workflow completed.");
        },
        onError: (error) => {
          toast.error(`Workflow stream failed: ${String(error.message || error)}`);
        },
      });
    } catch (error) {
      toast.error(`Workflow run failed: ${String(error)}`);
    } finally {
      setRunningWorkflow(false);
    }
  };

  const theatreColumns = useMemo(
    () =>
      steps.map((step) => {
        const agent = agents.find((item) => item.agent_id === step.agentId);
        const logs = stepLogs[step.stepId] || [];
        return {
          agentId: step.agentId || step.stepId,
          agentName: agent?.name || step.agentId || step.stepId,
          status: (stepStatuses[step.stepId] || "pending") as StepStatus,
          events: logs.length
            ? logs
            : [`Condition: ${step.condition || "always"}`, "Input mapping ready", "Output key assigned"],
        };
      }),
    [agents, stepLogs, stepStatuses, steps],
  );

  return (
    <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
      <div className="mx-auto max-w-[1320px] space-y-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5">
          <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">
            Workflow builder
          </p>
          <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">
            Compose multi-agent workflows
          </h1>
          <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-[1fr_1fr_auto_auto_auto]">
            <label className="rounded-xl border border-black/[0.08] bg-[#fcfcfd] px-3 py-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[#667085]">Workflow name</span>
              <input
                value={workflowName}
                onChange={(event) => setWorkflowName(event.target.value)}
                className="mt-1 w-full border-0 bg-transparent p-0 text-[13px] font-semibold text-[#111827] outline-none"
              />
            </label>
            <label className="rounded-xl border border-black/[0.08] bg-[#fcfcfd] px-3 py-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[#667085]">Saved workflows</span>
              <select
                value={selectedWorkflowId}
                onChange={(event) => setSelectedWorkflowId(event.target.value)}
                className="mt-1 w-full border-0 bg-transparent p-0 text-[13px] text-[#111827] outline-none"
              >
                <option value="">New workflow</option>
                {workflows.map((workflow) => (
                  <option key={workflow.workflow_id} value={workflow.workflow_id}>
                    {workflow.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={addStep}
              className="rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[12px] font-semibold text-[#344054]"
            >
              Add step
            </button>
            <button
              type="button"
              onClick={() => {
                void saveWorkflowDefinition();
              }}
              disabled={savingWorkflow}
              className="rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[12px] font-semibold text-[#344054] disabled:opacity-60"
            >
              {savingWorkflow ? "Saving..." : "Save workflow"}
            </button>
            <button
              type="button"
              onClick={() => {
                void runSelectedWorkflow();
              }}
              disabled={runningWorkflow}
              className="rounded-full bg-[#111827] px-4 py-2 text-[12px] font-semibold text-white disabled:opacity-60"
            >
              {runningWorkflow ? "Running..." : "Run workflow"}
            </button>
          </div>
        </section>

        {loadError ? (
          <section className="rounded-2xl border border-[#fca5a5] bg-[#fff1f2] p-4 text-[13px] text-[#9f1239]">
            {loadError}
          </section>
        ) : null}

        {loading ? (
          <section className="rounded-2xl border border-black/[0.08] bg-white p-4 text-[13px] text-[#667085]">
            Loading workflows...
          </section>
        ) : null}

        <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <article className="rounded-2xl border border-black/[0.08] bg-white p-4">
            <h2 className="text-[18px] font-semibold text-[#111827]">Saved playbooks</h2>
            <div className="mt-3 space-y-2">
              {playbooks.length === 0 ? (
                <p className="rounded-xl border border-black/[0.06] bg-[#fcfcfd] p-3 text-[12px] text-[#667085]">
                  No playbooks saved yet.
                </p>
              ) : (
                playbooks.map((playbook) => (
                  <div key={playbook.id} className="rounded-xl border border-black/[0.06] bg-[#fcfcfd] p-3">
                    <p className="text-[13px] font-semibold text-[#111827]">{playbook.name}</p>
                    <p className="mt-1 text-[12px] text-[#667085]">
                      {playbook.tool_ids.length} tools · v{playbook.version || 1}
                    </p>
                  </div>
                ))
              )}
            </div>
          </article>

          <article className="rounded-2xl border border-black/[0.08] bg-white p-4">
            <h2 className="text-[18px] font-semibold text-[#111827]">Scheduled workflows</h2>
            <div className="mt-3 space-y-2">
              {schedules.length === 0 ? (
                <p className="rounded-xl border border-black/[0.06] bg-[#fcfcfd] p-3 text-[12px] text-[#667085]">
                  No schedules configured.
                </p>
              ) : (
                schedules.map((schedule) => (
                  <div key={schedule.id} className="rounded-xl border border-black/[0.06] bg-[#fcfcfd] p-3">
                    <p className="text-[13px] font-semibold text-[#111827]">{schedule.name}</p>
                    <p className="mt-1 text-[12px] text-[#667085]">
                      {schedule.frequency} · {schedule.enabled ? "enabled" : "paused"}
                    </p>
                    <p className="mt-1 text-[11px] text-[#98a2b3]">
                      Next run:{" "}
                      {schedule.next_run_at ? new Date(schedule.next_run_at).toLocaleString() : "n/a"}
                    </p>
                  </div>
                ))
              )}
            </div>
          </article>
        </section>

        <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
          <h2 className="text-[18px] font-semibold text-[#111827]">Workflow steps</h2>
          <div className="mt-3 space-y-2">
            {steps.map((step, index) => (
              <div
                key={step.stepId}
                className="grid grid-cols-1 gap-2 rounded-xl border border-black/[0.06] bg-[#fcfcfd] p-3 md:grid-cols-[1fr_1fr_1.2fr_auto]"
              >
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
                  {agents.map((agent) => (
                    <option key={agent.agent_id} value={agent.agent_id}>
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
