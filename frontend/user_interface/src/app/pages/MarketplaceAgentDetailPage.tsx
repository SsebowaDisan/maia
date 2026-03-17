import { useEffect, useMemo, useState, type ComponentType } from "react";
import { toast } from "sonner";
import {
  Calendar,
  Database,
  FileText,
  MessageSquare,
  Search,
} from "lucide-react";

import {
  getMarketplaceAgent,
  getMarketplaceAgentReviews,
  installMarketplaceAgent,
  listAgents,
  listConnectorCatalog,
  listConnectorCredentials,
  listConnectorHealth,
  preflightMarketplaceAgentInstall,
  type MarketplaceAgentDetail,
  type MarketplaceAgentInstallPreflightResponse,
  type MarketplaceAgentReview,
} from "../../api/client";
import { AgentInstallModal } from "../components/marketplace/AgentInstallModal";
import { ConnectorStatusPill } from "../components/marketplace/ConnectorStatusPill";

type MarketplaceAgentDetailPageProps = {
  agentId: string;
  onInstalledAgentChange?: (payload: { agentId: string; version: string }) => void;
};

function navigateToPath(path: string) {
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function normalizeLabel(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function resolveConnectorIcon(connectorId: string): ComponentType<{ className?: string }> {
  const normalized = String(connectorId || "").trim().toLowerCase();
  if (normalized.includes("google")) return Calendar;
  if (normalized.includes("news") || normalized.includes("search")) return Search;
  if (normalized.includes("reddit") || normalized.includes("slack")) return MessageSquare;
  if (normalized.includes("sec") || normalized.includes("edgar")) return FileText;
  return Database;
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
  return `Cron schedule: ${cronExpression}`;
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

function compareVersions(leftRaw: string, rightRaw: string): number {
  const left = String(leftRaw || "").trim();
  const right = String(rightRaw || "").trim();
  if (!left && !right) {
    return 0;
  }
  if (!left) {
    return -1;
  }
  if (!right) {
    return 1;
  }
  const leftParts = left.split(/[^0-9A-Za-z]+/g).filter(Boolean);
  const rightParts = right.split(/[^0-9A-Za-z]+/g).filter(Boolean);
  const len = Math.max(leftParts.length, rightParts.length);
  for (let i = 0; i < len; i += 1) {
    const leftPart = leftParts[i] || "0";
    const rightPart = rightParts[i] || "0";
    const leftNum = Number(leftPart);
    const rightNum = Number(rightPart);
    const leftIsNum = Number.isFinite(leftNum) && /^\d+$/.test(leftPart);
    const rightIsNum = Number.isFinite(rightNum) && /^\d+$/.test(rightPart);
    if (leftIsNum && rightIsNum) {
      if (leftNum > rightNum) {
        return 1;
      }
      if (leftNum < rightNum) {
        return -1;
      }
      continue;
    }
    const cmp = leftPart.localeCompare(rightPart);
    if (cmp > 0) {
      return 1;
    }
    if (cmp < 0) {
      return -1;
    }
  }
  return 0;
}

function normalizeConnectorStatus(value: string): "connected" | "missing" | "not_required" {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "connected") {
    return "connected";
  }
  if (normalized === "missing") {
    return "missing";
  }
  return "not_required";
}

export function MarketplaceAgentDetailPage({
  agentId,
  onInstalledAgentChange,
}: MarketplaceAgentDetailPageProps) {
  const [agent, setAgent] = useState<MarketplaceAgentDetail | null>(null);
  const [reviews, setReviews] = useState<MarketplaceAgentReview[]>([]);
  const [connectedConnectorIds, setConnectedConnectorIds] = useState<string[]>([]);
  const [availableConnectorIds, setAvailableConnectorIds] = useState<string[]>([]);
  const [installedVersion, setInstalledVersion] = useState("");
  const [preflight, setPreflight] = useState<MarketplaceAgentInstallPreflightResponse | null>(null);
  const [preflightLoading, setPreflightLoading] = useState(false);
  const [installModalOpen, setInstallModalOpen] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [installError, setInstallError] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      setInstallError("");
      try {
        const [
          detail,
          reviewRows,
          healthRows,
          installedAgents,
          connectorCredentials,
          connectorCatalog,
          nextPreflight,
        ] = await Promise.all([
          getMarketplaceAgent(agentId),
          getMarketplaceAgentReviews(agentId, { limit: 20 }),
          listConnectorHealth(),
          listAgents(),
          listConnectorCredentials(),
          listConnectorCatalog(),
          preflightMarketplaceAgentInstall(agentId),
        ]);
        setAgent(detail);
        setReviews(reviewRows || []);
        setPreflight(nextPreflight);
        setConnectedConnectorIds(
          (healthRows || [])
            .filter((row) => Boolean(row?.ok))
            .map((row) => String(row?.connector_id || ""))
            .filter(Boolean),
        );
        const installedById = new Map(
          (installedAgents || [])
            .map((row) => [String(row?.agent_id || "").trim(), String(row?.version || "").trim()] as const)
            .filter(([id]) => Boolean(id)),
        );
        setInstalledVersion(installedById.get(String(agentId || "").trim()) || "");

        const publicConnectorIds = (connectorCatalog || [])
          .filter((row) => String(row?.auth?.kind || "").trim().toLowerCase() === "none")
          .map((row) => String(row.id || "").trim())
          .filter(Boolean);
        const credentialConnectorIds = (connectorCredentials || [])
          .map((row) => String(row.connector_id || "").trim())
          .filter(Boolean);
        setAvailableConnectorIds(Array.from(new Set([...credentialConnectorIds, ...publicConnectorIds])));
      } catch (nextError) {
        setError(String(nextError || "Failed to load marketplace agent."));
      } finally {
        setLoading(false);
      }
    };
    if (!agentId) {
      setLoading(false);
      setError("Missing agent id.");
      return;
    }
    void load();
  }, [agentId]);

  const refreshPreflight = async () => {
    if (!agentId) {
      return null;
    }
    setPreflightLoading(true);
    try {
      const next = await preflightMarketplaceAgentInstall(agentId, {
        version: agent?.version,
      });
      setPreflight(next);
      return next;
    } catch (nextError) {
      setInstallError(String(nextError || "Failed to refresh install readiness."));
      return null;
    } finally {
      setPreflightLoading(false);
    }
  };

  const applyInstallResult = (result: {
    already_installed?: boolean;
    installed_agent?: {
      agent_id: string;
      version: string;
    } | null;
  }) => {
    const nextVersion = String(result.installed_agent?.version || agent?.version || "").trim();
    if (nextVersion) {
      window.dispatchEvent(
        new CustomEvent("maia:marketplace-agent-installed", {
          detail: {
            agentId: String(agent?.agent_id || agentId || "").trim(),
            version: nextVersion,
          },
        }),
      );
      setInstalledVersion(nextVersion);
      onInstalledAgentChange?.({
        agentId: String(agent?.agent_id || agentId || "").trim(),
        version: nextVersion,
      });
    }
    if (preflight) {
      setPreflight({
        ...preflight,
        already_installed: true,
        can_install_immediately: true,
        missing_connectors: [],
      });
    }
  };

  const runInstall = async (payload: {
    version?: string | null;
    connector_mapping: Record<string, string>;
    gate_policies: Record<string, boolean>;
  }) => {
    if (!agent?.agent_id) {
      return {
        success: false,
        error: "Missing agent id.",
        triggerFamily: null,
        alreadyInstalled: false,
        autoMappedConnectors: {},
      };
    }
    setInstalling(true);
    setInstallError("");
    try {
      const result = await installMarketplaceAgent(agent.agent_id, payload);
      if (!result.success) {
        const message =
          result.error ||
          (Array.isArray(result.missing_connectors) && result.missing_connectors.length
            ? `Missing connectors: ${result.missing_connectors.join(", ")}`
            : "Install failed.");
        setInstallError(message);
        return {
          success: false,
          missingConnectors: result.missing_connectors || [],
          error: message,
          triggerFamily: null,
          alreadyInstalled: false,
          autoMappedConnectors: {},
        };
      }
      applyInstallResult(result);
      if (result.already_installed) {
        toast.success("Agent already installed.");
      } else {
        toast.success("Agent installed.");
      }
      return {
        success: true,
        triggerFamily: String(result.trigger_family || "").trim() || null,
        alreadyInstalled: Boolean(result.already_installed),
        autoMappedConnectors: result.auto_mapped_connectors || {},
      };
    } catch (nextError) {
      const message = `Install failed: ${String(nextError)}`;
      setInstallError(message);
      return {
        success: false,
        error: message,
        triggerFamily: null,
        alreadyInstalled: false,
        autoMappedConnectors: {},
      };
    } finally {
      setInstalling(false);
      void refreshPreflight();
    }
  };

  const requiredConnectors = useMemo(() => agent?.required_connectors || [], [agent]);
  const tags = useMemo(
    () =>
      Array.isArray(agent?.tags)
        ? agent.tags.map((tag) => String(tag || "").trim()).filter(Boolean)
        : [],
    [agent?.tags],
  );

  const connectorRows = useMemo(
    () =>
      requiredConnectors.map((connectorId) => {
        const rawStatus = String((agent?.connector_status || {})[connectorId] || "").trim();
        const status = rawStatus
          ? normalizeConnectorStatus(rawStatus)
          : connectedConnectorIds.includes(connectorId)
            ? "connected"
            : "missing";
        return {
          connectorId,
          status,
        };
      }),
    [agent?.connector_status, connectedConnectorIds, requiredConnectors],
  );

  const scheduleSummary = useMemo(() => {
    const trigger = (agent?.definition?.trigger || {}) as Record<string, unknown>;
    const family = String(trigger.family || "").trim().toLowerCase();
    if (family !== "scheduled") {
      return null;
    }
    const cronExpression = String(trigger.cron_expression || "").trim();
    const timezone = String(trigger.timezone || "UTC").trim() || "UTC";
    return {
      cronExpression,
      timezone,
      humanText: describeCronExpression(cronExpression),
      nextRun: getNextScheduledRun(cronExpression),
    };
  }, [agent?.definition]);

  const verifiedReviewCount = useMemo(
    () =>
      reviews.filter((review) => {
        const row = review as unknown as Record<string, unknown>;
        return Boolean(row.verified_purchase || row.verified_user || row.is_verified);
      }).length,
    [reviews],
  );

  const installed = Boolean(preflight?.already_installed || installedVersion);
  const hasUpdateAvailable = Boolean(
    installed && installedVersion && compareVersions(String(agent?.version || ""), installedVersion) > 0,
  );
  const canInstallImmediately = Boolean(preflight?.can_install_immediately);

  if (loading) {
    return (
      <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
        <div className="mx-auto max-w-[1080px] rounded-2xl border border-black/[0.08] bg-white p-5 text-[14px] text-[#667085]">
          Loading agent details...
        </div>
      </div>
    );
  }

  if (!agent || error) {
    return (
      <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
        <div className="mx-auto max-w-[980px] rounded-2xl border border-black/[0.08] bg-white p-5">
          <h1 className="text-[24px] font-semibold text-[#101828]">Agent not found</h1>
          <p className="mt-2 text-[14px] text-[#667085]">{error || "No marketplace entry for this agent id."}</p>
          <button
            type="button"
            onClick={() => navigateToPath("/marketplace")}
            className="mt-3 inline-block text-[13px] font-semibold text-[#1d4ed8] hover:underline"
          >
            Back to marketplace
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
      <div className="mx-auto max-w-[1080px] space-y-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5 shadow-[0_20px_54px_rgba(15,23,42,0.1)]">
          <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">
            Marketplace agent
          </p>
          <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">{agent.name}</h1>
          <p className="mt-2 text-[15px] text-[#475467]">{agent.description}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <span className="rounded-full border border-[#d0d5dd] bg-[#f8fafc] px-2.5 py-1 text-[11px] font-semibold text-[#344054]">
              {Number(agent.avg_rating || 0).toFixed(1)} rating
            </span>
            <span className="rounded-full border border-[#d0d5dd] bg-[#f8fafc] px-2.5 py-1 text-[11px] font-semibold text-[#344054]">
              {(agent.install_count || 0).toLocaleString()} installs
            </span>
            <span className="rounded-full border border-[#d0d5dd] bg-white px-2.5 py-1 text-[11px] font-semibold uppercase text-[#344054]">
              {agent.pricing_tier}
            </span>
            {installed ? (
              <span className="rounded-full border border-[#bbf7d0] bg-[#ecfdf3] px-2.5 py-1 text-[11px] font-semibold text-[#166534]">
                Installed
              </span>
            ) : null}
            {installed ? (
              <button
                type="button"
                onClick={() => navigateToPath(`/agents/${encodeURIComponent(agent.agent_id)}/run`)}
                className="rounded-full border border-[#bfdbfe] bg-[#eff6ff] px-2.5 py-1 text-[11px] font-semibold text-[#1d4ed8]"
              >
                View run history
              </button>
            ) : null}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            {preflightLoading ? (
              <button
                type="button"
                disabled
                className="rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[12px] font-semibold text-[#344054] opacity-70"
              >
                Checking install readiness...
              </button>
            ) : null}
            {!preflightLoading && hasUpdateAvailable ? (
              <button
                type="button"
                onClick={() => {
                  void runInstall({
                    version: agent.version,
                    connector_mapping: preflight?.auto_mapped || {},
                    gate_policies: {},
                  });
                }}
                disabled={installing}
                className="rounded-full bg-[#111827] px-4 py-2 text-[12px] font-semibold text-white disabled:opacity-60"
              >
                {installing ? "Updating..." : "Update available"}
              </button>
            ) : null}
            {!preflightLoading && !installed && canInstallImmediately ? (
              <button
                type="button"
                onClick={() => {
                  void runInstall({
                    version: agent.version,
                    connector_mapping: preflight?.auto_mapped || {},
                    gate_policies: {},
                  });
                }}
                disabled={installing}
                className="rounded-full bg-[#111827] px-4 py-2 text-[12px] font-semibold text-white disabled:opacity-60"
              >
                {installing ? "Installing..." : "Install"}
              </button>
            ) : null}
            {!preflightLoading && !installed && !canInstallImmediately ? (
              <button
                type="button"
                onClick={() => setInstallModalOpen(true)}
                className="rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[12px] font-semibold text-[#344054]"
              >
                Setup connectors and install
              </button>
            ) : null}
          </div>

          {installError ? (
            <p className="mt-2 rounded-xl border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-[12px] text-[#b42318]">
              {installError}
            </p>
          ) : null}

          {tags.length ? (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {tags.map((tag) => (
                <button
                  key={tag}
                  type="button"
                  onClick={() => navigateToPath(`/marketplace?tag=${encodeURIComponent(tag)}`)}
                  className="rounded-full border border-black/[0.08] bg-[#f9fafb] px-2 py-0.5 text-[11px] font-semibold text-[#475467] hover:border-black/[0.2] hover:text-[#111827]"
                >
                  #{tag}
                </button>
              ))}
            </div>
          ) : null}
        </section>

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border border-black/[0.08] bg-white p-4">
            <h2 className="text-[18px] font-semibold text-[#111827]">Required connectors</h2>
            {connectorRows.length ? (
              <div className="mt-3 space-y-2">
                {connectorRows.map(({ connectorId, status }) => {
                  const Icon = resolveConnectorIcon(connectorId);
                  return (
                    <div
                      key={connectorId}
                      className="flex items-center justify-between gap-2 rounded-xl border border-black/[0.06] bg-[#fcfcfd] px-3 py-2"
                    >
                      <div className="flex items-center gap-2">
                        <Icon className="h-4 w-4 text-[#667085]" />
                        <span className="text-[13px] font-semibold text-[#344054]">
                          {normalizeLabel(connectorId)}
                        </span>
                      </div>
                      <ConnectorStatusPill status={status} compact={false} />
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="mt-3 text-[12px] text-[#667085]">No connector requirements.</p>
            )}
            <p className="mt-3 text-[12px] text-[#667085]">
              Connector setup is managed in Settings.
            </p>
          </div>

          <div className="space-y-4">
            {scheduleSummary ? (
              <div className="rounded-2xl border border-black/[0.08] bg-white p-4">
                <h2 className="text-[18px] font-semibold text-[#111827]">Schedule</h2>
                <div className="mt-2 flex items-center gap-2">
                  <span className="rounded-full border border-[#bbf7d0] bg-[#f0fdf4] px-2.5 py-1 text-[11px] font-semibold text-[#166534]">
                    Automated
                  </span>
                  <span className="text-[12px] text-[#667085]">
                    Runs on cron:{" "}
                    <code className="rounded bg-[#f1f5f9] px-1 text-[#344054]">
                      {scheduleSummary.cronExpression}
                    </code>
                  </span>
                </div>
                <p className="mt-2 text-[12px] text-[#667085]">{scheduleSummary.humanText}</p>
                <p className="mt-1 text-[12px] text-[#667085]">Timezone: {scheduleSummary.timezone}</p>
                {scheduleSummary.nextRun ? (
                  <p className="mt-1 text-[12px] text-[#1d4ed8]">
                    Next run: {scheduleSummary.nextRun.toLocaleString()}
                  </p>
                ) : null}
              </div>
            ) : null}

            <div className="rounded-2xl border border-black/[0.08] bg-white p-4">
              <h2 className="text-[18px] font-semibold text-[#111827]">Tools</h2>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {Array.isArray(agent.definition?.tools) && (agent.definition.tools as string[]).length ? (
                  (agent.definition.tools as string[]).map((tool) => (
                    <span
                      key={tool}
                      className="rounded-full border border-[#e2e8f0] bg-[#f8fafc] px-2 py-0.5 text-[11px] font-mono text-[#475467]"
                    >
                      {tool}
                    </span>
                  ))
                ) : (
                  <p className="text-[12px] text-[#667085]">No tools listed.</p>
                )}
              </div>
            </div>

            <div className="rounded-2xl border border-black/[0.08] bg-white p-4">
              <h2 className="text-[18px] font-semibold text-[#111827]">Changelog</h2>
              <ul className="mt-3 list-disc space-y-1 pl-4 text-[13px] text-[#475467]">
                <li>Version {agent.version}</li>
                {installedVersion ? <li>Installed version {installedVersion}</li> : null}
              </ul>
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
          <h2 className="text-[18px] font-semibold text-[#111827]">Reviews</h2>
          <p className="mt-1 text-[12px] text-[#667085]">
            {reviews.length} total {verifiedReviewCount > 0 ? `- ${verifiedReviewCount} verified` : ""}
          </p>
          <div className="mt-3 space-y-2">
            {reviews.length ? (
              reviews.map((review) => (
                <div key={review.id} className="rounded-xl border border-black/[0.06] bg-[#fcfcfd] p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-[13px] font-semibold text-[#111827]">
                      {"*".repeat(Math.max(1, Math.min(5, Number(review.rating || 0))))}
                    </p>
                    {Boolean(
                      (review as unknown as Record<string, unknown>).verified_purchase ||
                        (review as unknown as Record<string, unknown>).verified_user ||
                        (review as unknown as Record<string, unknown>).is_verified,
                    ) ? (
                      <span className="rounded-full border border-[#bbf7d0] bg-[#ecfdf3] px-2 py-0.5 text-[10px] font-semibold text-[#166534]">
                        Verified user
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1 text-[12px] text-[#667085]">
                    {String(review.review_text || "").trim() || "No written review."}
                  </p>
                  {review.publisher_response ? (
                    <p className="mt-2 text-[12px] text-[#475467]">
                      Publisher response: {review.publisher_response}
                    </p>
                  ) : null}
                </div>
              ))
            ) : (
              <p className="text-[13px] text-[#667085]">No reviews yet.</p>
            )}
          </div>
        </section>
      </div>

      <AgentInstallModal
        open={installModalOpen}
        agent={agent}
        availableConnectorIds={availableConnectorIds}
        installing={installing}
        onOpenConnectorSetup={(connectorId) => {
          const normalized = String(connectorId || "").trim().toLowerCase();
          const mappedConnectorId =
            normalized === "google_calendar" || normalized === "google_analytics"
              ? "google_workspace"
              : connectorId;
          const target = `/connectors?connector=${encodeURIComponent(mappedConnectorId)}`;
          const popup = window.open(
            target,
            `connector-setup-${mappedConnectorId}`,
            "width=1120,height=820,noopener,noreferrer",
          );
          if (!popup) {
            navigateToPath(target);
          }
        }}
        onClose={() => {
          if (installing) {
            return;
          }
          setInstallModalOpen(false);
        }}
        onInstall={runInstall}
      />
    </div>
  );
}
