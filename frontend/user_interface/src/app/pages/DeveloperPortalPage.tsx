import { useEffect, useMemo, useState } from "react";
import { Clock, ShieldX } from "lucide-react";
import { toast } from "sonner";

import {
  getDeveloperStatus,
  listConnectorCatalog,
  listMarketplaceAgents,
  listMarketplaceAgentVersions,
  publishMarketplaceAgent,
  reviseMarketplaceAgent,
  submitMarketplaceAgent,
  type ConnectorCatalogRecord,
  type DeveloperStatus,
  type MarketplaceAgentSummary,
  type MarketplaceAgentVersionRecord,
} from "../../api/client";
import { DeveloperApplicationForm } from "../components/developer/DeveloperApplicationForm";

type TabKey = "agents" | "new" | "guide";
type TriggerFamily = "manual" | "scheduled" | "on_event";

type Draft = {
  id: string;
  name: string;
  description: string;
  version: string;
  author: string;
  tags: string;
  requiredConnectors: string[];
  tools: string[];
  systemPrompt: string;
  triggerFamily: TriggerFamily;
  cron: string;
  timezone: string;
  eventType: string;
  sourceConnector: string;
  pricing: "free" | "paid" | "enterprise";
  changelog: string;
};

const EMPTY_DRAFT: Draft = {
  id: "",
  name: "",
  description: "",
  version: "1.0.0",
  author: "",
  tags: "",
  requiredConnectors: [],
  tools: [],
  systemPrompt: "",
  triggerFamily: "manual",
  cron: "0 9 * * 1",
  timezone: "UTC",
  eventType: "",
  sourceConnector: "",
  pricing: "free",
  changelog: "",
};

function titleCase(value: string): string {
  return String(value || "")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function statusClass(status: string): string {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "published") return "border-[#bbf7d0] bg-[#f0fdf4] text-[#166534]";
  if (normalized === "approved") return "border-[#bfdbfe] bg-[#eff6ff] text-[#1d4ed8]";
  if (normalized === "pending_review") return "border-[#fde68a] bg-[#fffbeb] text-[#92400e]";
  if (normalized === "rejected") return "border-[#fecaca] bg-[#fff1f2] text-[#b42318]";
  return "border-[#d0d5dd] bg-[#f8fafc] text-[#475467]";
}

function buildDefinition(draft: Draft): Record<string, unknown> {
  const tags = draft.tags
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);

  const definition: Record<string, unknown> = {
    id: draft.id.trim(),
    name: draft.name.trim(),
    description: draft.description.trim(),
    version: draft.version.trim(),
    author: draft.author.trim(),
    tags,
    required_connectors: draft.requiredConnectors,
    tools: draft.tools,
    system_prompt: draft.systemPrompt,
    pricing_model: draft.pricing,
  };

  if (draft.triggerFamily === "scheduled") {
    definition.trigger = {
      family: "scheduled",
      cron_expression: draft.cron.trim(),
      timezone: draft.timezone.trim() || "UTC",
    };
  } else if (draft.triggerFamily === "on_event") {
    definition.trigger = {
      family: "on_event",
      event_type: draft.eventType.trim(),
      source_connector: draft.sourceConnector.trim(),
    };
  }
  return definition;
}

export function DeveloperPortalPage() {
  const [devStatus, setDevStatus] = useState<DeveloperStatus | "loading">("loading");
  const [rejectionReason, setRejectionReason] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>("agents");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [agents, setAgents] = useState<MarketplaceAgentSummary[]>([]);
  const [catalog, setCatalog] = useState<ConnectorCatalogRecord[]>([]);
  const [expandedAgentId, setExpandedAgentId] = useState<string | null>(null);
  const [versionsByAgent, setVersionsByAgent] = useState<Record<string, MarketplaceAgentVersionRecord[]>>({});
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [publishing, setPublishing] = useState(false);
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [selectedStatus, setSelectedStatus] = useState("");
  const [editingRejectedAgentId, setEditingRejectedAgentId] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [agentRows, connectorRows] = await Promise.all([
        listMarketplaceAgents({ sort_by: "newest", limit: 200 }),
        listConnectorCatalog(),
      ]);
      setAgents(Array.isArray(agentRows) ? agentRows : []);
      setCatalog(Array.isArray(connectorRows) ? connectorRows : []);
    } catch (nextError) {
      setError(String(nextError || "Failed to load developer portal."));
    } finally {
      setLoading(false);
    }
  };

  const fetchDevStatus = async () => {
    try {
      const result = await getDeveloperStatus();
      setDevStatus(result.status);
      setRejectionReason(result.rejection_reason || null);
    } catch {
      setDevStatus("none");
    }
  };

  useEffect(() => {
    void fetchDevStatus();
  }, []);

  useEffect(() => {
    if (devStatus === "verified" || devStatus === "trusted_publisher") {
      void load();
    }
  }, [devStatus]);

  const toolsByConnector = useMemo(() => {
    const map = new Map<string, Array<{ id: string; label: string }>>();
    for (const connector of catalog) {
      const id = String(connector.id || "").trim();
      if (!id) continue;
      const tools = (connector.tools || []).map((tool) => ({
        id: String(tool.id || ""),
        label: String(tool.title || tool.id || ""),
      }));
      map.set(id, tools);
    }
    return map;
  }, [catalog]);

  const draftInvalid =
    !draft.id.trim() ||
    !draft.name.trim() ||
    !draft.systemPrompt.trim() ||
    draft.tools.length === 0 ||
    (draft.triggerFamily === "scheduled" && !draft.cron.trim()) ||
    (draft.triggerFamily === "on_event" && (!draft.eventType.trim() || !draft.sourceConnector.trim()));

  const loadVersions = async (agentId: string) => {
    if (!agentId || versionsByAgent[agentId]) return;
    try {
      const rows = await listMarketplaceAgentVersions(agentId);
      setVersionsByAgent((prev) => ({ ...prev, [agentId]: Array.isArray(rows) ? rows : [] }));
    } catch (nextError) {
      toast.error(String(nextError || "Failed to load version history."));
    }
  };

  const editRejected = (agent: MarketplaceAgentSummary) => {
    setDraft((prev) => ({
      ...prev,
      id: agent.agent_id,
      name: agent.name,
      description: agent.description,
      version: agent.version,
      tags: (agent.tags || []).join(", "),
      requiredConnectors: agent.required_connectors || [],
      changelog: "",
    }));
    setEditingRejectedAgentId(agent.agent_id);
    setSelectedAgentId(agent.agent_id);
    setSelectedStatus(agent.status);
    setTab("new");
  };

  const createOrRevise = async () => {
    if (draftInvalid) {
      toast.error("Fill all required fields and select at least one tool.");
      return;
    }
    setPublishing(true);
    try {
      const definition = buildDefinition(draft);
      if (editingRejectedAgentId) {
        const revised = await reviseMarketplaceAgent(editingRejectedAgentId, {
          definition,
          changelog: draft.changelog.trim(),
        });
        setSelectedAgentId(revised.agent_id);
        setSelectedStatus(revised.status);
        toast.success(`Revised ${revised.agent_id}.`);
      } else {
        const created = await publishMarketplaceAgent({
          definition,
          metadata: { changelog: draft.changelog.trim() },
        });
        setSelectedAgentId(created.agent_id);
        setSelectedStatus(created.status);
        toast.success(`Draft created: ${created.agent_id}.`);
      }
      await load();
    } catch (nextError) {
      toast.error(String(nextError || "Failed to save draft."));
    } finally {
      setPublishing(false);
    }
  };

  const submitForReview = async () => {
    if (!selectedAgentId) {
      toast.error("Create or revise a draft first.");
      return;
    }
    setPublishing(true);
    try {
      const response = await submitMarketplaceAgent(selectedAgentId);
      setSelectedStatus(response.status);
      toast.success(`${response.agent_id} submitted for review.`);
      setTab("agents");
      await load();
    } catch (nextError) {
      toast.error(String(nextError || "Failed to submit draft."));
    } finally {
      setPublishing(false);
    }
  };

  // ── Gate: show application form or pending/rejected state ──────────────────
  if (devStatus === "loading") {
    return (
      <div className="flex h-full items-center justify-center bg-[#eef1f5]">
        <p className="text-[13px] text-[#86868b]">Loading developer status…</p>
      </div>
    );
  }

  if (devStatus === "none" || devStatus === "rejected") {
    return (
      <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
        <div className="mx-auto max-w-[1240px]">
          <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5">
            <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">Developer portal</p>
            <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">Publish agents</h1>
          </section>
          {devStatus === "rejected" && rejectionReason ? (
            <div className="mt-4 flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 p-4">
              <ShieldX className="mt-0.5 h-5 w-5 shrink-0 text-red-500" />
              <div>
                <p className="text-[13px] font-semibold text-red-800">Application rejected</p>
                <p className="mt-1 text-[12px] text-red-700">{rejectionReason}</p>
                <p className="mt-1 text-[12px] text-red-600">You can re-apply below with updated information.</p>
              </div>
            </div>
          ) : null}
          <div className="mt-4 rounded-2xl border border-black/[0.08] bg-white p-4">
            <DeveloperApplicationForm onSuccess={fetchDevStatus} />
          </div>
        </div>
      </div>
    );
  }

  if (devStatus === "pending") {
    return (
      <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
        <div className="mx-auto max-w-[1240px]">
          <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5">
            <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">Developer portal</p>
            <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">Publish agents</h1>
          </section>
          <div className="mt-4 flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-6">
            <Clock className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
            <div>
              <p className="text-[15px] font-semibold text-amber-900">Application under review</p>
              <p className="mt-1 text-[13px] text-amber-700">
                Your developer application is being reviewed. You&apos;ll be notified once a decision is made.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
      <div className="mx-auto max-w-[1240px] space-y-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5">
          <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">Developer portal</p>
          <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">Publish agents</h1>
          <div className="mt-4 flex flex-wrap gap-2">
            {[
              { key: "agents", label: "My agents" },
              { key: "new", label: "New agent" },
              { key: "guide", label: "Guidelines" },
            ].map((entry) => (
              <button
                key={entry.key}
                type="button"
                onClick={() => setTab(entry.key as TabKey)}
                className={`rounded-full px-3 py-1.5 text-[12px] font-semibold ${
                  tab === entry.key ? "bg-[#111827] text-white" : "border border-black/[0.12] bg-white text-[#344054]"
                }`}
              >
                {entry.label}
              </button>
            ))}
          </div>
        </section>

        {error ? <section className="rounded-2xl border border-[#fca5a5] bg-[#fff1f2] p-4 text-[13px] text-[#9f1239]">{error}</section> : null}

        {tab === "agents" ? (
          <section className="space-y-3">
            {loading ? <div className="rounded-2xl border border-black/[0.08] bg-white p-4 text-[13px] text-[#667085]">Loading agents...</div> : null}
            {agents.map((agent) => (
              <article key={agent.id} className="rounded-2xl border border-black/[0.08] bg-white p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-[18px] font-semibold text-[#101828]">{agent.name}</p>
                    <p className="mt-1 text-[12px] text-[#667085]">{agent.agent_id} · v{agent.version}</p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${statusClass(agent.status)}`}>{titleCase(agent.status)}</span>
                      {(agent.tags || []).slice(0, 5).map((tag) => (
                        <span key={`${agent.id}-${tag}`} className="rounded-full border border-black/[0.08] bg-white px-2 py-0.5 text-[11px] text-[#475467]">#{tag}</span>
                      ))}
                    </div>
                    {agent.status === "rejected" ? (
                      <p className="mt-2 text-[12px] text-[#b42318]">Rejected. Open edit mode and resubmit with fixes.</p>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        const next = expandedAgentId === agent.agent_id ? null : agent.agent_id;
                        setExpandedAgentId(next);
                        if (next) void loadVersions(next);
                      }}
                      className="rounded-full border border-black/[0.12] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#344054]"
                    >
                      {expandedAgentId === agent.agent_id ? "Hide versions" : "Version history"}
                    </button>
                    {agent.status === "rejected" ? (
                      <button type="button" onClick={() => editRejected(agent)} className="rounded-full bg-[#111827] px-3 py-1.5 text-[12px] font-semibold text-white">
                        Edit & resubmit
                      </button>
                    ) : null}
                  </div>
                </div>
                {expandedAgentId === agent.agent_id ? (
                  <div className="mt-3 rounded-xl border border-black/[0.08] bg-[#fcfcfd] p-3">
                    {(versionsByAgent[agent.agent_id] || []).length === 0 ? (
                      <p className="text-[12px] text-[#667085]">No version history found.</p>
                    ) : (
                      <div className="space-y-2">
                        {(versionsByAgent[agent.agent_id] || []).map((versionRow) => (
                          <div key={versionRow.id} className="rounded-lg border border-black/[0.08] bg-white px-3 py-2">
                            <p className="text-[12px] font-semibold text-[#111827]">v{versionRow.version} · {titleCase(versionRow.status)}</p>
                            {versionRow.changelog ? <p className="mt-1 text-[12px] text-[#475467]">{versionRow.changelog}</p> : null}
                            {versionRow.rejection_reason ? <p className="mt-1 text-[12px] text-[#b42318]">Reason: {versionRow.rejection_reason}</p> : null}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ) : null}
              </article>
            ))}
          </section>
        ) : null}

        {tab === "new" ? (
          <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
            <h2 className="text-[18px] font-semibold text-[#111827]">New agent submission</h2>
            <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
              <input value={draft.id} onChange={(event) => setDraft((prev) => ({ ...prev, id: event.target.value }))} placeholder="Agent ID" className="rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]" />
              <input value={draft.name} onChange={(event) => setDraft((prev) => ({ ...prev, name: event.target.value }))} placeholder="Agent name" className="rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]" />
              <input value={draft.version} onChange={(event) => setDraft((prev) => ({ ...prev, version: event.target.value }))} placeholder="Version" className="rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]" />
              <input value={draft.author} onChange={(event) => setDraft((prev) => ({ ...prev, author: event.target.value }))} placeholder="Author" className="rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]" />
              <input value={draft.description} onChange={(event) => setDraft((prev) => ({ ...prev, description: event.target.value }))} placeholder="Description" className="rounded-xl border border-black/[0.12] px-3 py-2 text-[13px] md:col-span-2" />
              <input value={draft.tags} onChange={(event) => setDraft((prev) => ({ ...prev, tags: event.target.value }))} placeholder="Tags (comma-separated)" className="rounded-xl border border-black/[0.12] px-3 py-2 text-[13px] md:col-span-2" />
            </div>

            <textarea value={draft.systemPrompt} onChange={(event) => setDraft((prev) => ({ ...prev, systemPrompt: event.target.value }))} rows={8} placeholder="System prompt" className="mt-3 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]" />
            <p className="mt-1 text-[11px] text-[#98a2b3]">{draft.systemPrompt.length}/32000 chars</p>

            <div className="mt-3 rounded-xl border border-black/[0.08] bg-[#fcfcfd] p-3">
              <p className="text-[12px] font-semibold text-[#667085]">Required connectors</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {catalog.map((connector) => {
                  const connectorId = String(connector.id || "");
                  const selected = draft.requiredConnectors.includes(connectorId);
                  return (
                    <button
                      key={connectorId}
                      type="button"
                      onClick={() =>
                        setDraft((prev) => ({
                          ...prev,
                          requiredConnectors: selected
                            ? prev.requiredConnectors.filter((entry) => entry !== connectorId)
                            : [...prev.requiredConnectors, connectorId],
                        }))
                      }
                      className={`rounded-full border px-2.5 py-1 text-[12px] font-semibold ${selected ? "border-[#111827] bg-[#111827] text-white" : "border-black/[0.12] bg-white text-[#344054]"}`}
                    >
                      {titleCase(connectorId)}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="mt-3 rounded-xl border border-black/[0.08] bg-[#fcfcfd] p-3">
              <p className="text-[12px] font-semibold text-[#667085]">Tools</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {draft.requiredConnectors.flatMap((connectorId) => toolsByConnector.get(connectorId) || []).map((tool) => {
                  const selected = draft.tools.includes(tool.id);
                  return (
                    <button
                      key={tool.id}
                      type="button"
                      onClick={() =>
                        setDraft((prev) => ({
                          ...prev,
                          tools: selected ? prev.tools.filter((entry) => entry !== tool.id) : [...prev.tools, tool.id],
                        }))
                      }
                      className={`rounded-full border px-2 py-0.5 text-[11px] ${selected ? "border-[#111827] bg-[#111827] text-white" : "border-black/[0.12] bg-white text-[#475467]"}`}
                    >
                      {tool.label || tool.id}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
              <select value={draft.triggerFamily} onChange={(event) => setDraft((prev) => ({ ...prev, triggerFamily: event.target.value as TriggerFamily }))} className="rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]">
                <option value="manual">Manual</option>
                <option value="scheduled">Scheduled</option>
                <option value="on_event">On event</option>
              </select>
              <select value={draft.pricing} onChange={(event) => setDraft((prev) => ({ ...prev, pricing: event.target.value as Draft["pricing"] }))} className="rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]">
                <option value="free">Free</option>
                <option value="paid">Paid</option>
                <option value="enterprise">Enterprise</option>
              </select>
              <input value={draft.changelog} onChange={(event) => setDraft((prev) => ({ ...prev, changelog: event.target.value }))} placeholder="Changelog" className="rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]" />
            </div>

            {draft.triggerFamily === "scheduled" ? (
              <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
                <input value={draft.cron} onChange={(event) => setDraft((prev) => ({ ...prev, cron: event.target.value }))} placeholder="Cron expression" className="rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]" />
                <input value={draft.timezone} onChange={(event) => setDraft((prev) => ({ ...prev, timezone: event.target.value }))} placeholder="Timezone" className="rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]" />
              </div>
            ) : null}
            {draft.triggerFamily === "on_event" ? (
              <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
                <input value={draft.eventType} onChange={(event) => setDraft((prev) => ({ ...prev, eventType: event.target.value }))} placeholder="Event type" className="rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]" />
                <input value={draft.sourceConnector} onChange={(event) => setDraft((prev) => ({ ...prev, sourceConnector: event.target.value }))} placeholder="Source connector" className="rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]" />
              </div>
            ) : null}

            <div className="mt-4 flex flex-wrap gap-2">
              <button type="button" disabled={publishing || draftInvalid} onClick={() => void createOrRevise()} className="rounded-full bg-[#111827] px-4 py-2 text-[12px] font-semibold text-white disabled:opacity-60">
                {publishing ? "Saving..." : editingRejectedAgentId ? "Revise draft" : "Create draft"}
              </button>
              <button type="button" disabled={publishing || !selectedAgentId} onClick={() => void submitForReview()} className="rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[12px] font-semibold text-[#344054] disabled:opacity-60">
                Submit for review
              </button>
            </div>
            {selectedAgentId ? <p className="mt-2 text-[12px] text-[#667085]">Current draft: {selectedAgentId} ({selectedStatus || "draft"})</p> : null}
          </section>
        ) : null}

        {tab === "guide" ? (
          <section className="space-y-3 rounded-2xl border border-black/[0.08] bg-white p-4">
            <h2 className="text-[18px] font-semibold text-[#111827]">Developer guidelines</h2>
            <ul className="list-disc space-y-1 pl-5 text-[13px] text-[#475467]">
              <li>Do not include credentials, secrets, or private URLs in definitions.</li>
              <li>Declare only required connectors and tools with clear user-facing purpose.</li>
              <li>Add changelog notes for every version update before submission.</li>
              <li>Use safe triggers, explicit gate policies, and deterministic prompt behavior.</li>
            </ul>
          </section>
        ) : null}
      </div>
    </div>
  );
}
