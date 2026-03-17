import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import {
  getConnectorBinding,
  getAgent,
  getImprovementSuggestion,
  listConnectorHealth,
  listAgentRuns,
  patchConnectorBinding,
  recordFeedback,
  subscribeAgentEvents,
  updateAgent,
  type AgentLiveEvent,
  type AgentDefinitionInput,
  type AgentDefinitionRecord,
  type ImprovementSuggestionRecord,
} from "../../api/client";
import {
  MultiAgentTheatre,
  type MultiAgentColumn,
  type MultiAgentEvent,
} from "../components/agentActivityPanel/MultiAgentTheatre";
import { AgentRunHistory, type AgentRunHistoryRecord } from "../components/agents/AgentRunHistory";
import { InstallHistoryTab } from "../components/agents/InstallHistoryTab";
import { ImprovementSuggestion } from "../components/agents/ImprovementSuggestion";
import { PageMonitorPanel } from "../components/agents/PageMonitorPanel";
import { openConnectorOverlay } from "../utils/connectorOverlay";

type AgentDetailPageProps = {
  agentId: string;
  initialTab?: AgentDetailTab;
};

type AgentDetailTab = "overview" | "history" | "improvement" | "monitor";

// Helpers

function hasPageMonitorCapability(agent: AgentDefinitionRecord | null): boolean {
  if (!agent) return false;
  const agentId = String(agent.agent_id || "").trim().toLowerCase();
  if (agentId === "competitor-change-radar") return true;
  const definition = (agent.definition || {}) as Record<string, unknown>;
  const tools = Array.isArray(definition.tools) ? definition.tools : [];
  if (tools.some((t) => /page[_-]?monitor|monitor[_-]?page|competitor[_-]?page/i.test(String(t || "")))) return true;
  const tags = Array.isArray(definition.tags) ? definition.tags : [];
  return tags.some((t) => /page[_-]?monitor|competitor/i.test(String(t || "")));
}

function normalizeConnectorId(value: unknown): string {
  return String(value || "").trim().toLowerCase();
}

function inferRequiredConnectors(definition: Record<string, unknown>): string[] {
  const explicit = Array.isArray(definition.required_connectors)
    ? definition.required_connectors.map((e) => normalizeConnectorId(e)).filter(Boolean)
    : [];
  if (explicit.length > 0) return Array.from(new Set(explicit));
  const tools = Array.isArray(definition.tools) ? definition.tools : [];
  const derived = tools
    .map((e) => String(e || "").trim().toLowerCase())
    .filter(Boolean)
    .map((id) => id.split(".")[0])
    .map((prefix) => {
      if (["gmail", "gcalendar", "gdrive", "ga4"].includes(prefix)) return "google_workspace";
      return prefix;
    })
    .filter((p) => p && !["http", "browser", "canvas", "workspace"].includes(p));
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

/** Convert a cron expression to a plain-English string for common patterns. */
function describeCron(expr: string): string {
  const parts = String(expr || "").trim().split(/\s+/);
  if (parts.length !== 5) return expr;
  const [minute, hour, , , dow] = parts;
  const h = parseInt(hour, 10);
  const m = parseInt(minute, 10);
  if (!Number.isFinite(h) || !Number.isFinite(m)) return expr;
  const timeStr = `${h % 12 === 0 ? 12 : h % 12}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
  if (dow === "1-5" || dow === "1,2,3,4,5") return `Weekdays at ${timeStr}`;
  if (dow === "*") return `Daily at ${timeStr}`;
  const dayNames = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  const dayIndex = parseInt(dow, 10);
  if (Number.isFinite(dayIndex) && dayNames[dayIndex]) return `${dayNames[dayIndex]}s at ${timeStr}`;
  return expr;
}

function formatRelativeTime(isoString: string | null | undefined): string {
  if (!isoString) return "Never";
  const ms = Date.now() - new Date(isoString).getTime();
  if (ms < 0) return "Just now";
  const minutes = Math.floor(ms / 60000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function normalizeLiveEventType(event: AgentLiveEvent): string {
  const explicitRoot = String(
    (event as unknown as { event_type?: string }).event_type || "",
  )
    .trim()
    .toLowerCase();
  const fallbackType = String(event.type || "").trim().toLowerCase();
  const data = (event.data || {}) as Record<string, unknown>;
  const explicitType = String(data.event_type || "").trim().toLowerCase();
  return explicitType || explicitRoot || fallbackType || "event";
}

function resolveLiveEventStatus(event: AgentLiveEvent): string {
  const data = (event.data || {}) as Record<string, unknown>;
  return String(
    data.status || (event as unknown as { status?: string }).status || "",
  )
    .trim()
    .toLowerCase();
}

function resolveLiveAgentIdentity(
  event: AgentLiveEvent,
  fallbackAgentId: string,
  fallbackAgentName: string,
): { agentId: string; agentName: string; skillId?: string; skillName?: string } {
  const data = (event.data || {}) as Record<string, unknown>;
  const agentIdCandidate = [
    data.agent_id,
    data.child_agent_id,
    data.target_agent_id,
    data.owner_agent_id,
    (event as unknown as { agent_id?: string }).agent_id,
  ]
    .map((value) => String(value || "").trim())
    .find(Boolean);
  const agentNameCandidate = [
    data.agent_name,
    data.agent_label,
    data.child_agent_name,
    data.target_agent_name,
    data.owner_agent_name,
  ]
    .map((value) => String(value || "").trim())
    .find(Boolean);
  const skillId = String(data.skill_id || "").trim();
  const skillName = String(data.skill_name || "").trim();
  return {
    agentId: agentIdCandidate || fallbackAgentId,
    agentName: agentNameCandidate || fallbackAgentName || fallbackAgentId,
    skillId: skillId || undefined,
    skillName: skillName || undefined,
  };
}

function resolveLiveEventText(event: AgentLiveEvent, eventType: string): string {
  const data = (event.data || {}) as Record<string, unknown>;
  const title = String((event as unknown as { title?: string }).title || data.title || "").trim();
  const detail = String(
    (event as unknown as { detail?: string }).detail || data.detail || event.message || "",
  ).trim();
  if (title && detail) {
    return `${title}: ${detail}`;
  }
  if (title) {
    return title;
  }
  if (detail) {
    return detail;
  }
  return eventType.replace(/[_-]+/g, " ");
}

function resolveLiveEventTone(eventType: string, status: string): MultiAgentEvent["type"] {
  if (eventType.includes("error") || eventType.includes("failed") || status === "failed") {
    return "error";
  }
  if (
    eventType.includes("skipped") ||
    eventType.includes("budget") ||
    eventType.includes("blocked") ||
    status === "blocked"
  ) {
    return "warning";
  }
  return "info";
}

function resolveNextColumnStatus(
  previous: MultiAgentColumn["status"],
  eventType: string,
  status: string,
): MultiAgentColumn["status"] {
  if (eventType.includes("error") || eventType.includes("failed") || eventType.includes("budget")) {
    return "blocked";
  }
  if (status === "failed" || status === "blocked") {
    return "blocked";
  }
  if (eventType.includes("completed") || eventType === "run_completed") {
    return "done";
  }
  if (status === "completed") {
    return "done";
  }
  if (eventType.includes("started") || status === "running") {
    return "running";
  }
  return previous;
}

function applyLiveEventToColumns(
  previousColumns: MultiAgentColumn[],
  event: AgentLiveEvent,
  fallbackAgentId: string,
  fallbackAgentName: string,
): MultiAgentColumn[] {
  const eventType = normalizeLiveEventType(event);
  const status = resolveLiveEventStatus(event);
  const identity = resolveLiveAgentIdentity(event, fallbackAgentId, fallbackAgentName);
  const text = resolveLiveEventText(event, eventType);
  const tone = resolveLiveEventTone(eventType, status);
  const nextEvent: MultiAgentEvent = {
    text,
    type: tone,
  };

  const nextColumns = [...previousColumns];
  const existingIndex = nextColumns.findIndex((column) => column.agentId === identity.agentId);
  if (existingIndex >= 0) {
    const current = nextColumns[existingIndex];
    const nextStatus = resolveNextColumnStatus(current.status, eventType, status);
    nextColumns[existingIndex] = {
      ...current,
      agentName: identity.agentName || current.agentName,
      skillId: identity.skillId || current.skillId,
      skillName: identity.skillName || current.skillName,
      status: nextStatus,
      events: [...current.events, nextEvent].slice(-120),
    };
  } else {
    nextColumns.push({
      agentId: identity.agentId,
      agentName: identity.agentName,
      skillId: identity.skillId,
      skillName: identity.skillName,
      status: resolveNextColumnStatus("pending", eventType, status),
      events: [nextEvent],
    });
  }

  if (eventType === "run_completed") {
    return nextColumns.map((column) =>
      column.status === "running" || column.status === "pending"
        ? { ...column, status: "done" }
        : column,
    );
  }

  if (eventType === "run_failed" || eventType === "error" || eventType === "budget_exceeded") {
    return nextColumns.map((column) =>
      column.status === "running" ? { ...column, status: "blocked" } : column,
    );
  }

  return nextColumns;
}

// Sub-components

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    active: "bg-[#d1fae5] text-[#065f46]",
    scheduled: "bg-[#ede9fe] text-[#5b21b6]",
    paused: "bg-[#fef3c7] text-[#92400e]",
    error: "bg-[#fee2e2] text-[#991b1b]",
  };
  const label: Record<string, string> = {
    active: "Active",
    scheduled: "Scheduled",
    paused: "Paused",
    error: "Error",
  };
  const key = status.toLowerCase();
  const cls = styles[key] || "bg-[#f3f4f6] text-[#374151]";
  return (
    <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${cls}`}>
      {label[key] || status}
    </span>
  );
}

function ConnectorChip({ connectorId, healthy }: { connectorId: string; healthy: boolean | null }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[12px] font-medium ${
        healthy === false
          ? "bg-[#fee2e2] text-[#991b1b]"
          : "bg-[#f5f3ff] text-[#6d28d9]"
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${healthy === false ? "bg-[#dc2626]" : "bg-[#8b5cf6]"}`} />
      {connectorId}
    </span>
  );
}

// Main component

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
  const [unhealthyConnectorIds, setUnhealthyConnectorIds] = useState<string[]>([]);
  const [connectorAccessError, setConnectorAccessError] = useState("");
  const [savingConnectorId, setSavingConnectorId] = useState("");
  const [liveColumns, setLiveColumns] = useState<MultiAgentColumn[]>([]);
  const [liveLoading, setLiveLoading] = useState(false);
  const [liveStreamError, setLiveStreamError] = useState("");

  useEffect(() => { setActiveTab(initialTab); }, [initialTab, agentId]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const [agent, runRows] = await Promise.all([getAgent(agentId), listAgentRuns(agentId)]);
        setAgentDetail(agent);
        setRuns((runRows || []).map(mapRunToUi));
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [agentId]);

  useEffect(() => {
    if (activeTab !== "improvement" || suggestionDismissed) return;
    let cancelled = false;
    const load = async () => {
      setSuggestionLoading(true);
      setSuggestionError("");
      try {
        const row = await getImprovementSuggestion(agentId);
        if (!cancelled) setSuggestion(row);
      } catch (e) {
        if (!cancelled) { setSuggestion(null); setSuggestionError(String(e || "No suggestion available yet.")); }
      } finally {
        if (!cancelled) setSuggestionLoading(false);
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [activeTab, agentId, suggestionDismissed, suggestionRefreshNonce]);

  const requiredConnectors = useMemo(
    () => inferRequiredConnectors((agentDetail?.definition || {}) as Record<string, unknown>),
    [agentDetail?.definition],
  );
  const monitorEnabled = useMemo(() => hasPageMonitorCapability(agentDetail), [agentDetail]);

  useEffect(() => {
    if (activeTab === "monitor" && !monitorEnabled) setActiveTab("overview");
  }, [activeTab, monitorEnabled]);

  useEffect(() => {
    if (!agentDetail || requiredConnectors.length === 0) {
      setConnectorAccessMap({}); setConnectorAllowedAgentMap({}); setConnectorAccessError(""); return;
    }
    let cancelled = false;
    const load = async () => {
      setConnectorAccessError("");
      try {
        const rows = await Promise.all(
          requiredConnectors.map(async (cid) => {
            try {
              const b = await getConnectorBinding(cid);
              const allowed = Array.isArray(b.allowed_agent_ids)
                ? b.allowed_agent_ids.map((e) => String(e || "").trim()).filter(Boolean)
                : [];
              return [cid, allowed] as const;
            } catch { return [cid, []] as const; }
          }),
        );
        if (cancelled) return;
        const nextAllowed: Record<string, string[]> = {};
        const nextAccess: Record<string, boolean> = {};
        for (const [cid, allowedIds] of rows) {
          nextAllowed[cid] = allowedIds as string[];
          nextAccess[cid] = (allowedIds as string[]).includes(agentDetail.agent_id);
        }
        setConnectorAllowedAgentMap(nextAllowed);
        setConnectorAccessMap(nextAccess);
      } catch (e) {
        if (!cancelled) setConnectorAccessError(String(e || "Failed to load connector permissions."));
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [agentDetail, requiredConnectors]);

  useEffect(() => {
    if (!agentDetail || requiredConnectors.length === 0) { setUnhealthyConnectorIds([]); return; }
    let cancelled = false;
    const load = async () => {
      try {
        const rows = await listConnectorHealth();
        if (cancelled) return;
        const healthMap = new Map<string, boolean>();
        for (const row of rows || []) {
          const cid = normalizeConnectorId((row as { connector_id?: string })?.connector_id || "");
          if (cid) healthMap.set(cid, Boolean((row as { ok?: boolean })?.ok));
        }
        setUnhealthyConnectorIds(requiredConnectors.filter((cid) => !healthMap.get(normalizeConnectorId(cid))));
      } catch { /* keep page usable */ }
    };
    void load();
    return () => { cancelled = true; };
  }, [agentDetail, requiredConnectors]);

  // Derived display values

  const definition = useMemo(
    () => (agentDetail?.definition || {}) as Record<string, unknown>,
    [agentDetail?.definition],
  );

  const agentDescription = String(definition.description || "").trim();
  const agentTags = Array.isArray(definition.tags) ? definition.tags.map(String) : [];
  const trigger = definition.trigger as { family?: string; cron_expression?: string } | undefined;
  const isScheduled = trigger?.family === "scheduled";
  const cronDescription = isScheduled && trigger?.cron_expression
    ? describeCron(trigger.cron_expression)
    : null;

  const lastRun = runs[0] || null;
  const agentStatus = lastRun?.status === "failed" ? "error" : isScheduled ? "scheduled" : "active";

  const tabs = useMemo(
    () => (["overview", "history", "improvement", ...(monitorEnabled ? (["monitor"] as const) : [])] as const),
    [monitorEnabled],
  );

  useEffect(() => {
    if (activeTab !== "overview" || !lastRun?.runId || !agentDetail?.agent_id) {
      setLiveColumns([]);
      setLiveLoading(false);
      setLiveStreamError("");
      return;
    }
    const fallbackId = String(agentDetail.agent_id || "").trim();
    const fallbackName = String(agentDetail.name || fallbackId || "Agent").trim();
    const baseColumn: MultiAgentColumn = {
      agentId: fallbackId || "agent",
      agentName: fallbackName,
      status: lastRun.status === "running" ? "running" : "pending",
      events: [],
    };
    setLiveColumns([baseColumn]);
    setLiveLoading(true);
    setLiveStreamError("");
    const unsubscribe = subscribeAgentEvents({
      runId: lastRun.runId,
      replay: lastRun.status === "running" ? 0 : 120,
      onReady: () => {
        setLiveLoading(false);
      },
      onEvent: (event) => {
        setLiveColumns((previous) =>
          applyLiveEventToColumns(previous, event, fallbackId, fallbackName),
        );
      },
      onError: () => {
        setLiveLoading(false);
        setLiveStreamError("Live stream disconnected.");
      },
    });
    return () => {
      unsubscribe();
    };
  }, [activeTab, agentDetail?.agent_id, agentDetail?.name, lastRun?.runId, lastRun?.status]);

  // Navigate to chat

  const openInChat = () => {
    const targetAgentId = String(agentDetail?.agent_id || agentId || "").trim();
    const nextPath = targetAgentId ? "/?agent=" + encodeURIComponent(targetAgentId) : "/";
    window.history.pushState({}, "", nextPath);
    window.dispatchEvent(new PopStateEvent("popstate"));
    toast.success("Opening chat with " + (agentDetail?.name || "the agent") + ".");
  };

  const openConnectorSettings = (connectorId?: string) => {
    openConnectorOverlay(connectorId, { fromPath: window.location.pathname });
  };

  // Loading / error states

  if (loading) {
    return (
      <div className="h-full overflow-y-auto bg-[#f6f6f7] p-5">
        <div className="mx-auto max-w-[1080px] rounded-2xl border border-black/[0.08] bg-white p-5 text-[14px] text-[#667085]">
          Loading agent...
        </div>
      </div>
    );
  }

  if (error || !agentDetail) {
    return (
      <div className="h-full overflow-y-auto bg-[#f6f6f7] p-5">
        <div className="mx-auto max-w-[1080px] rounded-2xl border border-[#fecaca] bg-[#fff1f2] p-5">
          <h1 className="text-[24px] font-semibold text-[#9f1239]">Agent not found</h1>
          <p className="mt-2 text-[13px] text-[#b42318]">{error || "No agent data returned."}</p>
        </div>
      </div>
    );
  }

  // Render

  return (
    <div className="h-full overflow-y-auto bg-[#f6f6f7] p-5">
      <div className="mx-auto max-w-[1240px] space-y-4">

        {/* Header card */}
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5 shadow-[0_20px_54px_rgba(15,23,42,0.1)]">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">
                  Agent
                </p>
                <StatusBadge status={agentStatus} />
                {cronDescription ? (
                  <span className="text-[12px] text-[#667085]">- {cronDescription}</span>
                ) : null}
              </div>
              <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">
                {agentDetail.name}
              </h1>
              {agentDescription ? (
                <p className="mt-2 max-w-[640px] text-[14px] leading-relaxed text-[#475467]">
                  {agentDescription}
                </p>
              ) : null}
              {agentTags.length > 0 ? (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {agentTags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full bg-[#f3f4f6] px-2.5 py-0.5 text-[11px] font-medium text-[#374151]"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>

            {/* Primary CTA */}
            <div className="flex shrink-0 flex-col items-end gap-2">
              <button
                type="button"
                onClick={openInChat}
                className="rounded-full bg-[#7c3aed] px-4 py-2 text-[13px] font-semibold text-white hover:bg-[#6d28d9] active:scale-[0.97] transition-all"
              >
                Chat with this agent
              </button>
              <a
                href={`/agents/${agentId}/edit`}
                className="rounded-full border border-black/[0.12] bg-white px-3 py-1.5 text-[12px] font-medium text-[#667085] hover:text-[#111827] transition-colors"
              >
                Edit
              </a>
            </div>
          </div>

          {/* Tab bar */}
          <div className="mt-4 flex gap-2">
            {tabs.map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setActiveTab(tab)}
                className={`rounded-full px-3 py-1.5 text-[12px] font-semibold capitalize transition-colors ${
                  activeTab === tab
                    ? "bg-[#7c3aed] text-white shadow-[0_1px_3px_rgba(124,58,237,0.3)]"
                    : "border border-black/[0.08] bg-white text-[#344054] hover:bg-[#f5f3ff] hover:text-[#7c3aed]"
                }`}
              >
                {tab}
              </button>
            ))}
          </div>

          {/* Unhealthy connector warning */}
          {unhealthyConnectorIds.length > 0 ? (
            <div className="mt-3 rounded-xl border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-[12px] text-[#9f1239]">
              Connector attention needed: {unhealthyConnectorIds.join(", ")}.{" "}
              <button
                type="button"
                onClick={() => openConnectorSettings(unhealthyConnectorIds[0])}
                className="font-semibold underline"
              >
                Configure connectors
              </button>
            </div>
          ) : null}
        </section>

        {/* Overview tab */}
        {activeTab === "overview" ? (
          <div className="space-y-4">

            {/* Last run summary */}
            <section className="rounded-2xl border border-black/[0.08] bg-white p-5">
              <h2 className="text-[16px] font-semibold text-[#111827]">Last run</h2>
              {lastRun ? (
                <div className="mt-3 space-y-3">
                  <div className="flex flex-wrap items-center gap-3 text-[13px] text-[#667085]">
                    <span
                      className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                        lastRun.status === "completed"
                          ? "bg-[#d1fae5] text-[#065f46]"
                          : lastRun.status === "failed"
                            ? "bg-[#fee2e2] text-[#991b1b]"
                            : "bg-[#f3f4f6] text-[#374151]"
                      }`}
                    >
                      {lastRun.status}
                    </span>
                    <span>{formatRelativeTime(lastRun.startedAt)}</span>
                    <span className="capitalize text-[#9ca3af]">{lastRun.triggerType}</span>
                  </div>
                  {lastRun.outputSummary && lastRun.outputSummary !== "No summary available." ? (
                    <p className="rounded-xl bg-[#f8fafc] border border-black/[0.06] p-3 text-[13px] leading-relaxed text-[#374151]">
                      {lastRun.outputSummary}
                    </p>
                  ) : (
                    <p className="text-[13px] text-[#9ca3af]">No output summary for this run.</p>
                  )}
                  <button
                    type="button"
                    onClick={() => setActiveTab("history")}
                    className="text-[12px] font-medium text-[#667085] underline hover:text-[#111827]"
                  >
                    View full run history
                  </button>
                </div>
              ) : (
                <div className="mt-3 rounded-xl border border-dashed border-black/[0.1] bg-[#f9fafb] p-4 text-center">
                  <p className="text-[13px] text-[#9ca3af]">This agent hasn't run yet.</p>
                  {isScheduled && cronDescription ? (
                    <p className="mt-1 text-[12px] text-[#c4c9d4]">
                      Scheduled to run - {cronDescription}
                    </p>
                  ) : (
                    <button
                      type="button"
                      onClick={openInChat}
                      className="mt-2 text-[12px] font-medium text-[#667085] underline hover:text-[#111827]"
                    >
                      Start a conversation to trigger it
                    </button>
                  )}
                </div>
              )}
            </section>

            {lastRun ? (
              <section className="rounded-2xl border border-black/[0.08] bg-white p-5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="text-[16px] font-semibold text-[#111827]">Live theatre</h2>
                  <p className="text-[12px] text-[#667085]">
                    {lastRun.status === "running" ? "Streaming now" : "Replay of latest run"}
                  </p>
                </div>
                {liveLoading ? (
                  <p className="mt-3 text-[12px] text-[#667085]">Connecting to live stream...</p>
                ) : null}
                {liveStreamError ? (
                  <p className="mt-3 rounded-xl border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-[12px] text-[#9f1239]">
                    {liveStreamError}
                  </p>
                ) : null}
                {liveColumns.some((column) => column.events.length > 0) ? (
                  <div className="mt-3">
                    <MultiAgentTheatre columns={liveColumns} />
                  </div>
                ) : (
                  <p className="mt-3 rounded-xl border border-dashed border-black/[0.12] bg-[#f8fafc] px-3 py-2 text-[12px] text-[#667085]">
                    No streamed events yet for this run.
                  </p>
                )}
              </section>
            ) : null}

            {/* Connectors */}
            {requiredConnectors.length > 0 ? (
              <section className="rounded-2xl border border-black/[0.08] bg-white p-5">
                <div className="flex items-center justify-between">
                  <h2 className="text-[16px] font-semibold text-[#111827]">Integrations</h2>
                  <button
                    type="button"
                    onClick={() => openConnectorSettings(requiredConnectors[0])}
                    className="text-[12px] font-medium text-[#667085] hover:text-[#111827]"
                  >
                    Manage connectors
                  </button>
                </div>
                <p className="mt-1 text-[13px] text-[#667085]">
                  This agent uses these integrations. Toggle access on or off per connector.
                </p>
                {connectorAccessError ? (
                  <p className="mt-3 rounded-xl border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-[12px] text-[#9f1239]">
                    {connectorAccessError}
                  </p>
                ) : null}
                <div className="mt-3 space-y-2">
                  {requiredConnectors.map((cid) => {
                    const checked = Boolean(connectorAccessMap[cid]);
                    const saving = savingConnectorId === cid;
                    const healthy = !unhealthyConnectorIds.includes(cid);
                    return (
                      <label
                        key={cid}
                        className="flex cursor-pointer items-center justify-between gap-3 rounded-xl border border-black/[0.08] bg-[#f8fafc] px-4 py-3 hover:bg-[#f1f5f9] transition-colors"
                      >
                        <div className="flex items-center gap-2">
                          <ConnectorChip connectorId={cid} healthy={healthy ? true : false} />
                          <span className="text-[13px] text-[#667085]">
                            {checked ? "Access granted" : "Access blocked"}
                          </span>
                        </div>
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={saving}
                          onChange={async (e) => {
                            const allow = e.target.checked;
                            const existing = Array.isArray(connectorAllowedAgentMap[cid])
                              ? connectorAllowedAgentMap[cid]
                              : [];
                            const next = allow
                              ? Array.from(new Set([...existing, agentDetail.agent_id]))
                              : existing.filter((id) => id !== agentDetail.agent_id);
                            setSavingConnectorId(cid);
                            setConnectorAccessError("");
                            try {
                              await patchConnectorBinding(cid, { allowed_agent_ids: next });
                              setConnectorAllowedAgentMap((prev) => ({ ...prev, [cid]: next }));
                              setConnectorAccessMap((prev) => ({ ...prev, [cid]: allow }));
                              toast.success(`${cid} access ${allow ? "granted" : "revoked"}.`);
                            } catch (ex) {
                              setConnectorAccessError(`Failed to update ${cid}: ${String(ex || "Unknown error")}`);
                            } finally {
                              setSavingConnectorId("");
                            }
                          }}
                          className="h-4 w-4 cursor-pointer rounded border border-black/[0.2]"
                        />
                      </label>
                    );
                  })}
                </div>
              </section>
            ) : null}

            {/* Schedule info */}
            {isScheduled ? (
              <section className="rounded-2xl border border-black/[0.08] bg-white p-5">
                <h2 className="text-[16px] font-semibold text-[#111827]">Schedule</h2>
                <div className="mt-3 flex flex-wrap gap-4 text-[13px] text-[#667085]">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-[#9ca3af]">Frequency</p>
                    <p className="mt-0.5 font-medium text-[#111827]">{cronDescription || trigger?.cron_expression}</p>
                  </div>
                  {lastRun ? (
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-[#9ca3af]">Last ran</p>
                      <p className="mt-0.5 font-medium text-[#111827]">{formatRelativeTime(lastRun.startedAt)}</p>
                    </div>
                  ) : null}
                </div>
                <p className="mt-3 text-[12px] text-[#9ca3af]">
                  Runs automatically. Results appear in your run history and chat when you ask.
                </p>
              </section>
            ) : null}
          </div>
        ) : null}

                {/* History tab */}
        {activeTab === "history" ? (
          <div className="space-y-4">
            <InstallHistoryTab agentId={agentId} />
            <AgentRunHistory
              runs={runs}
              onOpenReplay={(runId) => toast.message(`Opening replay for ${runId}`)}
              onSubmitFeedback={async ({ runId, feedbackType, originalOutput, correctedOutput }) => {
                await recordFeedback(agentId, runId, originalOutput, correctedOutput, feedbackType);
                toast.success("Feedback saved.");
              }}
            />
          </div>
        ) : null}

        {/* Improvement tab */}
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
                const current = (agentDetail.definition || {}) as Record<string, unknown>;
                const payload: AgentDefinitionInput = {
                  ...(current as AgentDefinitionInput),
                  id: String(current.id || agentDetail.agent_id || ""),
                  name: String(current.name || agentDetail.name || agentDetail.agent_id),
                  system_prompt: suggestion.suggested_prompt,
                };
                await updateAgent(agentId, payload);
                const refreshed = await getAgent(agentId);
                setAgentDetail(refreshed);
                toast.success("Improvement applied.");
              } catch (ex) {
                toast.error(`Failed to apply: ${String(ex)}`);
              } finally {
                setApplyingSuggestion(false);
              }
            }}
            onRefresh={() => {
              setSuggestionDismissed(false);
              setSuggestion(null);
              setSuggestionError("");
              setSuggestionRefreshNonce((n) => n + 1);
            }}
            onDismiss={() => {
              setSuggestionDismissed(true);
              setSuggestion(null);
              setSuggestionError("");
            }}
          />
        ) : null}

        {/* Monitor tab */}
        {activeTab === "monitor" && monitorEnabled ? (
          <PageMonitorPanel agentId={agentDetail.agent_id} />
        ) : null}
      </div>
    </div>
  );
}




