import { useEffect, useRef, type Dispatch, type SetStateAction } from "react";

import { getWorkflowRecord, listAgents } from "../../../../api/client";
import { useWorkflowViewStore } from "../../../stores/workflowViewStore";

export type ActiveAgentSelection = {
  agent_id: string;
  name: string;
};

export type ActiveWorkflowSelection = {
  workflow_id: string;
  name: string;
  description: string;
  steps: Array<{ step_id: string; agent_id: string; description?: string }>;
  missing_connectors?: string[];
};

type UseComposerPrefillEffectsParams = {
  setActiveAgent: Dispatch<SetStateAction<ActiveAgentSelection | null>>;
  setActiveWorkflow: Dispatch<SetStateAction<ActiveWorkflowSelection | null>>;
  setAgentControlsVisible: Dispatch<SetStateAction<boolean>>;
  setDeepSearchProfile: Dispatch<SetStateAction<"default" | "web_search">>;
  setMessage: Dispatch<SetStateAction<string>>;
  onAgentModeChange: (mode: string) => void;
  showActionStatus: (text: string) => void;
};

export function useComposerPrefillEffects(params: UseComposerPrefillEffectsParams) {
  const consumedAgentPrefillRef = useRef("");
  const consumedWorkflowPrefillRef = useRef("");

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const searchParams = new URLSearchParams(window.location.search);
    const requestedAgentId = String(searchParams.get("agent") || "").trim();
    if (!requestedAgentId || consumedAgentPrefillRef.current === requestedAgentId) {
      return;
    }
    consumedAgentPrefillRef.current = requestedAgentId;
    let disposed = false;
    const prefill = async () => {
      let agentName = requestedAgentId;
      let resolvedAgentId = requestedAgentId;
      try {
        const rows = await listAgents();
        const match = (rows || []).find((row) => {
          const rowAgentId = String(row.agent_id || "").trim();
          const rowId = String(row.id || "").trim();
          return rowAgentId === requestedAgentId || rowId === requestedAgentId;
        });
        const nextName = String(match?.name || "").trim();
        if (nextName) {
          agentName = nextName;
        }
        const nextAgentId = String(match?.agent_id || match?.id || "").trim();
        if (nextAgentId) {
          resolvedAgentId = nextAgentId;
        }
      } catch {
        // Keep prefill resilient even if the agents API is unavailable.
      }
      if (disposed) {
        return;
      }
      params.setActiveAgent({ agent_id: resolvedAgentId, name: agentName });
      params.setAgentControlsVisible(true);
      params.setDeepSearchProfile("default");
      params.onAgentModeChange("company_agent");
      params.setMessage((previous) => {
        const current = previous.trim();
        return current || `Run ${agentName} for me`;
      });
      params.showActionStatus(`Prepared prompt for ${agentName}.`);
      searchParams.delete("agent");
      const nextQuery = searchParams.toString();
      const nextPath = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ""}`;
      window.history.replaceState({}, "", nextPath);
    };
    void prefill();
    return () => {
      disposed = true;
    };
  }, [params]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const searchParams = new URLSearchParams(window.location.search);
    const requestedWorkflowId = String(searchParams.get("workflow") || "").trim();
    if (!requestedWorkflowId || consumedWorkflowPrefillRef.current === requestedWorkflowId) {
      return;
    }
    consumedWorkflowPrefillRef.current = requestedWorkflowId;
    let disposed = false;
    const prefill = async () => {
      let workflowName = "Workflow";
      let workflowDescription = "";
      let workflowSteps: Array<{ step_id: string; agent_id: string; description?: string }> = [];
      try {
        const workflow = await getWorkflowRecord(requestedWorkflowId);
        const definition = (workflow?.definition || {}) as Record<string, unknown>;
        workflowName = String(workflow?.name || definition.name || "Workflow").trim() || "Workflow";
        workflowDescription = String(workflow?.description || definition.description || "").trim();
        const steps = Array.isArray((definition as { steps?: unknown[] }).steps)
          ? ((definition as { steps?: Array<Record<string, unknown>> }).steps || [])
          : [];
        workflowSteps = steps.map((step) => ({
          step_id: String(step.step_id || "").trim(),
          agent_id: String(step.agent_id || "").trim(),
          description: String(step.description || "").trim() || undefined,
        }));
      } catch {
        // Keep resilient if workflow API is unavailable.
      }
      if (disposed) {
        return;
      }
      const missingConnectorsRaw = String(searchParams.get("missing_connectors") || "").trim();
      const missingConnectors = missingConnectorsRaw
        ? missingConnectorsRaw
            .split(",")
            .map((value) => value.trim())
            .filter(Boolean)
        : [];
      params.setActiveWorkflow({
        workflow_id: requestedWorkflowId,
        name: workflowName,
        description: workflowDescription,
        steps: workflowSteps,
        missing_connectors: missingConnectors,
      });
      params.setMessage((previous) => {
        const current = previous.trim();
        return current || `Run workflow \"${workflowName}\" with my latest context`;
      });
      params.showActionStatus(`Workflow \"${workflowName}\" is staged.`);
      searchParams.delete("workflow");
      searchParams.delete("missing_connectors");
      const nextQuery = searchParams.toString();
      const nextPath = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ""}`;
      window.history.replaceState({}, "", nextPath);
    };
    void prefill();
    return () => {
      disposed = true;
    };
  }, [params]);

  useEffect(() => {
    let previousStaged = "";
    return useWorkflowViewStore.subscribe((state) => {
      const staged = state.stagedMessage;
      if (staged && staged !== previousStaged) {
        previousStaged = staged;
        params.setMessage(staged);
        useWorkflowViewStore.setState({ stagedMessage: "" });
      }
    });
  }, [params]);
}
