import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { parse as parseYaml, stringify as stringifyYaml } from "yaml";

import {
  createAgent,
  deleteAgent,
  getAgent,
  listAgents,
  listConnectorHealth,
  listConnectorPlugins,
  updateAgent,
  type AgentDefinitionInput,
  type AgentSummaryRecord,
} from "../../api/client";
import { GateConfig, type ToolGate } from "../components/agentBuilder/GateConfig";
import { SystemPromptEditor } from "../components/agentBuilder/SystemPromptEditor";
import { ToolSelector } from "../components/agentBuilder/ToolSelector";
import { AgentMemoryTab } from "../components/agentActivityPanel/AgentMemoryTab";
import { SimulationPanel } from "../components/agentActivityPanel/SimulationPanel";
import type { ConnectorSummary } from "../types/connectorSummary";

type BuilderMode = "visual" | "yaml" | "memory" | "test_run";

type TriggerDraft = {
  type: "conversational" | "schedule" | "event";
  value: string;
};

type AgentDraft = {
  agent_id: string;
  version: string;
  name: string;
  description: string;
  author: string;
  tags: string[];
  system_prompt: string;
  tools: string[];
  memory: {
    working_enabled: boolean;
    episodic_enabled: boolean;
    semantic_enabled: boolean;
  };
  trigger: TriggerDraft;
  gates: ToolGate[];
  output_block_types: string[];
  max_delegation_depth: number;
  allowed_sub_agent_ids: string[];
  pricing_model: "free" | "per_use" | "subscription";
  price_per_use_cents: number;
  is_public: boolean;
  cost_gate_usd: number;
};

const OUTPUT_BLOCK_OPTIONS = ["markdown", "code", "math", "widget", "table", "image", "citation", "chart"];

function defaultDraft(): AgentDraft {
  return {
    agent_id: "new-agent",
    version: "1.0.0",
    name: "New Agent",
    description: "Describe the agent purpose.",
    author: "",
    tags: [],
    system_prompt: "You are an assistant focused on high-signal operational output.",
    tools: [],
    memory: {
      working_enabled: true,
      episodic_enabled: false,
      semantic_enabled: true,
    },
    trigger: { type: "conversational", value: "" },
    gates: [],
    output_block_types: ["markdown", "table"],
    max_delegation_depth: 0,
    allowed_sub_agent_ids: [],
    pricing_model: "free",
    price_per_use_cents: 0,
    is_public: false,
    cost_gate_usd: 0.5,
  };
}

function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function prettyYaml(value: unknown): string {
  try {
    return stringifyYaml(value, {
      lineWidth: 120,
      indentSeq: false,
      defaultStringType: "PLAIN",
    }).trim();
  } catch {
    return String(value || "");
  }
}

function slugifyAgentId(value: string): string {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9\s_-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-{2,}/g, "-")
    .replace(/^[-_]+|[-_]+$/g, "")
    .slice(0, 64);
}

function normalizeGateFallback(value: ToolGate["timeoutFallback"]): "skip" | "abort" | "auto_approve" {
  if (value === "cancel") {
    return "abort";
  }
  if (value === "proceed") {
    return "auto_approve";
  }
  return "skip";
}

function denormalizeGateFallback(value: string): ToolGate["timeoutFallback"] {
  if (value === "abort") {
    return "cancel";
  }
  if (value === "auto_approve") {
    return "proceed";
  }
  return "skip";
}

function buildDefinitionFromDraft(draft: AgentDraft): AgentDefinitionInput {
  const trigger: Record<string, unknown> =
    draft.trigger.type === "schedule"
      ? {
          family: "scheduled",
          cron_expression: draft.trigger.value.trim() || "0 9 * * 1",
          timezone: "UTC",
          timeout_seconds: 3600,
          payload: {},
        }
      : draft.trigger.type === "event"
        ? {
            family: "on_event",
            event_type: draft.trigger.value.trim() || "connector.event",
            source_connector_id: "slack",
            timeout_seconds: 300,
          }
        : {
            family: "conversational",
            keywords: draft.trigger.value.trim() ? [draft.trigger.value.trim()] : [],
            patterns: [],
            is_default_fallback: false,
            min_router_confidence: 0,
          };

  const gates = draft.gates
    .filter((gate) => gate.requireApproval)
    .map((gate) => ({
      name: `${gate.toolId} approval gate`,
      tool_ids: [gate.toolId],
      approval_prompt: `Please review ${gate.toolId} action before execution.`,
      timeout_seconds: Math.max(10, Math.round(gate.timeoutMinutes * 60)),
      fallback_action: normalizeGateFallback(gate.timeoutFallback),
      remember_approval_in_session: false,
      notify_channels: [],
    }));

  const agentId = slugifyAgentId(draft.agent_id || draft.name || "new-agent") || "new-agent";
  return {
    id: agentId,
    name: String(draft.name || agentId).trim(),
    description: String(draft.description || "").trim(),
    version: String(draft.version || "1.0.0").trim(),
    author: String(draft.author || "").trim(),
    tags: draft.tags.filter(Boolean),
    system_prompt: draft.system_prompt,
    tools: draft.tools,
    max_delegation_depth: draft.max_delegation_depth,
    allowed_sub_agent_ids: draft.allowed_sub_agent_ids.filter(Boolean),
    memory: {
      working: {
        enabled: draft.memory.working_enabled,
        backend: "redis",
        ttl_seconds: 3600,
        max_tokens: 8192,
      },
      episodic: {
        enabled: draft.memory.episodic_enabled,
        backend: "vector",
        max_episodes: 500,
        similarity_threshold: 0.75,
        top_k_retrieval: 5,
      },
      semantic: {
        enabled: draft.memory.semantic_enabled,
        index_ids: [],
        top_k_retrieval: 10,
      },
    },
    output: {
      format: "chat",
      allowed_block_types: draft.output_block_types,
      stream: true,
      include_next_steps: true,
      include_citations: true,
    },
    trigger,
    gates,
    is_public: draft.is_public,
    pricing_model: draft.pricing_model,
    price_per_use_cents: Math.max(0, Math.round(draft.price_per_use_cents)),
  };
}

function hydrateDraftFromDefinition(definition: AgentDefinitionInput): AgentDraft {
  const triggerRaw = (definition.trigger || {}) as Record<string, unknown>;
  const triggerFamily = String(triggerRaw.family || "conversational").toLowerCase();
  const trigger: TriggerDraft =
    triggerFamily === "scheduled"
      ? {
          type: "schedule",
          value: String(triggerRaw.cron_expression || ""),
        }
      : triggerFamily === "on_event"
        ? {
            type: "event",
            value: String(triggerRaw.event_type || ""),
          }
        : {
            type: "conversational",
            value: Array.isArray(triggerRaw.keywords) ? String(triggerRaw.keywords[0] || "") : "",
          };

  const memory = (definition.memory || {}) as Record<string, unknown>;
  const working = (memory.working || {}) as Record<string, unknown>;
  const episodic = (memory.episodic || {}) as Record<string, unknown>;
  const semantic = (memory.semantic || {}) as Record<string, unknown>;

  const output = (definition.output || {}) as Record<string, unknown>;
  const allowedBlocks = Array.isArray(output.allowed_block_types)
    ? output.allowed_block_types.map((value) => String(value))
    : [];

  const gates = Array.isArray(definition.gates)
    ? definition.gates.flatMap((gate) => {
        const row = gate as Record<string, unknown>;
        const toolIds = Array.isArray(row.tool_ids) ? row.tool_ids.map((entry) => String(entry)) : [];
        if (!toolIds.length) {
          return [];
        }
        return toolIds.map((toolId) => ({
          toolId,
          requireApproval: true,
          timeoutMinutes: Math.max(1, Math.round(Number(row.timeout_seconds || 3600) / 60)),
          timeoutFallback: denormalizeGateFallback(String(row.fallback_action || "skip")),
        }));
      })
    : [];

  return {
    agent_id: String(definition.id || "new-agent"),
    version: String(definition.version || "1.0.0"),
    name: String(definition.name || "New Agent"),
    description: String(definition.description || ""),
    author: String(definition.author || ""),
    tags: Array.isArray(definition.tags) ? definition.tags.map((entry) => String(entry)) : [],
    system_prompt: String(definition.system_prompt || ""),
    tools: Array.isArray(definition.tools) ? definition.tools.map((entry) => String(entry)) : [],
    memory: {
      working_enabled: Boolean(working.enabled ?? true),
      episodic_enabled: Boolean(episodic.enabled ?? false),
      semantic_enabled: Boolean(semantic.enabled ?? true),
    },
    trigger,
    gates,
    output_block_types: allowedBlocks.length ? allowedBlocks : ["markdown", "table"],
    max_delegation_depth: Number(definition.max_delegation_depth || 0),
    allowed_sub_agent_ids: Array.isArray(definition.allowed_sub_agent_ids)
      ? definition.allowed_sub_agent_ids.map((entry) => String(entry))
      : [],
    pricing_model:
      definition.pricing_model === "per_use" || definition.pricing_model === "subscription"
        ? definition.pricing_model
        : "free",
    price_per_use_cents: Number(definition.price_per_use_cents || 0),
    is_public: Boolean(definition.is_public),
    cost_gate_usd: 0.5,
  };
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function coerceDraftFromEditor(value: unknown): AgentDraft {
  const row = asRecord(value);
  if (!row) {
    throw new Error("Editor content must resolve to an object.");
  }
  if ("id" in row && !("agent_id" in row)) {
    return hydrateDraftFromDefinition(row as unknown as AgentDefinitionInput);
  }

  const baseline = defaultDraft();
  const triggerRaw = asRecord(row.trigger) || {};
  const memoryRaw = asRecord(row.memory) || {};

  const triggerType = String(triggerRaw.type || baseline.trigger.type).toLowerCase();
  const nextTriggerType: TriggerDraft["type"] =
    triggerType === "schedule" || triggerType === "event" || triggerType === "conversational"
      ? triggerType
      : baseline.trigger.type;

  const nextTools = Array.isArray(row.tools)
    ? row.tools.map((entry) => String(entry || "").trim()).filter(Boolean)
    : baseline.tools;

  const nextOutputBlocks = Array.isArray(row.output_block_types)
    ? row.output_block_types.map((entry) => String(entry || "").trim()).filter(Boolean)
    : baseline.output_block_types;

  const nextAllowedSubAgents = Array.isArray(row.allowed_sub_agent_ids)
    ? row.allowed_sub_agent_ids.map((entry) => String(entry || "").trim()).filter(Boolean)
    : baseline.allowed_sub_agent_ids;

  const nextTags = Array.isArray(row.tags)
    ? row.tags.map((entry) => String(entry || "").trim()).filter(Boolean)
    : baseline.tags;

  const nextGates = Array.isArray(row.gates)
    ? row.gates
        .map((entry) => asRecord(entry))
        .filter((entry): entry is Record<string, unknown> => Boolean(entry))
        .map((gate) => ({
          toolId: String(gate.toolId || "").trim(),
          requireApproval: Boolean(gate.requireApproval ?? true),
          timeoutMinutes: Math.max(1, Number(gate.timeoutMinutes || 60)),
          timeoutFallback: (() => {
            const fallback = String(gate.timeoutFallback || "skip").toLowerCase();
            if (fallback === "cancel" || fallback === "proceed" || fallback === "skip") {
              return fallback as ToolGate["timeoutFallback"];
            }
            return "skip" as ToolGate["timeoutFallback"];
          })(),
        }))
        .filter((gate) => gate.toolId)
    : baseline.gates;

  return {
    agent_id: slugifyAgentId(String(row.agent_id || row.id || baseline.agent_id)) || baseline.agent_id,
    version: String(row.version || baseline.version),
    name: String(row.name || baseline.name),
    description: String(row.description || baseline.description),
    author: String(row.author || baseline.author),
    tags: nextTags,
    system_prompt: String(row.system_prompt || baseline.system_prompt),
    tools: nextTools,
    memory: {
      working_enabled: Boolean(
        (asRecord(memoryRaw.working)?.enabled ?? memoryRaw.working_enabled ?? baseline.memory.working_enabled),
      ),
      episodic_enabled: Boolean(
        (asRecord(memoryRaw.episodic)?.enabled ?? memoryRaw.episodic_enabled ?? baseline.memory.episodic_enabled),
      ),
      semantic_enabled: Boolean(
        (asRecord(memoryRaw.semantic)?.enabled ?? memoryRaw.semantic_enabled ?? baseline.memory.semantic_enabled),
      ),
    },
    trigger: {
      type: nextTriggerType,
      value: String(triggerRaw.value || baseline.trigger.value),
    },
    gates: nextGates,
    output_block_types: nextOutputBlocks.length ? nextOutputBlocks : baseline.output_block_types,
    max_delegation_depth: Math.max(0, Number(row.max_delegation_depth || baseline.max_delegation_depth)),
    allowed_sub_agent_ids: nextAllowedSubAgents,
    pricing_model:
      row.pricing_model === "per_use" || row.pricing_model === "subscription"
        ? row.pricing_model
        : baseline.pricing_model,
    price_per_use_cents: Math.max(0, Number(row.price_per_use_cents || baseline.price_per_use_cents)),
    is_public: Boolean(row.is_public ?? baseline.is_public),
    cost_gate_usd: Math.max(0, Number(row.cost_gate_usd || baseline.cost_gate_usd)),
  };
}

function mapConnectorStatus(ok: unknown): "Connected" | "Not connected" {
  return ok ? "Connected" : "Not connected";
}

type AgentBuilderPageProps = {
  initialAgentId?: string;
};

export function AgentBuilderPage({ initialAgentId = "" }: AgentBuilderPageProps) {
  const [mode, setMode] = useState<BuilderMode>("visual");
  const [yamlError, setYamlError] = useState("");
  const [draft, setDraft] = useState<AgentDraft>(defaultDraft);
  const [yamlText, setYamlText] = useState(prettyYaml(defaultDraft()));
  const [saving, setSaving] = useState(false);
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  const [agentRows, setAgentRows] = useState<AgentSummaryRecord[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [connectors, setConnectors] = useState<ConnectorSummary[]>([]);

  const syncYamlFromDraft = (nextDraft: AgentDraft) => {
    setDraft(nextDraft);
    setYamlText(prettyYaml(nextDraft));
    setYamlError("");
  };

  const refreshCatalog = async () => {
    const rows = await listAgents();
    setAgentRows(Array.isArray(rows) ? rows : []);
  };

  const refreshConnectors = async () => {
    const [plugins, healthRows] = await Promise.all([listConnectorPlugins(), listConnectorHealth()]);
    const healthMap = new Map<string, boolean>();
    for (const health of healthRows || []) {
      const connectorId = String(health?.connector_id || "").trim();
      if (!connectorId) {
        continue;
      }
      healthMap.set(connectorId, Boolean(health?.ok));
    }
    const next: ConnectorSummary[] = (plugins || []).map((plugin) => {
      const toolIds = Array.isArray(plugin.actions)
        ? Array.from(new Set(plugin.actions.flatMap((action) => action.tool_ids || []).map((entry) => String(entry))))
        : [];
      return {
        id: plugin.connector_id,
        name: plugin.label || plugin.connector_id,
        description: `${toolIds.length} tools available`,
        authType: "oauth2",
        status: mapConnectorStatus(healthMap.get(plugin.connector_id)),
        tools: toolIds,
      };
    });
    setConnectors(next.sort((left, right) => left.name.localeCompare(right.name)));
  };

  const loadAgentIntoDraft = async (agentId: string) => {
    const detail = await getAgent(agentId);
    const nextDraft = hydrateDraftFromDefinition(detail.definition || ({} as AgentDefinitionInput));
    setSelectedAgentId(agentId);
    syncYamlFromDraft(nextDraft);
  };

  useEffect(() => {
    const load = async () => {
      setLoadingCatalog(true);
      try {
        await Promise.all([refreshCatalog(), refreshConnectors()]);
      } catch (error) {
        toast.error(`Failed to load builder catalog: ${String(error)}`);
      } finally {
        setLoadingCatalog(false);
      }
    };
    void load();
  }, []);

  useEffect(() => {
    const targetAgentId = String(initialAgentId || "").trim();
    if (!targetAgentId || loadingCatalog) {
      return;
    }
    if (selectedAgentId === targetAgentId) {
      return;
    }
    const exists = agentRows.some((row) => String(row.agent_id || "").trim() === targetAgentId);
    if (!exists) {
      return;
    }
    void loadAgentIntoDraft(targetAgentId);
  }, [agentRows, initialAgentId, loadingCatalog, selectedAgentId]);

  const parsedPreview = useMemo(() => prettyJson(buildDefinitionFromDraft(draft)), [draft]);
  const hasExistingAgent = Boolean(selectedAgentId);

  const saveDraft = async () => {
    const payload = buildDefinitionFromDraft(draft);
    setSaving(true);
    try {
      if (hasExistingAgent && selectedAgentId) {
        await updateAgent(selectedAgentId, payload);
        toast.success(`Updated ${selectedAgentId}`);
      } else {
        const created = await createAgent(payload);
        setSelectedAgentId(created.agent_id);
        toast.success(`Created ${created.agent_id}`);
      }
      await refreshCatalog();
    } catch (error) {
      toast.error(`Save failed: ${String(error)}`);
    } finally {
      setSaving(false);
    }
  };

  const resetToNew = () => {
    setSelectedAgentId(null);
    syncYamlFromDraft(defaultDraft());
  };

  const deleteCurrent = async () => {
    if (!selectedAgentId) {
      return;
    }
    const confirmed = window.confirm(`Delete agent "${selectedAgentId}"? This cannot be undone.`);
    if (!confirmed) {
      return;
    }
    setSaving(true);
    try {
      await deleteAgent(selectedAgentId);
      toast.success(`Deleted ${selectedAgentId}`);
      resetToNew();
      await refreshCatalog();
    } catch (error) {
      toast.error(`Delete failed: ${String(error)}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto bg-[#f6f6f7] p-5">
      <div className="mx-auto max-w-[1240px] space-y-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5 shadow-[0_20px_54px_rgba(15,23,42,0.1)]">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">Agent builder</p>
              <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">Create and configure agents</h1>
              <p className="mt-2 text-[15px] text-[#475467]">Visual and schema editing stay synchronized while saving to live backend APIs.</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={selectedAgentId || ""}
                onChange={(event) => {
                  const value = String(event.target.value || "");
                  if (!value) {
                    resetToNew();
                    return;
                  }
                  void loadAgentIntoDraft(value);
                }}
                className="h-10 min-w-[220px] rounded-xl border border-black/[0.12] bg-white px-3 text-[13px] text-[#111827]"
              >
                <option value="">{loadingCatalog ? "Loading agents..." : "New agent draft"}</option>
                {agentRows.map((row) => (
                  <option key={row.agent_id} value={row.agent_id}>
                    {row.name} ({row.agent_id})
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={resetToNew}
                className="h-10 rounded-xl border border-black/[0.12] bg-white px-4 text-[13px] font-semibold text-[#344054]"
              >
                New
              </button>
              <button
                type="button"
                onClick={() => void saveDraft()}
                disabled={saving}
                className="h-10 rounded-xl bg-[#7c3aed] px-4 text-[13px] font-semibold text-white disabled:opacity-60"
              >
                {saving ? "Saving..." : hasExistingAgent ? "Update agent" : "Create agent"}
              </button>
              {hasExistingAgent ? (
                <button
                  type="button"
                  onClick={() => void deleteCurrent()}
                  disabled={saving}
                  className="h-10 rounded-xl border border-[#fca5a5] bg-[#fff1f2] px-4 text-[13px] font-semibold text-[#9f1239] disabled:opacity-60"
                >
                  Delete
                </button>
              ) : null}
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            {([
              { key: "visual", label: "Visual" },
              { key: "yaml", label: "YAML" },
              { key: "memory", label: "Memory" },
              { key: "test_run", label: "Test Run" },
            ] as const).map((entry) => (
              <button
                key={entry.key}
                type="button"
                onClick={() => setMode(entry.key)}
                className={`rounded-full px-4 py-2 text-[13px] font-semibold capitalize ${
                  mode === entry.key ? "bg-[#7c3aed] text-white shadow-[0_1px_3px_rgba(124,58,237,0.3)]" : "border border-black/[0.08] bg-white text-[#344054] hover:bg-[#f5f3ff] hover:text-[#7c3aed]"
                }`}
              >
                {entry.label}
              </button>
            ))}
          </div>
        </section>

        {mode === "visual" ? (
          <section className="grid grid-cols-1 gap-4 xl:grid-cols-[1.05fr_0.95fr]">
            <div className="space-y-4">
              <div className="rounded-2xl border border-black/[0.08] bg-white p-4">
                <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">Identity</p>
                <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <label>
                    <span className="text-[12px] font-semibold text-[#344054]">Agent ID</span>
                    <input
                      value={draft.agent_id}
                      onChange={(event) => syncYamlFromDraft({ ...draft, agent_id: slugifyAgentId(event.target.value) })}
                      className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
                    />
                  </label>
                  <label>
                    <span className="text-[12px] font-semibold text-[#344054]">Version</span>
                    <input
                      value={draft.version}
                      onChange={(event) => syncYamlFromDraft({ ...draft, version: event.target.value })}
                      className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
                    />
                  </label>
                  <label>
                    <span className="text-[12px] font-semibold text-[#344054]">Name</span>
                    <input
                      value={draft.name}
                      onChange={(event) => syncYamlFromDraft({ ...draft, name: event.target.value })}
                      className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
                    />
                  </label>
                  <label>
                    <span className="text-[12px] font-semibold text-[#344054]">Author</span>
                    <input
                      value={draft.author}
                      onChange={(event) => syncYamlFromDraft({ ...draft, author: event.target.value })}
                      className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
                    />
                  </label>
                </div>
                <label className="mt-3 block">
                  <span className="text-[12px] font-semibold text-[#344054]">Description</span>
                  <textarea
                    value={draft.description}
                    onChange={(event) => syncYamlFromDraft({ ...draft, description: event.target.value })}
                    className="mt-1 h-20 w-full resize-none rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
                  />
                </label>
              </div>

              <SystemPromptEditor
                value={draft.system_prompt}
                onChange={(next) => syncYamlFromDraft({ ...draft, system_prompt: next })}
              />

              <ToolSelector
                connectors={connectors}
                selectedTools={draft.tools}
                onChange={(next) => syncYamlFromDraft({ ...draft, tools: next })}
              />
            </div>

            <div className="space-y-4">
              <GateConfig
                tools={draft.tools}
                gates={draft.gates}
                onChange={(next) => syncYamlFromDraft({ ...draft, gates: next })}
                maxCostBeforePause={draft.cost_gate_usd}
                onChangeMaxCostBeforePause={(next) => syncYamlFromDraft({ ...draft, cost_gate_usd: next })}
              />

              <div className="rounded-2xl border border-black/[0.08] bg-white p-4">
                <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">Trigger</p>
                <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <label>
                    <span className="text-[12px] font-semibold text-[#344054]">Type</span>
                    <select
                      value={draft.trigger.type}
                      onChange={(event) =>
                        syncYamlFromDraft({
                          ...draft,
                          trigger: {
                            ...draft.trigger,
                            type: event.target.value as TriggerDraft["type"],
                          },
                        })
                      }
                      className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
                    >
                      <option value="conversational">Conversational</option>
                      <option value="schedule">Scheduled</option>
                      <option value="event">On event</option>
                    </select>
                  </label>
                  <label>
                    <span className="text-[12px] font-semibold text-[#344054]">
                      {draft.trigger.type === "schedule"
                        ? "Cron expression"
                        : draft.trigger.type === "event"
                          ? "Event type"
                          : "Keyword"}
                    </span>
                    <input
                      value={draft.trigger.value}
                      onChange={(event) =>
                        syncYamlFromDraft({
                          ...draft,
                          trigger: { ...draft.trigger, value: event.target.value },
                        })
                      }
                      className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
                    />
                  </label>
                </div>
              </div>

              <div className="rounded-2xl border border-black/[0.08] bg-white p-4">
                <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">Output blocks</p>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  {OUTPUT_BLOCK_OPTIONS.map((option) => {
                    const checked = draft.output_block_types.includes(option);
                    return (
                      <label key={option} className="inline-flex items-center gap-2 text-[13px] text-[#344054]">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(event) => {
                            const next = event.target.checked
                              ? [...draft.output_block_types, option]
                              : draft.output_block_types.filter((type) => type !== option);
                            syncYamlFromDraft({ ...draft, output_block_types: next });
                          }}
                        />
                        {option}
                      </label>
                    );
                  })}
                </div>
              </div>

              <div className="rounded-2xl border border-black/[0.08] bg-white p-4">
                <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">Runtime controls</p>
                <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <label>
                    <span className="text-[12px] font-semibold text-[#344054]">Max delegation depth</span>
                    <input
                      type="number"
                      min={0}
                      max={10}
                      value={draft.max_delegation_depth}
                      onChange={(event) =>
                        syncYamlFromDraft({
                          ...draft,
                          max_delegation_depth: Number(event.target.value || 0),
                        })
                      }
                      className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
                    />
                  </label>
                  <label>
                    <span className="text-[12px] font-semibold text-[#344054]">Pricing model</span>
                    <select
                      value={draft.pricing_model}
                      onChange={(event) =>
                        syncYamlFromDraft({
                          ...draft,
                          pricing_model: event.target.value as AgentDraft["pricing_model"],
                        })
                      }
                      className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
                    >
                      <option value="free">Free</option>
                      <option value="per_use">Per use</option>
                      <option value="subscription">Subscription</option>
                    </select>
                  </label>
                </div>
                <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <label>
                    <span className="text-[12px] font-semibold text-[#344054]">Price per use (cents)</span>
                    <input
                      type="number"
                      min={0}
                      value={draft.price_per_use_cents}
                      onChange={(event) =>
                        syncYamlFromDraft({
                          ...draft,
                          price_per_use_cents: Number(event.target.value || 0),
                        })
                      }
                      className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
                    />
                  </label>
                  <label className="inline-flex items-center gap-2 pt-7 text-[13px] font-semibold text-[#344054]">
                    <input
                      type="checkbox"
                      checked={draft.is_public}
                      onChange={(event) => syncYamlFromDraft({ ...draft, is_public: event.target.checked })}
                    />
                    List in marketplace
                  </label>
                </div>
              </div>
            </div>
          </section>
        ) : mode === "yaml" ? (
          <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
            <p className="mb-2 text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">Schema editor (YAML)</p>
            <textarea
              value={yamlText}
              onChange={(event) => setYamlText(event.target.value)}
              className="h-[460px] w-full resize-none rounded-xl border border-black/[0.12] bg-[#0b1020] px-3 py-2 font-mono text-[12px] leading-[1.55] text-[#d1e0ff]"
            />
            <p className="mt-2 text-[12px] text-[#667085]">
              Paste either agent draft YAML or full definition YAML/JSON. Visual mode stays in sync after apply.
            </p>
            <div className="mt-3 flex items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  try {
                    const parsed = parseYaml(yamlText);
                    const nextDraft = coerceDraftFromEditor(parsed);
                    syncYamlFromDraft(nextDraft);
                  } catch (error) {
                    setYamlError(`Invalid YAML/JSON: ${String(error)}`);
                  }
                }}
                className="rounded-full bg-[#7c3aed] px-4 py-2 text-[13px] font-semibold text-white"
              >
                Apply editor changes
              </button>
              {yamlError ? <span className="text-[12px] text-[#b42318]">{yamlError}</span> : null}
            </div>
          </section>
        ) : mode === "memory" ? (
          <section className="rounded-2xl border border-black/[0.08] bg-white p-0">
            {selectedAgentId ? (
              <div className="h-[560px] min-h-0">
                <AgentMemoryTab agentId={selectedAgentId} />
              </div>
            ) : (
              <div className="px-5 py-8 text-[13px] text-[#667085]">
                Save this draft first to create an `agent_id`, then memory entries can be viewed and managed here.
              </div>
            )}
          </section>
        ) : (
          <section className="rounded-2xl border border-black/[0.08] bg-white p-0">
            {selectedAgentId ? (
              <div className="h-[640px] min-h-0">
                <SimulationPanel agentId={selectedAgentId} />
              </div>
            ) : (
              <div className="px-5 py-8 text-[13px] text-[#667085]">
                Save this draft first to run a simulation against a persisted agent.
              </div>
            )}
          </section>
        )}

        <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
          <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">Compiled definition preview</p>
          <pre className="mt-2 overflow-x-auto rounded-xl border border-black/[0.08] bg-[#f8fafc] p-3 text-[12px] text-[#344054]">
            <code>{parsedPreview}</code>
          </pre>
        </section>
      </div>
    </div>
  );
}
