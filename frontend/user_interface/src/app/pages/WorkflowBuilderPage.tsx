import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { listAgents, listMarketplaceAgents } from "../../api/client";

import {
  createWorkflowRecord,
  generateWorkflowFromDescription,
  listWorkflowRunHistory,
  listWorkflowTemplates,
  streamGenerateWorkflowFromDescription,
  updateWorkflowRecord,
  validateWorkflowDefinition,
  type SaveWorkflowPayload,
} from "../../api/client/workflows";
import type { WorkflowDefinition, WorkflowRecord, WorkflowRunRecord, WorkflowTemplate } from "../../api/client/types";
import { WorkflowCanvas } from "../components/workflowCanvas/WorkflowCanvas";
import { WorkflowGallery } from "../components/workflowCanvas/WorkflowGallery";
import { WorkflowQuickSwitcher } from "../components/workflowCanvas/WorkflowQuickSwitcher";
import { useWorkflowStore } from "../stores/workflowStore";
import { useWorkflowViewStore } from "../stores/workflowViewStore";

const MAX_WORKFLOW_NAME_LENGTH = 60;

function clampWorkflowName(raw: string): string {
  const trimmed = String(raw || "").trim();
  return trimmed.length > MAX_WORKFLOW_NAME_LENGTH
    ? `${trimmed.slice(0, MAX_WORKFLOW_NAME_LENGTH - 1)}…`
    : trimmed;
}

function normalizeWorkflowRecordName(record: { name?: string; definition?: { name?: string } }) {
  const direct = String(record.name || "").trim();
  if (direct) {
    return clampWorkflowName(direct);
  }
  const nested = String(record.definition?.name || "").trim();
  return clampWorkflowName(nested || "Untitled workflow");
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

const RUN_HISTORY_PAGE_SIZE = 30;

type AgentMetadata = {
  name: string;
  description: string;
  tags: string[];
};

function warningMapFromValidationWarnings(warnings: string[]): Record<string, string> {
  const byStep: Record<string, string[]> = {};
  for (const warning of warnings) {
    const text = String(warning || "").trim();
    if (!text) {
      continue;
    }
    if (!/missing connector|requires connectors/i.test(text)) {
      continue;
    }
    const match = text.match(/step\s+'([^']+)'/i) || text.match(/step\s+"([^"]+)"/i);
    if (!match?.[1]) {
      continue;
    }
    const stepId = String(match[1] || "").trim();
    if (!stepId) {
      continue;
    }
    const connectorsMatch = text.match(/tenant:\s*(.+?)\.?$/i);
    const connectors = connectorsMatch?.[1]
      ? connectorsMatch[1]
          .split(",")
          .map((connector) => connector.trim())
          .filter(Boolean)
      : [];
    const normalizedConnectorText = connectors
      .map((connector) =>
        connector
          .replace(/[_-]+/g, " ")
          .replace(/\s+/g, " ")
          .trim()
          .replace(/\b\w/g, (char) => char.toUpperCase()),
      )
      .join(", ");
    const formatted = normalizedConnectorText
      ? `Missing connector${connectors.length > 1 ? "s" : ""}: ${normalizedConnectorText} - configure in Settings`
      : text;
    byStep[stepId] = [...(byStep[stepId] || []), formatted];
  }
  const flattened: Record<string, string> = {};
  for (const [stepId, messages] of Object.entries(byStep)) {
    flattened[stepId] = messages.join(" ");
  }
  return flattened;
}
export function WorkflowBuilderPage() {
  const workflowId = useWorkflowStore((state) => state.workflowId);
  const workflowName = useWorkflowStore((state) => state.workflowName);
  const workflowDescription = useWorkflowStore((state) => state.workflowDescription);
  const isDirty = useWorkflowStore((state) => state.isDirty);
  const nodes = useWorkflowStore((state) => state.nodes);
  const loadDefinition = useWorkflowStore((state) => state.loadDefinition);
  const setMetadata = useWorkflowStore((state) => state.setMetadata);
  const toDefinition = useWorkflowStore((state) => state.toDefinition);
  const markSaved = useWorkflowStore((state) => state.markSaved);
  const clearRun = useWorkflowStore((state) => state.clearRun);
  const startRun = useWorkflowStore((state) => state.startRun);
  const setRunStatus = useWorkflowStore((state) => state.setRunStatus);
  const setNodeRunState = useWorkflowStore((state) => state.setNodeRunState);
  const hydrateRunOutputs = useWorkflowStore((state) => state.hydrateRunOutputs);
  const updateNodeData = useWorkflowStore((state) => state.updateNodeData);

  const view = useWorkflowViewStore((s) => s.view);
  const setView = useWorkflowViewStore((s) => s.setView);
  const quickSwitcherOpen = useWorkflowViewStore((s) => s.quickSwitcherOpen);
  const closeQuickSwitcher = useWorkflowViewStore((s) => s.closeQuickSwitcher);

  const handleSelectWorkflow = useCallback(
    (record: WorkflowRecord) => {
      loadDefinition(record.definition, {
        workflowId: record.id,
        activeTemplateId: null,
      });
      setMetadata({
        workflowId: record.id,
        workflowName: normalizeWorkflowRecordName(record),
        workflowDescription: String(record.description || record.definition?.description || ""),
      });
      markSaved();
      clearRun();
      setView("canvas");
    },
    [loadDefinition, setMetadata, markSaved, clearRun, setView],
  );

  const handleNewWorkflow = useCallback(() => {
    clearRun();
    setMetadata({
      workflowId: null,
      workflowName: "Untitled workflow",
      workflowDescription: "",
      activeTemplateId: null,
    });
    useWorkflowStore.getState().setNodes([]);
    useWorkflowStore.getState().setEdges([]);
    markSaved();
    setView("canvas");
  }, [clearRun, setMetadata, markSaved, setView]);

  const [saving, setSaving] = useState(false);
  const [showSavedDialog, setShowSavedDialog] = useState(false);
  const [savedDialogName, setSavedDialogName] = useState("");
  const [running, setRunning] = useState(false);

  const [templates, setTemplates] = useState<WorkflowTemplate[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);

  const [runHistory, setRunHistory] = useState<WorkflowRunRecord[]>([]);
  const [runHistoryLoading, setRunHistoryLoading] = useState(false);
  const [runHistoryLoadingMore, setRunHistoryLoadingMore] = useState(false);
  const [runHistoryHasMore, setRunHistoryHasMore] = useState(false);

  const [agentMetadataById, setAgentMetadataById] = useState<Record<string, AgentMetadata>>({});

  const [nlGenerating, setNlGenerating] = useState(false);
  const [nlStreamLog, setNlStreamLog] = useState("");
  const [nlError, setNlError] = useState("");
  const [validationWarningsByNodeId, setValidationWarningsByNodeId] = useState<
    Record<string, string>
  >({});

  const initialAgentHintId = useMemo(() => {
    if (typeof window === "undefined") {
      return "";
    }
    const params = new URLSearchParams(window.location.search);
    return String(params.get("agent") || "").trim();
  }, []);
  const openPickerFromRouteHint = useMemo(() => {
    if (typeof window === "undefined") {
      return false;
    }
    const params = new URLSearchParams(window.location.search);
    return params.get("open_picker") === "1" || Boolean(initialAgentHintId);
  }, [initialAgentHintId]);

  const refreshTemplates = async () => {
    setTemplatesLoading(true);
    try {
      const rows = await listWorkflowTemplates().catch(() => []);
      setTemplates(Array.isArray(rows) ? rows : []);
    } finally {
      setTemplatesLoading(false);
    }
  };

  const refreshRunHistory = async (
    targetWorkflowId?: string | null,
    options?: { append?: boolean },
  ) => {
    const recordId = String(targetWorkflowId || workflowId || "").trim();
    if (!recordId) {
      setRunHistory([]);
      setRunHistoryHasMore(false);
      return;
    }
    const append = Boolean(options?.append);
    if (append) {
      setRunHistoryLoadingMore(true);
    } else {
      setRunHistoryLoading(true);
    }
    try {
      const offset = append ? runHistory.length : 0;
      const rows = await listWorkflowRunHistory(recordId, {
        limit: RUN_HISTORY_PAGE_SIZE,
        offset,
      }).catch(() => []);
      const normalizedRows = Array.isArray(rows) ? rows : [];
      setRunHistory((previous) =>
        append ? [...previous, ...normalizedRows] : normalizedRows,
      );
      setRunHistoryHasMore(normalizedRows.length >= RUN_HISTORY_PAGE_SIZE);
    } finally {
      if (append) {
        setRunHistoryLoadingMore(false);
      } else {
        setRunHistoryLoading(false);
      }
    }
  };

  const loadInitialData = async () => {
    try {
      await refreshTemplates();
    } catch (error) {
      toast.error(`Failed to load workflow data: ${String(error)}`);
    }
  };

  const loadAgentMetadata = async () => {
    try {
      const [installedRows, catalogRows] = await Promise.all([
        listAgents().catch(() => []),
        listMarketplaceAgents({ limit: 100 }).catch(() => []),
      ]);
      const nextById: Record<string, AgentMetadata> = {};
      for (const row of catalogRows || []) {
        const agentId = String(row.agent_id || "").trim();
        if (!agentId) {
          continue;
        }
        nextById[agentId] = {
          name: String(row.name || agentId).trim(),
          description: String(row.description || "").trim(),
          tags: Array.isArray(row.tags)
            ? row.tags.map((tag) => String(tag || "").trim()).filter(Boolean)
            : [],
        };
      }
      for (const row of installedRows || []) {
        const agentId = String(row.agent_id || "").trim();
        if (!agentId) {
          continue;
        }
        nextById[agentId] = {
          name: String(row.name || nextById[agentId]?.name || agentId).trim(),
          description: String(row.description || nextById[agentId]?.description || "").trim(),
          tags: Array.isArray(row.tags)
            ? row.tags.map((tag) => String(tag || "").trim()).filter(Boolean)
            : nextById[agentId]?.tags || [],
        };
      }
      setAgentMetadataById(nextById);
    } catch {
      // Keep workflow usable even if metadata lookup fails.
    }
  };

  useEffect(() => {
    void loadInitialData();
    void loadAgentMetadata();
  }, []);

  useEffect(() => {
    if (!openPickerFromRouteHint) {
      return;
    }
    const query = new URLSearchParams(window.location.search);
    query.delete("agent");
    query.delete("open_picker");
    const nextQuery = query.toString();
    const nextPath = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ""}`;
    window.history.replaceState({}, "", nextPath);
  }, [openPickerFromRouteHint]);

  useEffect(() => {
    void refreshRunHistory(workflowId);
  }, [workflowId]);

  useEffect(() => {
    if (!nodes.length || !Object.keys(agentMetadataById).length) {
      return;
    }
    for (const node of nodes) {
      const agentId = String(node.data.agentId || "").trim();
      if (!agentId) {
        continue;
      }
      const metadata = agentMetadataById[agentId];
      if (!metadata) {
        continue;
      }
      const currentName = String(node.data.agentName || "").trim();
      const currentDescription = String(node.data.agentDescription || "").trim();
      const currentTags = Array.isArray(node.data.agentTags) ? node.data.agentTags : [];
      const needsName = !currentName || currentName === agentId;
      const needsDescription = !currentDescription;
      const needsTags = currentTags.length === 0 && metadata.tags.length > 0;
      if (!needsName && !needsDescription && !needsTags) {
        continue;
      }
      updateNodeData(
        node.id,
        {
          ...(needsName ? { agentName: metadata.name } : {}),
          ...(needsDescription ? { agentDescription: metadata.description } : {}),
          ...(needsTags ? { agentTags: metadata.tags } : {}),
          config: {
            ...(node.data.config || {}),
            ...(needsName ? { agent_name: metadata.name } : {}),
            ...(needsDescription ? { agent_description: metadata.description } : {}),
            ...(needsTags ? { agent_tags: metadata.tags } : {}),
          },
        },
        { markDirty: false },
      );
    }
  }, [agentMetadataById, nodes, updateNodeData]);

  const runValidation = async (definition: WorkflowDefinition): Promise<boolean> => {
    try {
      const result = await validateWorkflowDefinition(definition);
      if (!result.valid) {
        setValidationWarningsByNodeId({});
        const firstError = result.errors[0] || "Workflow validation failed.";
        toast.error(firstError);
        return false;
      }
      const warningMap = warningMapFromValidationWarnings(result.warnings || []);
      setValidationWarningsByNodeId(warningMap);
      if (Object.keys(warningMap).length > 0) {
        toast.warning("Workflow saved with connector warnings. Configure missing connectors in Settings.");
      }
      return true;
    } catch (error) {
      toast.error(`Validation request failed: ${String(error)}`);
      return false;
    }
  };

  const persistWorkflow = async (options?: { skipValidation?: boolean }): Promise<string | null> => {
    const definition = toDefinition();
    if (!options?.skipValidation) {
      const isValid = await runValidation(definition);
      if (!isValid) {
        return null;
      }
    }
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
      setSavedDialogName(normalizeWorkflowRecordName(response));
      setShowSavedDialog(true);
      return nextWorkflowId;
    } catch (error) {
      toast.error(`Failed to save workflow: ${String(error)}`);
      return null;
    } finally {
      setSaving(false);
    }
  };

  const runWorkflow = () => {
    const runInChat = useWorkflowViewStore.getState().runInChat;
    if (!runInChat) {
      toast.error("Chat is not available. Please try again.");
      return;
    }

    const definition = toDefinition();
    const steps = Array.isArray(definition.steps) ? definition.steps : [];
    if (steps.length === 0) {
      toast.warning("Add at least one agent to run the workflow.");
      return;
    }

    // Compose a natural-language prompt from the workflow definition
    const name = String(workflowName || "Untitled workflow").trim();
    const desc = String(workflowDescription || "").trim();
    const storeNodes = useWorkflowStore.getState().nodes;

    const lines: string[] = [];
    lines.push(`Run my workflow "${name}".`);
    if (desc) {
      lines.push(`Description: ${desc}`);
    }
    lines.push("");
    lines.push("Steps:");
    for (let i = 0; i < steps.length; i++) {
      const step = steps[i];
      const node = storeNodes.find((n) => n.id === step.step_id);
      const label = String(node?.data.label || step.description || step.agent_id || `Step ${i + 1}`).trim();
      const agentId = String(step.agent_id || "").trim();
      const stepDesc = String(step.description || "").trim();
      lines.push(`${i + 1}. ${label}${agentId ? ` (agent: ${agentId})` : ""}${stepDesc && stepDesc !== label ? ` — ${stepDesc}` : ""}`);
    }

    // Include input/output descriptions if set
    const firstNode = storeNodes[0];
    const lastNode = storeNodes[storeNodes.length - 1];
    const inputDesc = String(firstNode?.data.inputDescription || "").trim();
    const outputDesc = String(lastNode?.data.outputDescription || "").trim();
    if (inputDesc && !inputDesc.startsWith("Describe")) {
      lines.push("");
      lines.push(`Input: ${inputDesc}`);
    }
    if (outputDesc && !outputDesc.startsWith("Describe")) {
      lines.push(`Expected output: ${outputDesc}`);
    }

    const message = lines.join("\n");
    runInChat(message);
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
      setValidationWarningsByNodeId({});
      useWorkflowStore.getState().setMetadata({
        workflowId: null,
        workflowName: clampWorkflowName(streamedDefinition.name || "Generated workflow"),
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
    setValidationWarningsByNodeId({});
    useWorkflowStore.getState().setMetadata({
      workflowId: null,
      workflowName: clampWorkflowName(template.name),
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
    <div className="h-full overflow-hidden">
      {view === "gallery" ? (
        <WorkflowGallery
          onSelectWorkflow={handleSelectWorkflow}
          onNewWorkflow={handleNewWorkflow}
          templates={templates}
          templatesLoading={templatesLoading}
          onSelectTemplate={(template) => {
            applyTemplate(template);
            setView("canvas");
          }}
        />
      ) : (
        <div className="mx-auto flex h-full max-w-[1540px] min-h-0 flex-col">
          <section className="min-h-0 flex-1">
            <WorkflowCanvas
              isRunning={running}
              isDirty={isDirty}
              templates={templates}
              templatesLoading={templatesLoading}
              runHistory={runHistory}
              runHistoryLoading={runHistoryLoading}
              runHistoryHasMore={runHistoryHasMore}
              runHistoryLoadingMore={runHistoryLoadingMore}
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
              onLoadMoreRunHistory={() => {
                if (!runHistoryHasMore || runHistoryLoadingMore) {
                  return;
                }
                void refreshRunHistory(undefined, { append: true });
              }}
              onGenerateFromDescription={generateFromDescription}
              onSelectTemplate={applyTemplate}
              onLoadRunOutputs={loadRunOutputs}
              initialAgentHintId={openPickerFromRouteHint ? initialAgentHintId : null}
              validationWarningsByNodeId={validationWarningsByNodeId}
            />
          </section>
        </div>
      )}

      {/* Cmd+K quick switcher */}
      <WorkflowQuickSwitcher
        open={quickSwitcherOpen}
        onClose={closeQuickSwitcher}
        onSelectWorkflow={handleSelectWorkflow}
        onNewWorkflow={handleNewWorkflow}
      />

      {/* Saved success dialog */}
      {showSavedDialog ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm transition-opacity duration-200"
          onClick={() => setShowSavedDialog(false)}
          style={{ animation: "fadeIn 200ms ease-out" }}
        >
          <div
            className="mx-4 w-full max-w-sm rounded-2xl border border-black/[0.08] bg-white p-6 text-center shadow-[0_20px_60px_-12px_rgba(0,0,0,0.25)]"
            onClick={(e) => e.stopPropagation()}
            style={{ animation: "scaleIn 200ms ease-out" }}
          >
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-[#ecfdf5]">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#059669" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
            </div>
            <h3 className="mt-4 text-[16px] font-semibold text-[#101828]">Workflow saved</h3>
            <p className="mt-2 text-[13px] leading-relaxed text-[#667085]">
              <span className="font-medium text-[#344054]">{savedDialogName || "Your workflow"}</span>{" "}
              has been saved and is ready to run. You can run it now or continue editing.
            </p>
            <div className="mt-5 flex gap-2">
              <button
                type="button"
                onClick={() => setShowSavedDialog(false)}
                className="flex-1 rounded-xl border border-black/[0.08] px-4 py-2.5 text-[13px] font-semibold text-[#344054] transition-colors hover:bg-[#f2f4f7]"
              >
                Continue editing
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowSavedDialog(false);
                  void runWorkflow();
                }}
                className="flex-1 rounded-xl bg-[#7c3aed] px-4 py-2.5 text-[13px] font-semibold text-white transition-colors hover:bg-[#6d28d9]"
              >
                Run now
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

