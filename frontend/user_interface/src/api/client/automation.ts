import { fetchApi, request } from "./core";

type CollaborationEntry = {
  run_id?: string;
  from_agent: string;
  to_agent: string;
  message: string;
  entry_type: string;
  timestamp?: number;
  metadata?: Record<string, unknown>;
};

type AgentMemoryEntry = {
  id: string;
  agent_id?: string;
  content: string;
  category?: string;
  tags?: string[];
  source?: string;
  created_at?: string | number | null;
  recorded_at?: number;
  metadata?: Record<string, unknown>;
};

type TriggerEventTypeRecord = {
  event_type: string;
  label: string;
  description?: string;
};

type TriggerRecord = {
  trigger_id: string;
  agent_id: string;
  event_type: string;
  source_connector_id?: string;
  enabled?: boolean;
  description?: string;
  created_at?: number | string | null;
  metadata?: Record<string, unknown>;
};

type CreateTriggerRequest = {
  agent_id: string;
  event_type: string;
  source_connector_id?: string;
  filter_expression?: string;
  description?: string;
};

type TriggerTestResponse = {
  event_type: string;
  matched_agents: string[];
  count: number;
  matched_triggers?: TriggerRecord[];
};

type DashboardWidgetRecord = {
  id: string;
  title: string;
  widget_type: string;
  source_agent_id?: string;
  source_workflow_id?: string;
  source_run_id?: string;
  content?: string;
  refresh_interval_minutes?: number;
  position?: number;
  created_at?: number;
  last_refreshed_at?: number;
};

type CreateDashboardWidgetRequest = {
  title: string;
  widget_type?: string;
  source_agent_id?: string;
  source_workflow_id?: string;
  source_run_id?: string;
  content?: string;
  refresh_interval_minutes?: number;
  position?: number;
};

type UpdateDashboardWidgetRequest = {
  title?: string;
  position?: number;
  refresh_interval_minutes?: number;
};

type SlackIntegrationStatus = {
  configured: boolean;
  bot_token_set: boolean;
  commands_url: string;
};

type WorkflowTemplatePreview = {
  template_id: string;
  name?: string;
  sample_output: string;
  step_count?: number;
  generated_at?: number;
};

function isNotFoundError(error: unknown): boolean {
  const text = error instanceof Error ? error.message : String(error || "");
  const normalized = text.trim().toLowerCase();
  return normalized.includes("404") || normalized.includes("not found");
}

function listRunCollaboration(runId: string) {
  return request<CollaborationEntry[]>(
    `/api/agent/runs/${encodeURIComponent(runId)}/collaboration`,
  ).catch((error) => {
    if (isNotFoundError(error)) {
      return [] as CollaborationEntry[];
    }
    throw error;
  });
}

function listAgentMemory(options?: { agentId?: string }) {
  const agentId = String(options?.agentId || "").trim();
  const path = agentId
    ? `/api/agent/memory/${encodeURIComponent(agentId)}`
    : "/api/agent/memory";
  return request<AgentMemoryEntry[]>(path).catch((error) => {
    if (isNotFoundError(error)) {
      return [] as AgentMemoryEntry[];
    }
    throw error;
  });
}

async function deleteAgentMemory(memoryId: string) {
  const response = await fetchApi(`/api/agent/memory/${encodeURIComponent(memoryId)}`, {
    method: "DELETE",
  });
  if (response.ok || response.status === 204) {
    return;
  }
  const detail = (await response.text()).trim();
  throw new Error(detail || `Failed to delete memory (${response.status})`);
}

function clearAgentMemory() {
  return request<{ status: string; count?: number }>("/api/agent/memory/clear", {
    method: "POST",
  });
}

function listTriggerEventTypes() {
  return request<TriggerEventTypeRecord[]>("/api/triggers/events").catch((error) => {
    if (isNotFoundError(error)) {
      return [] as TriggerEventTypeRecord[];
    }
    throw error;
  });
}

function listAgentTriggers() {
  return request<TriggerRecord[]>("/api/triggers").catch((error) => {
    if (isNotFoundError(error)) {
      return [] as TriggerRecord[];
    }
    throw error;
  });
}

function createAgentTrigger(body: CreateTriggerRequest) {
  return request<TriggerRecord>("/api/triggers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      agent_id: body.agent_id,
      event_type: body.event_type,
      source_connector_id: body.source_connector_id || "",
      filter_expression: body.filter_expression || "",
      description: body.description || "",
    }),
  });
}

async function deleteAgentTrigger(triggerId: string) {
  const response = await fetchApi(`/api/triggers/${encodeURIComponent(triggerId)}`, {
    method: "DELETE",
  });
  if (response.ok || response.status === 204) {
    return;
  }
  const detail = (await response.text()).trim();
  throw new Error(detail || `Failed to delete trigger (${response.status})`);
}

function testAgentTrigger(eventType: string, payload?: Record<string, unknown>) {
  return request<TriggerTestResponse>("/api/triggers/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      event_type: eventType,
      payload: payload || {},
    }),
  });
}

function listDashboardWidgets() {
  return request<DashboardWidgetRecord[]>("/api/dashboard").catch((error) => {
    if (isNotFoundError(error)) {
      return [] as DashboardWidgetRecord[];
    }
    throw error;
  });
}

function createDashboardWidget(body: CreateDashboardWidgetRequest) {
  return request<DashboardWidgetRecord>("/api/dashboard", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: body.title,
      widget_type: body.widget_type || "agent_output",
      source_agent_id: body.source_agent_id || "",
      source_workflow_id: body.source_workflow_id || "",
      source_run_id: body.source_run_id || "",
      content: body.content || "",
      refresh_interval_minutes: Number(body.refresh_interval_minutes || 0),
      position: Number(body.position || 0),
    }),
  });
}

function updateDashboardWidget(widgetId: string, body: UpdateDashboardWidgetRequest) {
  return request<DashboardWidgetRecord>(`/api/dashboard/${encodeURIComponent(widgetId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function deleteDashboardWidget(widgetId: string) {
  const response = await fetchApi(`/api/dashboard/${encodeURIComponent(widgetId)}`, {
    method: "DELETE",
  });
  if (response.ok || response.status === 204) {
    return;
  }
  const detail = (await response.text()).trim();
  throw new Error(detail || `Failed to delete widget (${response.status})`);
}

function refreshDashboardWidget(widgetId: string) {
  return request<DashboardWidgetRecord>(
    `/api/dashboard/${encodeURIComponent(widgetId)}/refresh`,
    { method: "POST" },
  );
}

function getSlackIntegrationStatus() {
  return request<SlackIntegrationStatus>("/api/integrations/slack/status").catch((error) => {
    if (isNotFoundError(error)) {
      return {
        configured: false,
        bot_token_set: false,
        commands_url: "/api/integrations/slack/commands",
      } as SlackIntegrationStatus;
    }
    throw error;
  });
}

function getWorkflowTemplatePreview(templateId: string) {
  return request<WorkflowTemplatePreview>(
    `/api/workflows/templates/${encodeURIComponent(templateId)}/preview`,
  );
}

export {
  clearAgentMemory,
  createAgentTrigger,
  createDashboardWidget,
  deleteAgentMemory,
  deleteAgentTrigger,
  deleteDashboardWidget,
  getSlackIntegrationStatus,
  getWorkflowTemplatePreview,
  listAgentMemory,
  listAgentTriggers,
  listDashboardWidgets,
  listRunCollaboration,
  listTriggerEventTypes,
  refreshDashboardWidget,
  testAgentTrigger,
  updateDashboardWidget,
};

export type {
  AgentMemoryEntry,
  CollaborationEntry,
  CreateDashboardWidgetRequest,
  CreateTriggerRequest,
  DashboardWidgetRecord,
  SlackIntegrationStatus,
  TriggerEventTypeRecord,
  TriggerRecord,
  TriggerTestResponse,
  UpdateDashboardWidgetRequest,
  WorkflowTemplatePreview,
};
