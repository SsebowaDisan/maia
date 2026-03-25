import type {
  ConnectorCredentialRecord,
  ConnectorPluginManifest,
  WorkGraphPayloadResponse,
  WorkGraphReplayStateResponse,
  AgentLiveEvent,
} from "../types";

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
  agent_id?: string;
};

type AgentSummaryRecord = {
  id: string;
  agent_id: string;
  name: string;
  description?: string;
  trigger_family?: string;
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
  run_id?: string;
  tool_id: string;
  status?: string;
  action_label?: string;
  params_preview: string | Record<string, unknown>;
  preview?: Record<string, unknown> | null;
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

type AgentInstallHistoryRecord = {
  id: string;
  timestamp: number;
  user_id: string;
  marketplace_agent_id: string;
  agent_id: string;
  version: string;
  connector_mapping: Record<string, string>;
};

function isNotFoundError(error: unknown): boolean {
  const message = error instanceof Error ? String(error.message || "") : String(error || "");
  const normalized = message.trim().toLowerCase();
  return normalized.includes("404") || normalized.includes("not found");
}

function toLegacyPlaybookPayload(definition: AgentDefinitionInput) {
  return {
    name: String(definition.name || definition.agent_id || definition.id || "Untitled agent").trim(),
    prompt_template: String(definition.system_prompt || "").trim(),
    tool_ids: Array.isArray(definition.tools)
      ? definition.tools.map((toolId) => String(toolId || "").trim()).filter(Boolean)
      : [],
  };
}

function toAgentSummaryFromPlaybook(playbook: AgentPlaybookRecord): AgentSummaryRecord {
  const id = String(playbook.id || "").trim();
  return {
    id,
    agent_id: id || String(playbook.name || "").trim() || "legacy-agent",
    name: String(playbook.name || "Untitled agent"),
    version: String(playbook.version || "1"),
  };
}

function toAgentDefinitionFromPlaybook(playbook: AgentPlaybookRecord): AgentDefinitionRecord {
  const id = String(playbook.id || "").trim();
  const name = String(playbook.name || "Untitled agent");
  const tools = Array.isArray(playbook.tool_ids) ? playbook.tool_ids : [];
  const definition: AgentDefinitionInput = {
    id: id || name,
    agent_id: id || name,
    name,
    description: "",
    version: String(playbook.version || "1"),
    system_prompt: String(playbook.prompt_template || ""),
    tools,
    memory: {},
    output: {},
    trigger: null,
    gates: [],
  };
  return {
    id,
    agent_id: id || name,
    name,
    version: String(playbook.version || "1"),
    definition,
  };
}

function toAgentRunFromApiRun(row: AgentApiRunRecord): AgentRunRecord {
  const runId = String(row.run_id || row.id || "").trim() || "unknown_run";
  return {
    run_id: runId,
    agent_id: String(row.agent_id || "").trim() || "legacy-agent",
    status: String(row.status || "").trim() || "unknown",
    trigger_type: String(row.trigger_type || "").trim() || "manual",
    started_at: String(row.started_at || row.date_created || "").trim() || new Date().toISOString(),
    ended_at: row.ended_at ? String(row.ended_at) : null,
    error: row.error ? String(row.error) : null,
    result_summary: row.result_summary ? String(row.result_summary) : null,
  };
}

export {
  isNotFoundError,
  toAgentDefinitionFromPlaybook,
  toAgentRunFromApiRun,
  toAgentSummaryFromPlaybook,
  toLegacyPlaybookPayload,
};
export type {
  AgentApiRunRecord,
  AgentDefinitionInput,
  AgentDefinitionRecord,
  AgentInstallHistoryRecord,
  AgentLiveEvent,
  AgentPlaybookRecord,
  AgentRunRecord,
  AgentScheduleRecord,
  AgentSummaryRecord,
  ConnectorBindingRecord,
  ConnectorCredentialRecord,
  ConnectorPluginManifest,
  FeedbackRecord,
  GatePendingRecord,
  ImprovementSuggestionRecord,
  RegisterWebhookResponse,
  WebhookRecord,
  WorkGraphPayloadResponse,
  WorkGraphReplayStateResponse,
  WorkflowDefinitionInput,
  WorkflowRunEvent,
  WorkflowRunStreamOptions,
  WorkflowSummaryRecord,
};
