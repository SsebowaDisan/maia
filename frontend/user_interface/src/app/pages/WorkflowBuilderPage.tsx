import { useEffect, useState } from "react";
import { toast } from "sonner";

import { listAgents, type AgentSummaryRecord } from "../../api/client";
import {
  createWorkflowRecord,
  generateWorkflowFromDescription,
  listWorkflowRunHistory,
  listWorkflowTemplates,
  runWorkflowWithStream,
  streamGenerateWorkflowFromDescription,
  updateWorkflowRecord,
  type SaveWorkflowPayload,
} from "../../api/client/workflows";
import type { WorkflowDefinition, WorkflowRunRecord, WorkflowTemplate } from "../../api/client/types";
import { applyWorkflowRunEvent } from "../appShell/workflowEventHelpers";
import { WorkflowCanvas } from "../components/workflowCanvas/WorkflowCanvas";
import { useWorkflowStore } from "../stores/workflowStore";

function normalizeWorkflowRecordName(record: { name?: string; definition?: { name?: string } }) {
  const direct = String(record.name || "").trim();
  if (direct) {
    return direct;
  }
  const nested = String(record.definition?.name || "").trim();
  return nested || "Untitled workflow";
}

function toWorkflowSavePayload(
  definition: WorkflowDefinition,
  workflowName: string,
  workflowDescription: string,
): SaveWorkflowPayload {
  return {
    name: String(workflowName || definition.name || "Untitled workflow").trim() || "Untitled workflow",
    description: String(workflowDescription || definition.description || "").trim(),
    definition,
  };
}

export function WorkflowBuilderPage() {
  const workflowId = useWorkflowStore((state) => state.workflowId);
  const workflowName = useWorkflowStore((state) => state.workflowName);
  const workflowDescription = useWorkflowStore((state) => state.workflowDescription);
  const isDirty = useWorkflowStore((state) => state.isDirty);
  const loadDefinition = useWorkflowStore((state) => state.loadDefinition);
  const toDefinition = useWorkflowStore((state) => state.toDefinition);
  const markSaved = useWorkflowStore((state) => state.markSaved);
  const clearRun = useWorkflowStore((state) => state.clearRun);
  const startRun = useWorkflowStore((state) => state.startRun);
  const setRunStatus = useWorkflowStore((state) => state.setRunStatus);
  const setNodeRunState = useWorkflowStore((state) => state.setNodeRunState);
  const hydrateRunOutputs = useWorkflowStore((state) => state.hydrateRunOutputs);

  const [agents, setAgents] = useState<AgentSummaryRecord[]>([]);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);

  const [templates, setTemplates] = useState<WorkflowTemplate[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);

  const [runHistory, setRunHistory] = useState<WorkflowRunRecord[]>([]);
  const [runHistoryLoading, setRunHistoryLoading] = useState(false);

  const [nlGenerating, setNlGenerating] = useState(false);
  const [nlStreamLog, setNlStreamLog] = useState("");
  const [nlError, setNlError] = useState("");

  const refreshTemplates = async () => {
    setTemplatesLoading(true);
    try {
      const rows = await listWorkflowTemplates().catch(() => []);
      setTemplates(Array.isArray(rows) ? rows : []);
    } finally {
      setTemplatesLoading(false);
    }
  };

  const refreshRunHistory = async (targetWorkflowId?: string | null) => {
    const recordId = String(targetWorkflowId || workflowId || "").trim();
    if (!recordId) {
      setRunHistory([]);
      return;
    }
    setRunHistoryLoading(true);
    try {
      const rows = await listWorkflowRunHistory(recordId).catch(() => []);
      setRunHistory(Array.isArray(rows) ? rows : []);
    } finally {
      setRunHistoryLoading(false);
    }
  };

  const loadInitialData = async () => {
    try {
      const [agentRows] = await Promise.all([listAgents(), refreshTemplates()]);
      setAgents(Array.isArray(agentRows) ? agentRows : []);
    } catch (error) {
      toast.error(`Failed to load workflow data: ${String(error)}`);
    }
  };

  useEffect(() => {
    void loadInitialData();
  }, []);

  useEffect(() => {
    void refreshRunHistory(workflowId);
  }, [workflowId]);

  const persistWorkflow = async (): Promise<string | null> => {
    const definition = toDefinition();
    const payload = toWorkflowSavePayload(definition, workflowName, workflowDescription);

    setSaving(true);
    try {
      const response = workflowId
        ? await updateWorkflowRecord(workflowId, payload)
        : await createWorkflowRecord(payload);

      const nextWorkflowId = String(response.id || workflowId || "").trim();
      if (!nextWorkflowId) {
        throw new Error("No workflow id returned from save.");
      }

      useWorkflowStore.getState().setMetadata({
        workflowId: nextWorkflowId,
        workflowName: normalizeWorkflowRecordName(response),
        workflowDescription: String(response.description || ""),
      });
      markSaved();
      await refreshRunHistory(nextWorkflowId);
      toast.success("Workflow saved.");
      return nextWorkflowId;
    } catch (error) {
      toast.error(`Failed to save workflow: ${String(error)}`);
      return null;
    } finally {
      setSaving(false);
    }
  };

  const runWorkflow = async () => {
    let recordId = String(workflowId || "").trim();
    if (!recordId) {
      const saved = await persistWorkflow();
      if (!saved) {
        return;
      }
      recordId = saved;
    }

    setRunning(true);
    setRunStatus("running");
    setNlError("");

    try {
      await runWorkflowWithStream(recordId, {
        onEvent: (event) => {
          if (event.event_type === "run_started") {
            const runId = String((event as { run_id?: string }).run_id || "").trim();
            if (runId) {
              startRun(runId);
            }
          }
          applyWorkflowRunEvent(event);
        },
        onDone: () => {
          toast.success("Workflow run completed.");
        },
        onError: (error) => {
          toast.error(`Workflow stream failed: ${String(error.message || error)}`);
        },
      });
      await refreshRunHistory(recordId);
    } catch (error) {
      setRunStatus("failed");
      toast.error(`Workflow run failed: ${String(error)}`);
    } finally {
      setRunning(false);
    }
  };

  const generateFromDescription = async (description: string, maxSteps: number): Promise<boolean> => {
    const normalizedDescription = String(description || "").trim();
    if (!normalizedDescription) {
      setNlError("Description is required.");
      return false;
    }

    setNlGenerating(true);
    setNlError("");
    setNlStreamLog("");

    let streamedDefinition: WorkflowDefinition | null = null;
    try {
      await streamGenerateWorkflowFromDescription(normalizedDescription, {
        maxSteps,
        onEvent: (event) => {
          if (event.event_type === "nl_build_error") {
            const errorText = String((event as { error?: string }).error || "Generation failed").trim();
            setNlError(errorText);
            return;
          }
          if (event.event_type === "nl_build_delta") {
            const delta = String((event as { delta?: string }).delta || "");
            if (delta) {
              setNlStreamLog((previous) => `${previous}${delta}`);
            }
            const definition = (event as { definition?: WorkflowDefinition }).definition;
            if (definition && Array.isArray(definition.steps)) {
              streamedDefinition = definition;
            }
          }
        },
      });

      if (!streamedDefinition) {
        const generated = await generateWorkflowFromDescription(normalizedDescription, maxSteps);
        streamedDefinition = generated.definition;
      }

      if (!streamedDefinition) {
        throw new Error("No workflow definition generated.");
      }

      loadDefinition(streamedDefinition, { workflowId: null, activeTemplateId: null });
      useWorkflowStore.getState().setMetadata({
        workflowId: null,
        workflowName: String(streamedDefinition.name || "Generated workflow"),
        workflowDescription: String(streamedDefinition.description || normalizedDescription),
      });
      toast.success("Workflow generated. Review and save when ready.");
      return true;
    } catch (error) {
      setNlError(String(error));
      return false;
    } finally {
      setNlGenerating(false);
    }
  };

  const applyTemplate = (template: WorkflowTemplate) => {
    loadDefinition(template.definition, {
      workflowId: null,
      activeTemplateId: template.template_id,
    });
    useWorkflowStore.getState().setMetadata({
      workflowId: null,
      workflowName: template.name,
      workflowDescription: template.description,
      activeTemplateId: template.template_id,
    });
    setRunHistory([]);
    clearRun();
    toast.success(`Loaded template: ${template.name}`);
  };

  const loadRunOutputs = (run: WorkflowRunRecord) => {
    startRun(String(run.run_id || "").trim() || `run_${Date.now()}`);
    hydrateRunOutputs(Array.isArray(run.step_results) ? run.step_results : []);
    for (const row of run.step_results || []) {
      const stepId = String(row.step_id || "").trim();
      if (!stepId) {
        continue;
      }
      const normalizedStatus = String(row.status || "").trim().toLowerCase();
      if (normalizedStatus === "completed") {
        setNodeRunState(stepId, "completed");
      } else if (normalizedStatus === "failed") {
        setNodeRunState(stepId, "failed");
      } else if (normalizedStatus === "skipped") {
        setNodeRunState(stepId, "skipped");
      }
    }
    if (run.status === "completed") {
      setRunStatus("completed");
    } else if (run.status === "failed") {
      setRunStatus("failed");
    }
    toast.success("Loaded run outputs onto canvas.");
  };

  return (
    <div className="h-full overflow-hidden bg-[#eef1f5] p-3">
      <div className="mx-auto flex h-full max-w-[1540px] min-h-0 flex-col">
        <section className="min-h-0 flex-1">
          <WorkflowCanvas
            agents={agents}
            isRunning={running}
            isDirty={isDirty}
            templates={templates}
            templatesLoading={templatesLoading}
            runHistory={runHistory}
            runHistoryLoading={runHistoryLoading}
            nlGenerating={nlGenerating}
            nlStreamLog={nlStreamLog}
            nlError={nlError}
            onRun={() => {
              void runWorkflow();
            }}
            onStop={() => {
              toast.info("Stop is not available yet for in-flight workflow runs.");
            }}
            onSave={() => {
              void persistWorkflow();
            }}
            onRefreshTemplates={() => {
              void refreshTemplates();
            }}
            onRefreshRunHistory={() => {
              void refreshRunHistory();
            }}
            onGenerateFromDescription={generateFromDescription}
            onSelectTemplate={applyTemplate}
            onLoadRunOutputs={loadRunOutputs}
          />
        </section>
      </div>
    </div>
  );
}
