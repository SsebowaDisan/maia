import { API_BASE, fetchApi, request, withUserIdQuery } from "./core";
import type {
  AgentLiveEvent,
  ConnectorCredentialRecord,
  ConnectorPluginManifest,
  WorkGraphPayloadResponse,
  WorkGraphReplayStateResponse,
} from "./types";

type AgentDefinitionInput = {
  id: string;
  name: string;
  description?: string;
  version?: string;
  author?: string;
  tags?: string[];
  system_prompt?: string;
  tools?: string[];
  max_delegation_depth?: number;
  allowed_sub_agent_ids?: string[];
  memory?: Record<string, unknown>;
  output?: Record<string, unknown>;
  trigger?: Record<string, unknown> | null;
  gates?: Array<Record<string, unknown>>;
  is_public?: boolean;
  pricing_model?: string;
  price_per_use_cents?: number;
};

type AgentSummaryRecord = {
  id: string;
  agent_id: string;
  name: string;
  version: string;
};

type AgentDefinitionRecord = {
  id: string;
  agent_id: string;
  name: string;
  version: string;
  definition: AgentDefinitionInput;
};

type AgentRunRecord = {
  run_id: string;
  agent_id: string;
  status: string;
  trigger_type: string;
  started_at: string;
  ended_at?: string | null;
  error?: string | null;
  result_summary?: string | null;
};

type AgentApiRunRecord = {
  id?: string;
  run_id?: string;
  agent_id?: string;
  status?: string;
  trigger_type?: string;
  started_at?: string;
  ended_at?: string | null;
  date_created?: string;
  date_updated?: string;
  error?: string | null;
  result_summary?: string | null;
  llm_cost_usd?: number | null;
  cost_usd?: number | null;
  duration_ms?: number | null;
  [key: string]: unknown;
};

type AgentPlaybookRecord = {
  id: string;
  name: string;
  prompt_template: string;
  tool_ids: string[];
  owner_id?: string;
  version?: number;
  date_created?: string;
  date_updated?: string;
};

type AgentScheduleRecord = {
  id: string;
  user_id: string;
  name: string;
  prompt: string;
  frequency: "daily" | "weekly" | "monthly" | string;
  enabled: boolean;
  next_run_at?: string | null;
  last_run_at?: string | null;
  outputs?: string[];
  channels?: string[];
  date_created?: string;
  date_updated?: string;
};

type ConnectorBindingRecord = {
  connector_id: string;
  allowed_agent_ids: string[];
  enabled_tool_ids: string[];
  is_active?: boolean;
  last_used_at?: string | null;
};

type GatePendingRecord = {
  gate_id: string;
  run_id: string;
  tool_id: string;
  status: string;
  params_preview: string;
  cost_estimate?: number | null;
};

type WorkflowDefinitionInput = {
  workflow_id: string;
  name: string;
  steps: Array<{
    step_id: string;
    agent_id: string;
    input_mapping?: Record<string, string>;
    output_key: string;
  }>;
  edges: Array<{
    from_step: string;
    to_step: string;
    condition?: string;
  }>;
};

type WorkflowSummaryRecord = {
  workflow_id: string;
  name: string;
  step_count: number;
  edge_count: number;
  date_created?: string | null;
  date_updated?: string | null;
};

type WorkflowRunEvent = {
  event_type: string;
  workflow_id?: string;
  step_id?: string;
  agent_id?: string;
  output_key?: string;
  result_preview?: string;
  error?: string;
  detail?: string;
  [key: string]: unknown;
};

type WorkflowRunStreamOptions = {
  onEvent?: (event: WorkflowRunEvent) => void;
  onDone?: () => void;
  onError?: (error: Error) => void;
};

type WebhookRecord = {
  id: string;
  connector_id: string;
  event_types: string[];
  external_hook_id?: string | null;
  receiver_url?: string;
  active: boolean;
  created_at?: number;
};

type RegisterWebhookResponse = {
  id: string;
  connector_id: string;
  event_types_json?: string;
  active?: boolean;
};

type FeedbackRecord = {
  id: string;
  tenant_id: string;
  agent_id: string;
  run_id: string;
  original_output: string;
  corrected_output: string;
  feedback_type: string;
  created_at: number;
};

type ImprovementSuggestionRecord = {
  suggested_prompt: string;
  reasoning: string;
  feedback_count: number;
  agent_id: string;
};

function getAgentEventSnapshotUrl(runId: string, eventId: string): string {
  return `${API_BASE}/api/agent/runs/${encodeURIComponent(runId)}/events/${encodeURIComponent(eventId)}/snapshot`;
}

function getAgentRunEvents(runId: string) {
  return request<unknown[]>(
    `/api/agent/runs/${encodeURIComponent(runId)}/events`,
  );
}

function getAgentRunWorkGraph(
  runId: string,
  filters?: {
    agent_role?: string;
    status?: string;
    event_index_min?: number;
    event_index_max?: number;
  },
) {
  const query = new URLSearchParams();
  if (filters?.agent_role) {
    query.set("agent_role", filters.agent_role);
  }
  if (filters?.status) {
    query.set("status", filters.status);
  }
  if (typeof filters?.event_index_min === "number") {
    query.set("event_index_min", String(filters.event_index_min));
  }
  if (typeof filters?.event_index_max === "number") {
    query.set("event_index_max", String(filters.event_index_max));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<WorkGraphPayloadResponse>(`/api/agent/runs/${encodeURIComponent(runId)}/work-graph${suffix}`);
}

function getAgentRunWorkGraphReplayState(
  runId: string,
  filters?: {
    agent_role?: string;
    status?: string;
    event_index_min?: number;
    event_index_max?: number;
  },
) {
  const query = new URLSearchParams();
  if (filters?.agent_role) {
    query.set("agent_role", filters.agent_role);
  }
  if (filters?.status) {
    query.set("status", filters.status);
  }
  if (typeof filters?.event_index_min === "number") {
    query.set("event_index_min", String(filters.event_index_min));
  }
  if (typeof filters?.event_index_max === "number") {
    query.set("event_index_max", String(filters.event_index_max));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<WorkGraphReplayStateResponse>(
    `/api/agent/runs/${encodeURIComponent(runId)}/work-graph/replay-state${suffix}`,
  );
}

function exportAgentRunEvents(runId: string) {
  return request<{
    run_id: string;
    run_started: Record<string, unknown>;
    run_completed: Record<string, unknown>;
    total_rows: number;
    total_events: number;
    events: Array<Record<string, unknown>>;
  }>(`/api/agent/runs/${encodeURIComponent(runId)}/events/export`);
}

function listAgentTools() {
  return request<Array<Record<string, unknown>>>("/api/agent/tools");
}

function listConnectorHealth() {
  return request<Array<Record<string, unknown>>>("/api/agent/connectors/health");
}

function listConnectorPlugins() {
  return request<ConnectorPluginManifest[]>("/api/agent/connectors/plugins");
}

function getConnectorPlugin(connectorId: string) {
  return request<ConnectorPluginManifest>(`/api/agent/connectors/plugins/${encodeURIComponent(connectorId)}`);
}

function listConnectorCredentials() {
  return request<ConnectorCredentialRecord[]>("/api/agent/connectors/credentials");
}

function upsertConnectorCredentials(connectorId: string, values: Record<string, string>) {
  return request<ConnectorCredentialRecord>("/api/agent/connectors/credentials", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      connector_id: connectorId,
      values,
    }),
  });
}

function deleteConnectorCredentials(connectorId: string) {
  return request<{ status: string; connector_id: string }>(
    `/api/agent/connectors/credentials/${encodeURIComponent(connectorId)}`,
    {
      method: "DELETE",
    },
  );
}

function createAgent(definition: AgentDefinitionInput) {
  return request<{
    id: string;
    agent_id: string;
    version: string;
  }>("/api/agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(definition),
  });
}

function listAgents() {
  return request<AgentSummaryRecord[]>("/api/agents");
}

function getAgent(agentId: string, options?: { version?: string }) {
  const query = new URLSearchParams();
  if (options?.version) {
    query.set("version", options.version);
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<AgentDefinitionRecord>(`/api/agents/${encodeURIComponent(agentId)}${suffix}`);
}

function updateAgent(agentId: string, definition: AgentDefinitionInput) {
  return request<{
    id: string;
    agent_id: string;
    version: string;
  }>(`/api/agents/${encodeURIComponent(agentId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(definition),
  });
}

async function deleteAgent(agentId: string) {
  const response = await fetchApi(`/api/agents/${encodeURIComponent(agentId)}`, {
    method: "DELETE",
  });
  if (!response.ok && response.status !== 204) {
    const detail = (await response.text()).trim();
    throw new Error(detail || `Delete failed: ${response.status}`);
  }
}

function listAgentRuns(agentId: string, options?: { limit?: number }) {
  const query = new URLSearchParams();
  if (typeof options?.limit === "number") {
    query.set("limit", String(options.limit));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<AgentRunRecord[]>(`/api/agents/${encodeURIComponent(agentId)}/runs${suffix}`);
}

function listAgentApiRuns(options?: { limit?: number }) {
  const query = new URLSearchParams();
  if (typeof options?.limit === "number") {
    query.set("limit", String(options.limit));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<AgentApiRunRecord[]>(`/api/agent/runs${suffix}`);
}

function listPlaybooks(options?: { limit?: number }) {
  const query = new URLSearchParams();
  if (typeof options?.limit === "number") {
    query.set("limit", String(options.limit));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<AgentPlaybookRecord[]>(`/api/agent/playbooks${suffix}`);
}

function listSchedules() {
  return request<AgentScheduleRecord[]>("/api/agent/schedules");
}

function getConnectorBinding(connectorId: string) {
  return request<ConnectorBindingRecord>(`/api/connectors/${encodeURIComponent(connectorId)}/bindings`);
}

function patchConnectorBinding(
  connectorId: string,
  payload: { allowed_agent_ids?: string[]; enabled_tool_ids?: string[] },
) {
  return request<{ status: string; connector_id: string }>(
    `/api/connectors/${encodeURIComponent(connectorId)}/bindings`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}

function getAgentRun(runId: string) {
  return request<AgentRunRecord>(`/api/agents/runs/${encodeURIComponent(runId)}`);
}

function listPendingGates(runId: string) {
  return request<GatePendingRecord[]>(`/api/agents/runs/${encodeURIComponent(runId)}/gates`);
}

function approveAgentRunGate(runId: string, gateId: string) {
  return request<{ status: string; run_id: string; gate_id: string }>(
    `/api/agents/runs/${encodeURIComponent(runId)}/gates/${encodeURIComponent(gateId)}/approve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    },
  );
}

function rejectAgentRunGate(runId: string, gateId: string) {
  return request<{ status: string; run_id: string; gate_id: string }>(
    `/api/agents/runs/${encodeURIComponent(runId)}/gates/${encodeURIComponent(gateId)}/reject`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    },
  );
}

function listWebhooks() {
  return request<WebhookRecord[]>("/api/connectors/webhooks");
}

function registerWebhook(connectorId: string, eventTypes: string[]) {
  return request<RegisterWebhookResponse>(
    `/api/connectors/${encodeURIComponent(connectorId)}/webhooks`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_types: eventTypes }),
    },
  );
}

async function deregisterWebhook(webhookId: string) {
  const response = await fetchApi(`/api/connectors/webhooks/${encodeURIComponent(webhookId)}`, {
    method: "DELETE",
  });
  if (!response.ok && response.status !== 204) {
    const detail = (await response.text()).trim();
    throw new Error(detail || `Delete failed: ${response.status}`);
  }
}

function createWorkflow(definition: WorkflowDefinitionInput) {
  return request<WorkflowSummaryRecord>("/api/agents/workflows", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(definition),
  });
}

function listWorkflows() {
  return request<WorkflowSummaryRecord[]>("/api/agents/workflows");
}

function updateWorkflow(workflowId: string, definition: WorkflowDefinitionInput) {
  return request<WorkflowSummaryRecord>(`/api/agents/workflows/${encodeURIComponent(workflowId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(definition),
  });
}

function parseWorkflowSseBlock(block: string): WorkflowRunEvent | null {
  const lines = block
    .split("\n")
    .map((line) => line.trimEnd())
    .filter(Boolean);
  if (!lines.length) {
    return null;
  }
  const dataLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  const dataText = dataLines.join("\n");
  if (!dataText || dataText === "[DONE]") {
    return { event_type: "done" };
  }
  try {
    return JSON.parse(dataText) as WorkflowRunEvent;
  } catch {
    return { event_type: "message", detail: dataText };
  }
}

async function runWorkflow(workflowId: string, options?: WorkflowRunStreamOptions) {
  const response = await fetchApi(`/api/agents/workflows/${encodeURIComponent(workflowId)}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  if (!response.ok) {
    const detail = (await response.text()).trim();
    throw new Error(detail || `Workflow run failed: ${response.status}`);
  }
  if (!response.body) {
    throw new Error("No workflow stream body returned by backend.");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const read = await reader.read();
      if (read.done) {
        break;
      }
      buffer += decoder.decode(read.value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";
      for (const block of blocks) {
        const parsed = parseWorkflowSseBlock(block);
        if (!parsed) {
          continue;
        }
        if (parsed.event_type === "done") {
          options?.onDone?.();
          continue;
        }
        options?.onEvent?.(parsed);
      }
    }
    if (buffer.trim()) {
      const parsed = parseWorkflowSseBlock(buffer);
      if (parsed?.event_type === "done") {
        options?.onDone?.();
      } else if (parsed) {
        options?.onEvent?.(parsed);
      }
    }
  } catch (error) {
    options?.onError?.(error instanceof Error ? error : new Error(String(error)));
    throw error;
  }
}

function recordFeedback(
  agentId: string,
  runId: string,
  originalOutput: string,
  correctedOutput: string,
  feedbackType: "correction" | "approval" | "rejection" = "correction",
) {
  return request<FeedbackRecord>(`/api/agents/${encodeURIComponent(agentId)}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      run_id: runId,
      original_output: originalOutput,
      corrected_output: correctedOutput,
      feedback_type: feedbackType,
    }),
  });
}

function getImprovementSuggestion(agentId: string) {
  return request<ImprovementSuggestionRecord>(
    `/api/agents/${encodeURIComponent(agentId)}/improvement`,
  );
}

function subscribeAgentEvents(options?: {
  runId?: string;
  replay?: number;
  onReady?: (payload: Record<string, unknown>) => void;
  onEvent?: (event: AgentLiveEvent) => void;
  onError?: () => void;
}) {
  const query = new URLSearchParams();
  if (options?.runId) {
    query.set("run_id", options.runId);
  }
  if (typeof options?.replay === "number") {
    query.set("replay", String(options.replay));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  const eventSource = new EventSource(`${API_BASE}${withUserIdQuery(`/api/agent/events${suffix}`)}`);

  eventSource.addEventListener("ready", (event) => {
    try {
      const parsed = JSON.parse((event as MessageEvent<string>).data || "{}");
      options?.onReady?.(parsed);
    } catch {
      options?.onReady?.({});
    }
  });
  eventSource.addEventListener("event", (event) => {
    try {
      const parsed = JSON.parse((event as MessageEvent<string>).data || "{}");
      options?.onEvent?.(parsed as AgentLiveEvent);
    } catch {
      // Ignore malformed event chunks.
    }
  });
  eventSource.onerror = () => {
    options?.onError?.();
  };

  return () => {
    eventSource.close();
  };
}

export {
  createAgent,
  deleteAgent,
  approveAgentRunGate,
  deleteConnectorCredentials,
  exportAgentRunEvents,
  getAgent,
  getAgentRun,
  getAgentEventSnapshotUrl,
  getAgentRunEvents,
  getAgentRunWorkGraph,
  getAgentRunWorkGraphReplayState,
  getConnectorBinding,
  getConnectorPlugin,
  listAgentTools,
  listAgentApiRuns,
  listAgentRuns,
  listAgents,
  listPlaybooks,
  listSchedules,
  listConnectorCredentials,
  listPendingGates,
  listWebhooks,
  listWorkflows,
  listConnectorHealth,
  listConnectorPlugins,
  patchConnectorBinding,
  createWorkflow,
  deregisterWebhook,
  getImprovementSuggestion,
  recordFeedback,
  registerWebhook,
  rejectAgentRunGate,
  runWorkflow,
  subscribeAgentEvents,
  updateWorkflow,
  updateAgent,
  upsertConnectorCredentials,
};

export type {
  AgentDefinitionInput,
  AgentApiRunRecord,
  AgentDefinitionRecord,
  AgentPlaybookRecord,
  AgentRunRecord,
  AgentScheduleRecord,
  AgentSummaryRecord,
  ConnectorBindingRecord,
  FeedbackRecord,
  GatePendingRecord,
  ImprovementSuggestionRecord,
  RegisterWebhookResponse,
  WebhookRecord,
  WorkflowDefinitionInput,
  WorkflowRunEvent,
  WorkflowSummaryRecord,
};
