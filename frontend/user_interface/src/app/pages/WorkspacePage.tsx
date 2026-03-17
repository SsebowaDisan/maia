import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  applyMarketplaceUpdate,
  checkMarketplaceUpdates,
  getAgent,
  listAgentRuns,
  listAgents,
  listConnectorCatalog,
  listConnectorCredentials,
  listConnectorHealth,
  type AgentRunRecord,
  type MarketplaceAgentUpdateRecord,
} from "../../api/client";

import { AgentRunHistory, type AgentRunHistoryRecord } from "../components/agents/AgentRunHistory";
import { MemoryExplorer } from "../components/agents/MemoryExplorer";
import { WorkspaceSidebar } from "../components/workspace/WorkspaceSidebar";
import { UpdateBanner } from "../components/workspace/UpdateBanner";
import { openConnectorOverlay } from "../utils/connectorOverlay";

type WorkspaceAgentCard = {
  id: string;
  name: string;
  description: string;
  status: "active" | "paused" | "error";
  lastRun: string;
  totalRuns: number;
  runs: AgentRunHistoryRecord[];
  requiredConnectors: string[];
  unhealthyConnectors: string[];
  scheduleLabel?: string;
  nextRunAt?: string | null;
};

type WorkspaceConnectorCard = {
  id: string;
  name: string;
  description: string;
  authType: string;
  status: "Connected" | "Not connected" | "Expired";
};

type ConnectorHealthEntry = {
  ok: boolean;
  message: string;
};

function formatRelativeTime(isoLike: string): string {
  const date = new Date(isoLike);
  if (Number.isNaN(date.getTime())) {
    return "Unknown";
  }
  const diffMs = Date.now() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) {
    return "just now";
  }
  if (diffMins < 60) {
    return `${diffMins}m ago`;
  }
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) {
    return `${diffHours}h ago`;
  }
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

function deriveDurationMs(startedAt: string, endedAt?: string | null): number {
  const start = new Date(startedAt).getTime();
  const end = endedAt ? new Date(endedAt).getTime() : Date.now();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) {
    return 0;
  }
  return end - start;
}

function inferAgentStatus(runs: AgentRunHistoryRecord[]): WorkspaceAgentCard["status"] {
  if (!runs.length) {
    return "paused";
  }
  const latest = String(runs[0]?.status || "").toLowerCase();
  if (latest === "failed" || latest === "error") {
    return "error";
  }
  return "active";
}

function normalizeRun(run: AgentRunRecord): AgentRunHistoryRecord {
  const startedAt = String(run.started_at || new Date().toISOString());
  const endedAt = run.ended_at || null;
  return {
    runId: String(run.run_id || ""),
    agentId: String(run.agent_id || ""),
    triggerType: String(run.trigger_type || "manual"),
    status: String(run.status || "unknown"),
    durationMs: deriveDurationMs(startedAt, endedAt),
    llmCostUsd: 0,
    startedAt,
    outputSummary: String(run.result_summary || ""),
    errorMessage: String(run.error || ""),
  };
}

function resolveConnectorStatus(
  authKind: string,
  health: ConnectorHealthEntry | null,
  hasCredential: boolean,
): "Connected" | "Not connected" | "Expired" {
  if (String(authKind || "").trim().toLowerCase() === "none") {
    return "Connected";
  }
  const message = String(health?.message || "").toLowerCase();
  if (health?.ok) {
    return "Connected";
  }
  if (hasCredential && /(expired|refresh|unauthorized|forbidden|invalid)/i.test(message)) {
    return "Expired";
  }
  return "Not connected";
}

function safeAuthKind(raw: unknown): string {
  const kind = String(raw || "").trim().toLowerCase();
  if (!kind) {
    return "none";
  }
  return kind;
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

function describeCronExpression(cronExpression: string): string {
  const parts = String(cronExpression || "").trim().split(/\s+/);
  if (parts.length < 5) {
    return "Custom schedule";
  }
  const [minuteRaw, hourRaw, dayOfMonth, month, dayOfWeek] = parts;
  const minute = Number(minuteRaw);
  const hour = Number(hourRaw);
  const hasFixedTime = Number.isFinite(minute) && Number.isFinite(hour);
  const timeText = hasFixedTime
    ? `${String(Math.max(0, Math.min(23, hour))).padStart(2, "0")}:${String(
        Math.max(0, Math.min(59, minute)),
      ).padStart(2, "0")}`
    : "scheduled time";
  const weekdayMap: Record<string, string> = {
    "0": "Sunday",
    "1": "Monday",
    "2": "Tuesday",
    "3": "Wednesday",
    "4": "Thursday",
    "5": "Friday",
    "6": "Saturday",
    "7": "Sunday",
  };
  if (dayOfMonth === "*" && month === "*" && dayOfWeek === "*") {
    return `Every day at ${timeText} UTC`;
  }
  if (dayOfMonth === "*" && month === "*" && weekdayMap[dayOfWeek]) {
    return `Every ${weekdayMap[dayOfWeek]} at ${timeText} UTC`;
  }
  return `Cron: ${cronExpression}`;
}

function getNextScheduledRun(cronExpression: string): Date | null {
  const parts = String(cronExpression || "").trim().split(/\s+/);
  if (parts.length < 5) {
    return null;
  }
  const [minuteRaw, hourRaw, dayOfMonth, month, dayOfWeek] = parts;
  if (dayOfMonth !== "*" || month !== "*") {
    return null;
  }
  if (!/^\d+$/.test(minuteRaw) || !/^\d+$/.test(hourRaw)) {
    return null;
  }
  const minute = Number(minuteRaw);
  const hour = Number(hourRaw);
  if (minute < 0 || minute > 59 || hour < 0 || hour > 23) {
    return null;
  }
  const now = new Date();
  const candidate = new Date(now);
  candidate.setUTCSeconds(0, 0);
  candidate.setUTCHours(hour, minute, 0, 0);
  if (dayOfWeek === "*") {
    if (candidate.getTime() <= now.getTime()) {
      candidate.setUTCDate(candidate.getUTCDate() + 1);
    }
    return candidate;
  }
  if (!/^\d+$/.test(dayOfWeek)) {
    return null;
  }
  const targetDay = Number(dayOfWeek) % 7;
  const currentDay = candidate.getUTCDay();
  let daysAhead = (targetDay - currentDay + 7) % 7;
  if (daysAhead === 0 && candidate.getTime() <= now.getTime()) {
    daysAhead = 7;
  }
  candidate.setUTCDate(candidate.getUTCDate() + daysAhead);
  return candidate;
}

export function WorkspacePage() {
  const [selectedConnectorId, setSelectedConnectorId] = useState<string | null>(null);
  const [bannerDismissed, setBannerDismissed] = useState(false);
  const [updatesLoading, setUpdatesLoading] = useState(false);
  const [updatesError, setUpdatesError] = useState("");
  const [updatesPanelOpen, setUpdatesPanelOpen] = useState(false);
  const [updates, setUpdates] = useState<MarketplaceAgentUpdateRecord[]>([]);
  const [updatingAgentIds, setUpdatingAgentIds] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [agentCards, setAgentCards] = useState<WorkspaceAgentCard[]>([]);
  const [allRuns, setAllRuns] = useState<AgentRunHistoryRecord[]>([]);
  const [connectorCards, setConnectorCards] = useState<WorkspaceConnectorCard[]>([]);

  const loadUpdates = async () => {
    setUpdatesLoading(true);
    setUpdatesError("");
    try {
      const rows = await checkMarketplaceUpdates();
      setUpdates(Array.isArray(rows) ? rows : []);
    } catch (error) {
      const message = String(error || "Failed to check marketplace updates.");
      setUpdatesError(message);
    } finally {
      setUpdatesLoading(false);
    }
  };

  const loadWorkspaceData = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const [agentRows, connectorCatalog, healthRows, credentialRows] = await Promise.all([
        listAgents(),
        listConnectorCatalog(),
        listConnectorHealth(),
        listConnectorCredentials(),
      ]);

      const healthMap: Record<string, ConnectorHealthEntry> = {};
      for (const row of healthRows) {
        const connectorId = String(row?.connector_id || "").trim();
        if (!connectorId) {
          continue;
        }
        healthMap[connectorId] = {
          ok: Boolean(row?.ok),
          message: String(row?.message || ""),
        };
      }

      const credentialSet = new Set(
        credentialRows
          .map((row) => String(row?.connector_id || "").trim())
          .filter(Boolean),
      );

      const connectors: WorkspaceConnectorCard[] = (connectorCatalog || [])
        .map((connector) => {
          const connectorId = String(connector.id || "").trim();
          return {
            id: connectorId,
            name: String(connector.name || connectorId),
            description: String(connector.description || ""),
            authType: safeAuthKind(connector.auth?.kind),
            status: resolveConnectorStatus(
              safeAuthKind(connector.auth?.kind),
              healthMap[connectorId] || null,
              credentialSet.has(connectorId),
            ),
          };
        })
        .filter((connector) => connector.id)
        .sort((left, right) => left.name.localeCompare(right.name));
      const connectorReadyMap = new Map<string, boolean>();
      for (const connector of connectors) {
        connectorReadyMap.set(
          normalizeConnectorId(connector.id),
          connector.status === "Connected",
        );
      }

      const agentCardRows = await Promise.all(
        (agentRows || []).map(async (agent) => {
          const [runsRaw, definition] = await Promise.all([
            listAgentRuns(agent.agent_id, { limit: 100 }),
            getAgent(agent.agent_id).catch(() => null),
          ]);
          const runs = (runsRaw || [])
            .map(normalizeRun)
            .sort(
              (left, right) =>
                new Date(right.startedAt).getTime() - new Date(left.startedAt).getTime(),
            );
          const rawDefinition = ((definition?.definition || {}) as Record<string, unknown>);
          const requiredConnectors = inferRequiredConnectors(rawDefinition);
          const unhealthyConnectors = requiredConnectors.filter(
            (connectorId) => !connectorReadyMap.get(normalizeConnectorId(connectorId)),
          );
          const trigger = (rawDefinition.trigger || {}) as Record<string, unknown>;
          const isScheduled = String(trigger.family || "").trim().toLowerCase() === "scheduled";
          const cronExpression = String(trigger.cron_expression || "").trim();
          const nextRunDate = isScheduled ? getNextScheduledRun(cronExpression) : null;
          return {
            id: agent.agent_id,
            name: agent.name,
            description: String(rawDefinition.description || "Agent definition ready."),
            status: inferAgentStatus(runs),
            lastRun: runs[0]?.startedAt || "",
            totalRuns: runs.length,
            runs,
            requiredConnectors,
            unhealthyConnectors,
            scheduleLabel: isScheduled ? describeCronExpression(cronExpression) : "",
            nextRunAt: nextRunDate ? nextRunDate.toISOString() : null,
          } satisfies WorkspaceAgentCard;
        }),
      );

      const mergedRuns = agentCardRows
        .flatMap((agent) => agent.runs)
        .sort(
          (left, right) =>
            new Date(right.startedAt).getTime() - new Date(left.startedAt).getTime(),
        );

      setConnectorCards(connectors);
      setAgentCards(agentCardRows);
      setAllRuns(mergedRuns);
    } catch (error) {
      setLoadError(`Failed to load workspace data: ${String(error)}`);
      setConnectorCards([]);
      setAgentCards([]);
      setAllRuns([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void Promise.all([loadWorkspaceData(), loadUpdates()]);
  }, [loadWorkspaceData]);

  const updatesAvailable = updates.length;
  const activeConnector = connectorCards.find((connector) => connector.id === selectedConnectorId) || null;
  const connectorHint = activeConnector
    ? `${activeConnector.name} selected from workspace sidebar.`
    : "Select a connector from the sidebar for quick context.";

  const runsByAgent = useMemo(
    () =>
      agentCards.map((agent) => ({
        agent,
        runs: agent.runs,
      })),
    [agentCards],
  );

  const episodes = useMemo(
    () =>
      allRuns
        .filter((run) => run.outputSummary)
        .slice(0, 20)
        .map((run) => ({
          id: run.runId,
          summary: run.outputSummary,
          createdAt: run.startedAt,
        })),
    [allRuns],
  );

  const workingMemory = useMemo(() => {
    const latest = allRuns[0];
    if (!latest) {
      return [];
    }
    return [
      { key: "run_id", value: latest.runId },
      { key: "agent_id", value: latest.agentId },
      { key: "trigger_type", value: latest.triggerType },
      { key: "status", value: latest.status },
    ];
  }, [allRuns]);

  return (
    <div className="h-full overflow-y-auto bg-[#f6f6f7] p-5">
      <div className="mx-auto flex max-w-[1360px] gap-4">
        <WorkspaceSidebar
          connectors={connectorCards}
          agents={agentCards.map((agent) => ({ id: agent.id, status: agent.status }))}
          onOpenConnector={setSelectedConnectorId}
        />

        <div className="min-w-0 flex-1 space-y-4">
          <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5 shadow-[0_20px_54px_rgba(15,23,42,0.1)]">
            <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">Workspace</p>
            <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">Agent operations dashboard</h1>
            <p className="mt-2 text-[15px] text-[#475467]">{connectorHint}</p>
          </section>

          {!bannerDismissed ? (
            <UpdateBanner
              totalUpdates={updatesAvailable}
              onOpenUpdates={() => setUpdatesPanelOpen(true)}
              onDismiss={() => setBannerDismissed(true)}
            />
          ) : null}

          {updatesPanelOpen ? (
            <section className="rounded-2xl border border-black/[0.08] bg-white p-4 shadow-[0_14px_36px_rgba(15,23,42,0.08)]">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-[16px] font-semibold text-[#111827]">Available agent updates</h2>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => void loadUpdates()}
                    disabled={updatesLoading}
                    className="rounded-full border border-black/[0.12] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#344054] disabled:opacity-50"
                  >
                    {updatesLoading ? "Refreshing..." : "Refresh"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setUpdatesPanelOpen(false)}
                    className="rounded-full border border-black/[0.12] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#344054]"
                  >
                    Close
                  </button>
                </div>
              </div>
              {updatesError ? (
                <p className="mt-3 rounded-xl border border-[#fca5a5] bg-[#fff1f2] px-3 py-2 text-[12px] text-[#9f1239]">
                  {updatesError}
                </p>
              ) : null}
              {!updatesError && updates.length === 0 ? (
                <p className="mt-3 text-[13px] text-[#667085]">Everything is up to date.</p>
              ) : null}
              {updates.length > 0 ? (
                <div className="mt-3 space-y-2">
                  {updates.map((update) => {
                    const isApplying = Boolean(updatingAgentIds[update.agent_id]);
                    return (
                      <article
                        key={`${update.agent_id}:${update.latest_version}`}
                        className="rounded-xl border border-black/[0.08] bg-[#f8fafc] px-3 py-2.5"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div>
                            <p className="text-[13px] font-semibold text-[#111827]">{update.agent_id}</p>
                            <p className="text-[12px] text-[#667085]">
                              {update.current_version} {"->"} {update.latest_version}
                            </p>
                          </div>
                          <button
                            type="button"
                            disabled={isApplying}
                            onClick={async () => {
                              setUpdatingAgentIds((previous) => ({
                                ...previous,
                                [update.agent_id]: true,
                              }));
                              try {
                                const result = await applyMarketplaceUpdate(
                                  update.agent_id,
                                  update.latest_version,
                                );
                                if (!result.success) {
                                  toast.error(result.error || "Update failed.");
                                  return;
                                }
                                toast.success(`${update.agent_id} updated to ${update.latest_version}.`);
                                await loadUpdates();
                              } catch (error) {
                                toast.error(`Update failed: ${String(error)}`);
                              } finally {
                                setUpdatingAgentIds((previous) => ({
                                  ...previous,
                                  [update.agent_id]: false,
                                }));
                              }
                            }}
                            className="rounded-full bg-[#7c3aed] hover:bg-[#6d28d9] transition-colors px-3 py-1.5 text-[12px] font-semibold text-white disabled:opacity-50"
                          >
                            {isApplying ? "Updating..." : "Update"}
                          </button>
                        </div>
                        <p className="mt-1 text-[12px] text-[#475467]">{update.changelog}</p>
                      </article>
                    );
                  })}
                </div>
              ) : null}
            </section>
          ) : null}

          {loadError ? (
            <section className="rounded-2xl border border-[#fca5a5] bg-[#fff1f2] p-4 text-[13px] text-[#9f1239]">
              {loadError}
            </section>
          ) : null}

          {loading ? (
            <section className="rounded-2xl border border-black/[0.08] bg-white p-4 text-[13px] text-[#667085]">
              Loading agents and run history...
            </section>
          ) : null}

          <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {runsByAgent.map(({ agent, runs }) => (
              <article
                key={agent.id}
                className="rounded-2xl border border-black/[0.08] bg-white p-4 shadow-[0_14px_36px_rgba(15,23,42,0.08)]"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h2 className="text-[18px] font-semibold text-[#111827]">{agent.name}</h2>
                    <p className="mt-1 text-[13px] text-[#667085]">{agent.description}</p>
                    <p className="mt-1 text-[12px] text-[#98a2b3]">
                      Last run {agent.lastRun ? formatRelativeTime(agent.lastRun) : "never"} · {agent.totalRuns} total runs
                    </p>
                    {agent.scheduleLabel ? (
                      <p className="mt-1 text-[12px] text-[#7c3aed]">
                        Next run {agent.nextRunAt ? new Date(agent.nextRunAt).toLocaleString() : "scheduled"} · {agent.scheduleLabel}
                      </p>
                    ) : null}
                  </div>
                  <span
                    className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                      agent.status === "active"
                        ? "bg-[#ecfdf3] text-[#166534]"
                        : agent.status === "paused"
                          ? "bg-[#fff7ed] text-[#9a3412]"
                          : "bg-[#fff1f2] text-[#b91c1c]"
                    }`}
                  >
                    {agent.status}
                  </span>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <a
                    href={`/agents/${encodeURIComponent(agent.id)}`}
                    className="rounded-full bg-[#7c3aed] hover:bg-[#6d28d9] transition-colors px-3 py-1.5 text-[12px] font-semibold text-white"
                  >
                    Open agent
                  </a>
                  {agent.unhealthyConnectors.length > 0 ? (
                    <button
                      type="button"
                      onClick={() =>
                        openConnectorOverlay(agent.unhealthyConnectors[0], {
                          fromPath: window.location.pathname,
                        })
                      }
                      className="rounded-full border border-[#f59e0b] bg-[#fffbeb] px-3 py-1.5 text-[12px] font-semibold text-[#92400e]"
                    >
                      Configure connectors
                    </button>
                  ) : null}
                </div>
                {agent.unhealthyConnectors.length > 0 ? (
                  <div className="mt-2 rounded-xl border border-[#fde68a] bg-[#fffbeb] px-3 py-2 text-[12px] text-[#92400e]">
                    This agent needs connector setup before it can run reliably:
                    {" "}
                    {agent.unhealthyConnectors.join(", ")}
                  </div>
                ) : null}
                <div className="mt-3 space-y-1 text-[12px] text-[#667085]">
                  {runs.slice(0, 2).map((run) => (
                    <p key={run.runId}>
                      {run.runId}: {run.status} · ${(run.llmCostUsd || 0).toFixed(2)}
                    </p>
                  ))}
                  {runs.length === 0 ? <p>No runs yet.</p> : null}
                </div>
              </article>
            ))}
          </section>

          <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <AgentRunHistory runs={allRuns} />
            <MemoryExplorer
              episodes={episodes}
              workingMemory={workingMemory}
            />
          </section>
        </div>
      </div>
    </div>
  );
}
