import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import {
  getConnectorBinding,
  getAgent,
  getImprovementSuggestion,
  listAgentRuns,
  patchConnectorBinding,
  recordFeedback,
  updateAgent,
  type AgentDefinitionInput,
  type AgentDefinitionRecord,
  type ImprovementSuggestionRecord,
} from "../../api/client";
import { AgentRunHistory, type AgentRunHistoryRecord } from "../components/agents/AgentRunHistory";
import { ImprovementSuggestion } from "../components/agents/ImprovementSuggestion";
import { PageMonitorPanel } from "../components/agents/PageMonitorPanel";

type AgentDetailPageProps = {
  agentId: string;
  initialTab?: AgentDetailTab;
};

type AgentDetailTab = "overview" | "history" | "improvement" | "monitor";

function hasPageMonitorCapability(agent: AgentDefinitionRecord | null): boolean {
  if (!agent) {
    return false;
  }
  const agentId = String(agent.agent_id || "").trim().toLowerCase();
  if (agentId === "competitor-change-radar") {
    return true;
  }
  const definition = (agent.definition || {}) as Record<string, unknown>;
  const tools = Array.isArray(definition.tools) ? definition.tools : [];
  if (
    tools.some((entry) =>
      /page[_-]?monitor|monitor[_-]?page|competitor[_-]?page/i.test(String(entry || "")),
    )
  ) {
    return true;
  }
  const tags = Array.isArray(definition.tags) ? definition.tags : [];
  return tags.some((entry) => /page[_-]?monitor|competitor/i.test(String(entry || "")));
}

function normalizeConnectorId(value: unknown): string {
  return String(value || "").trim().toLowerCase();
}

function inferRequiredConnectors(definition: Record<string, unknown>): string[] {
  const explicit = Array.isArray(definition.required_connectors)
    ? definition.required_connectors.map((entry) => normalizeConnectorId(entry)).filter(Boolean)
    : [];
  if (explicit.length > 0) {
    return Array.from(new Set(explicit));
  }
  const tools = Array.isArray(definition.tools) ? definition.tools : [];
  const derived = tools
    .map((entry) => String(entry || "").trim().toLowerCase())
    .filter(Boolean)
    .map((toolId) => toolId.split(".")[0])
    .map((prefix) => {
      if (prefix === "gmail" || prefix === "gcalendar" || prefix === "gdrive" || prefix === "ga4") {
        return "google_workspace";
      }
      return prefix;
    })
    .filter((prefix) => prefix && prefix !== "http" && prefix !== "browser" && prefix !== "canvas");
  return Array.from(new Set(derived));
}

function mapRunToUi(run: {
  run_id: string;
  agent_id: string;
  status: string;
  trigger_type: string;
  started_at: string;
  ended_at?: string | null;
  error?: string | null;
  result_summary?: string | null;
}): AgentRunHistoryRecord {
  const startedAt = String(run.started_at || new Date().toISOString());
  const endedAt = run.ended_at || null;
  const startMs = new Date(startedAt).getTime();
  const endMs = endedAt ? new Date(endedAt).getTime() : Date.now();
  const durationMs = Number.isFinite(startMs) && Number.isFinite(endMs) && endMs >= startMs ? endMs - startMs : 0;
  return {
    runId: String(run.run_id || ""),
    agentId: String(run.agent_id || ""),
    triggerType: String(run.trigger_type || "manual"),
    status: String(run.status || "unknown"),
    durationMs,
    llmCostUsd: 0,
    startedAt,
    outputSummary: String(run.result_summary || "No summary available."),
    errorMessage: String(run.error || ""),
  };
}

export function AgentDetailPage({ agentId, initialTab = "overview" }: AgentDetailPageProps) {
  const [activeTab, setActiveTab] = useState<AgentDetailTab>(initialTab);
  const [agentDetail, setAgentDetail] = useState<AgentDefinitionRecord | null>(null);
  const [runs, setRuns] = useState<AgentRunHistoryRecord[]>([]);
  const [suggestion, setSuggestion] = useState<ImprovementSuggestionRecord | null>(null);
  const [suggestionLoading, setSuggestionLoading] = useState(false);
  const [suggestionError, setSuggestionError] = useState("");
  const [suggestionDismissed, setSuggestionDismissed] = useState(false);
  const [applyingSuggestion, setApplyingSuggestion] = useState(false);
  const [suggestionRefreshNonce, setSuggestionRefreshNonce] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [connectorAccessMap, setConnectorAccessMap] = useState<Record<string, boolean>>({});
  const [connectorAllowedAgentMap, setConnectorAllowedAgentMap] = useState<Record<string, string[]>>({});
  const [connectorAccessError, setConnectorAccessError] = useState("");
  const [savingConnectorId, setSavingConnectorId] = useState("");

  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab, agentId]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const [agent, runRows] = await Promise.all([getAgent(agentId), listAgentRuns(agentId)]);
        setAgentDetail(agent);
        setRuns((runRows || []).map(mapRunToUi));
      } catch (nextError) {
        setError(String(nextError));
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [agentId]);

  useEffect(() => {
    if (activeTab !== "improvement" || suggestionDismissed) {
      return;
    }
    let cancelled = false;
    const loadSuggestion = async () => {
      setSuggestionLoading(true);
      setSuggestionError("");
      try {
        const row = await getImprovementSuggestion(agentId);
        if (cancelled) {
          return;
        }
        setSuggestion(row);
      } catch (nextError) {
        if (cancelled) {
          return;
        }
        setSuggestion(null);
        setSuggestionError(String(nextError || "No suggestion available yet."));
      } finally {
        if (!cancelled) {
          setSuggestionLoading(false);
        }
      }
    };
    void loadSuggestion();
    return () => {
      cancelled = true;
    };
  }, [activeTab, agentId, suggestionDismissed, suggestionRefreshNonce]);

  const definitionPreview = useMemo(
    () => JSON.stringify(agentDetail?.definition || {}, null, 2),
    [agentDetail?.definition],
  );
  const requiredConnectors = useMemo(
    () => inferRequiredConnectors((agentDetail?.definition || {}) as Record<string, unknown>),
    [agentDetail?.definition],
  );
  const monitorEnabled = useMemo(() => hasPageMonitorCapability(agentDetail), [agentDetail]);
  const tabs = useMemo(
    () =>
      (["overview", "history", "improvement", ...(monitorEnabled ? (["monitor"] as const) : [])] as const),
    [monitorEnabled],
  );

  useEffect(() => {
    if (activeTab === "monitor" && !monitorEnabled) {
      setActiveTab("overview");
    }
  }, [activeTab, monitorEnabled]);

  useEffect(() => {
    if (!agentDetail || requiredConnectors.length === 0) {
      setConnectorAccessMap({});
      setConnectorAllowedAgentMap({});
      setConnectorAccessError("");
      return;
    }
    let cancelled = false;
    const loadConnectorAccess = async () => {
      setConnectorAccessError("");
      try {
        const bindingRows = await Promise.all(
          requiredConnectors.map(async (connectorId) => {
            try {
              const binding = await getConnectorBinding(connectorId);
              const allowed = Array.isArray(binding.allowed_agent_ids)
                ? binding.allowed_agent_ids.map((entry) => String(entry || "").trim()).filter(Boolean)
                : [];
              return [connectorId, allowed] as const;
            } catch {
              return [connectorId, []] as const;
            }
          }),
        );
        if (cancelled) {
          return;
        }
        const nextAllowedMap: Record<string, string[]> = {};
        const nextAccessMap: Record<string, boolean> = {};
        for (const [connectorId, allowedAgentIds] of bindingRows) {
          nextAllowedMap[connectorId] = allowedAgentIds;
          nextAccessMap[connectorId] = allowedAgentIds.includes(agentDetail.agent_id);
        }
        setConnectorAllowedAgentMap(nextAllowedMap);
        setConnectorAccessMap(nextAccessMap);
      } catch (nextError) {
        if (!cancelled) {
          setConnectorAccessError(String(nextError || "Failed to load connector permissions."));
        }
      }
    };
    void loadConnectorAccess();
    return () => {
      cancelled = true;
    };
  }, [agentDetail, requiredConnectors]);

  if (loading) {
    return (
      <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
        <div className="mx-auto max-w-[1080px] rounded-2xl border border-black/[0.08] bg-white p-5 text-[14px] text-[#667085]">
          Loading agent details...
        </div>
      </div>
    );
  }

  if (error || !agentDetail) {
    return (
      <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
        <div className="mx-auto max-w-[1080px] rounded-2xl border border-[#fecaca] bg-[#fff1f2] p-5">
          <h1 className="text-[24px] font-semibold text-[#9f1239]">Agent not found</h1>
          <p className="mt-2 text-[13px] text-[#b42318]">{error || "No agent data returned."}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
      <div className="mx-auto max-w-[1240px] space-y-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5 shadow-[0_20px_54px_rgba(15,23,42,0.1)]">
          <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">Agent detail</p>
          <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">{agentDetail.name}</h1>
          <p className="mt-2 text-[14px] text-[#475467]">
            Agent ID: <span className="font-semibold text-[#111827]">{agentDetail.agent_id}</span> · Version{" "}
            <span className="font-semibold text-[#111827]">{agentDetail.version}</span>
          </p>
          <div className="mt-4 flex gap-2">
            {tabs.map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setActiveTab(tab)}
                className={`rounded-full px-3 py-1.5 text-[12px] font-semibold capitalize ${
                  activeTab === tab ? "bg-[#111827] text-white" : "border border-black/[0.12] bg-white text-[#344054]"
                }`}
              >
                {tab}
              </button>
            ))}
            <a
              href="/agent-builder"
              className="rounded-full border border-black/[0.12] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#344054]"
            >
              Open builder
            </a>
          </div>
        </section>

        {activeTab === "overview" ? (
          <div className="space-y-4">
            <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
              <h2 className="text-[18px] font-semibold text-[#111827]">Definition</h2>
              <pre className="mt-3 overflow-x-auto rounded-xl border border-black/[0.08] bg-[#f8fafc] p-3 text-[12px] text-[#344054]">
                <code>{definitionPreview}</code>
              </pre>
            </section>

            {requiredConnectors.length > 0 ? (
              <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
                <h2 className="text-[18px] font-semibold text-[#111827]">Connector permissions</h2>
                <p className="mt-1 text-[13px] text-[#667085]">
                  Control whether this agent is allowed to execute actions on each required connector.
                </p>
                {connectorAccessError ? (
                  <p className="mt-3 rounded-xl border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-[12px] text-[#9f1239]">
                    {connectorAccessError}
                  </p>
                ) : null}
                <div className="mt-3 space-y-2">
                  {requiredConnectors.map((connectorId) => {
                    const checked = Boolean(connectorAccessMap[connectorId]);
                    const saving = savingConnectorId === connectorId;
                    return (
                      <label
                        key={connectorId}
                        className="flex items-center justify-between gap-3 rounded-xl border border-black/[0.08] bg-[#f8fafc] px-3 py-2"
                      >
                        <div>
                          <p className="text-[13px] font-semibold text-[#111827]">{connectorId}</p>
                          <p className="text-[12px] text-[#667085]">
                            {checked ? "Allowed for this agent" : "Blocked for this agent"}
                          </p>
                        </div>
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={saving}
                          onChange={async (event) => {
                            const allow = event.target.checked;
                            const existingAllowed = Array.isArray(connectorAllowedAgentMap[connectorId])
                              ? connectorAllowedAgentMap[connectorId]
                              : [];
                            const nextAllowed = allow
                              ? Array.from(new Set([...existingAllowed, agentDetail.agent_id]))
                              : existingAllowed.filter((entry) => entry !== agentDetail.agent_id);
                            setSavingConnectorId(connectorId);
                            setConnectorAccessError("");
                            try {
                              await patchConnectorBinding(connectorId, { allowed_agent_ids: nextAllowed });
                              setConnectorAllowedAgentMap((previous) => ({
                                ...previous,
                                [connectorId]: nextAllowed,
                              }));
                              setConnectorAccessMap((previous) => ({
                                ...previous,
                                [connectorId]: allow,
                              }));
                              toast.success(`${connectorId} permission updated.`);
                            } catch (nextError) {
                              setConnectorAccessError(
                                `Failed to update ${connectorId}: ${String(nextError || "Unknown error")}`,
                              );
                            } finally {
                              setSavingConnectorId("");
                            }
                          }}
                          className="h-4 w-4 rounded border border-black/[0.2]"
                        />
                      </label>
                    );
                  })}
                </div>
              </section>
            ) : null}
          </div>
        ) : null}

        {activeTab === "history" ? (
          <AgentRunHistory
            runs={runs}
            onOpenReplay={(runId) => toast.message(`Opening replay for ${runId}`)}
            onSubmitFeedback={async ({ runId, feedbackType, originalOutput, correctedOutput }) => {
              await recordFeedback(agentId, runId, originalOutput, correctedOutput, feedbackType);
              toast.success("Feedback saved.");
              if (activeTab === "improvement") {
                setSuggestionDismissed(false);
              }
            }}
          />
        ) : null}

        {activeTab === "improvement" ? (
          <ImprovementSuggestion
            feedbackCount={suggestion?.feedback_count || 0}
            currentPrompt={String((agentDetail.definition as { system_prompt?: string })?.system_prompt || "")}
            suggestedPrompt={suggestion?.suggested_prompt || ""}
            reasoning={suggestion?.reasoning || ""}
            loading={suggestionLoading || applyingSuggestion}
            error={suggestionError}
            onApply={async () => {
              if (!agentDetail || !suggestion?.suggested_prompt) {
                toast.error("No suggestion available to apply.");
                return;
              }
              setApplyingSuggestion(true);
              try {
                const currentDefinition = (agentDetail.definition || {}) as Record<string, unknown>;
                const payload: AgentDefinitionInput = {
                  ...(currentDefinition as AgentDefinitionInput),
                  id: String(currentDefinition.id || agentDetail.agent_id || ""),
                  name: String(currentDefinition.name || agentDetail.name || agentDetail.agent_id),
                  system_prompt: suggestion.suggested_prompt,
                };
                await updateAgent(agentId, payload);
                const refreshed = await getAgent(agentId);
                setAgentDetail(refreshed);
                toast.success("Improvement suggestion applied.");
              } catch (nextError) {
                toast.error(`Failed to apply suggestion: ${String(nextError)}`);
              } finally {
                setApplyingSuggestion(false);
              }
            }}
            onRefresh={() => {
              setSuggestionDismissed(false);
              setSuggestion(null);
              setSuggestionError("");
              setSuggestionRefreshNonce((previous) => previous + 1);
            }}
            onDismiss={() => {
              setSuggestionDismissed(true);
              setSuggestion(null);
              setSuggestionError("");
            }}
          />
        ) : null}

        {activeTab === "monitor" && monitorEnabled ? (
          <PageMonitorPanel agentId={agentDetail.agent_id} />
        ) : null}
      </div>
    </div>
  );
}
