import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import {
  listAgents,
  listConnectorCredentials,
  listConnectorCatalog,
  installMarketplaceAgent,
  listMarketplaceAgents,
  getMarketplaceAgent,
  type MarketplaceAgentDetail,
  type MarketplaceAgentSummary,
} from "../../api/client";
import { AgentInstallModal } from "../components/marketplace/AgentInstallModal";
import { ConnectorStatusPill } from "../components/marketplace/ConnectorStatusPill";
import { AppRouteOverlayModal } from "../components/AppRouteOverlayModal";
import { openConnectorOverlay } from "../utils/connectorOverlay";
import {
  MarketplaceHeaderControls,
  type MarketplacePricingFilter,
} from "../components/marketplace/MarketplaceHeaderControls";
import { MarketplaceAgentDetailPage } from "./MarketplaceAgentDetailPage";

type PricingFilter = MarketplacePricingFilter;

function navigateToPath(path: string) {
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function buildWorkflowPickerPath(agentId: string): string {
  const query = new URLSearchParams({
    open_picker: "1",
    agent: String(agentId || "").trim(),
  });
  return `/workflow-builder?${query.toString()}`;
}

type SetupComplexity = "Easy" | "Medium" | "Complex";

function getSetupComplexity(requiredConnectorCount: number): SetupComplexity {
  if (requiredConnectorCount <= 1) {
    return "Easy";
  }
  if (requiredConnectorCount <= 3) {
    return "Medium";
  }
  return "Complex";
}

function setupComplexityClass(value: SetupComplexity): string {
  if (value === "Easy") {
    return "border-[#bbf7d0] bg-[#ecfdf3] text-[#166534]";
  }
  if (value === "Medium") {
    return "border-[#fde68a] bg-[#fffbeb] text-[#92400e]";
  }
  return "border-[#fecaca] bg-[#fff1f2] text-[#b42318]";
}

function inferOutputFormatLabel(agent: MarketplaceAgentSummary): string {
  const explicit = String((agent as Record<string, unknown>).output_format || "").trim();
  if (explicit) {
    return explicit;
  }
  const description = String(agent.description || "").toLowerCase();
  if (/(google\s+sheet|spreadsheet|csv|dashboard)/i.test(description)) {
    return "Google Sheet";
  }
  if (/(google\s+doc|document|brief|report)/i.test(description)) {
    return "Google Doc";
  }
  if (/(slack|channel)/i.test(description)) {
    return "Slack message";
  }
  if (/(email|outreach|newsletter)/i.test(description)) {
    return "Email draft";
  }
  return "Chat response";
}

type ConnectorStatusValue = "connected" | "missing" | "not_required";
type InstalledAgentRecord = {
  id?: string;
  agent_id: string;
  name?: string;
  version: string;
  definition?: Record<string, unknown>;
};

function readConnectorStatusSummary(
  agent: MarketplaceAgentSummary,
): { status: ConnectorStatusValue; missing: number; connected: number } {
  const required = Array.isArray(agent.required_connectors) ? agent.required_connectors : [];
  if (!required.length) {
    return { status: "not_required", missing: 0, connected: 0 };
  }
  const map = (agent.connector_status || {}) as Record<string, string>;
  let missing = 0;
  let connected = 0;
  for (const connectorId of required) {
    const value = String(map[connectorId] || "not_required").trim().toLowerCase();
    if (value === "missing") {
      missing += 1;
      continue;
    }
    if (value === "connected") {
      connected += 1;
    }
  }
  if (missing > 0) {
    return { status: "missing", missing, connected };
  }
  if (connected > 0) {
    return { status: "connected", missing: 0, connected };
  }
  return { status: "not_required", missing: 0, connected: 0 };
}

type MarketplacePageProps = {
  query?: string;
  onQueryChange?: (value: string) => void;
  pricingFilter?: PricingFilter;
  onPricingFilterChange?: (value: PricingFilter) => void;
  onFilteredCountChange?: (count: number) => void;
  hideTopControls?: boolean;
};

export function MarketplacePage({
  query: controlledQuery,
  onQueryChange,
  pricingFilter: controlledPricingFilter,
  onPricingFilterChange,
  onFilteredCountChange,
  hideTopControls = false,
}: MarketplacePageProps = {}) {
  const [internalQuery, setInternalQuery] = useState("");
  const [internalPricingFilter, setInternalPricingFilter] = useState<PricingFilter>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [agents, setAgents] = useState<MarketplaceAgentSummary[]>([]);
  const [availableConnectorIds, setAvailableConnectorIds] = useState<string[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [selectedAgentDetail, setSelectedAgentDetail] = useState<MarketplaceAgentDetail | null>(null);
  const [selectedDetailAgentId, setSelectedDetailAgentId] = useState<string | null>(null);
  const [installing, setInstalling] = useState(false);
  const [installedAgentIds, setInstalledAgentIds] = useState<string[]>([]);
  const [installedAgentRecordById, setInstalledAgentRecordById] = useState<
    Record<string, InstalledAgentRecord>
  >({});
  const [installedAgentVersionById, setInstalledAgentVersionById] = useState<Record<string, string>>(
    {},
  );
  const openedFromWorkflow = useMemo(() => {
    if (typeof window === "undefined") {
      return false;
    }
    const params = new URLSearchParams(window.location.search || "");
    return String(params.get("from") || "").trim() === "/workflow-builder";
  }, []);
  const query = controlledQuery ?? internalQuery;
  const pricingFilter = controlledPricingFilter ?? internalPricingFilter;
  const setQuery = onQueryChange ?? setInternalQuery;
  const setPricingFilter = onPricingFilterChange ?? setInternalPricingFilter;

  useEffect(() => {
    const onInstalled = (event: Event) => {
      const detail = (event as CustomEvent<{ agentId?: string; version?: string }>).detail || {};
      const installedId = String(detail.agentId || "").trim();
      if (!installedId) {
        return;
      }
      setInstalledAgentIds((previous) =>
        previous.includes(installedId) ? previous : [...previous, installedId],
      );
      const installedVersion = String(detail.version || "").trim();
      if (installedVersion) {
        setInstalledAgentVersionById((previous) => ({
          ...previous,
          [installedId]: installedVersion,
        }));
      }
      setInstalledAgentRecordById((previous) => ({
        ...previous,
        [installedId]: {
          ...(previous[installedId] || { agent_id: installedId, version: "" }),
          agent_id: installedId,
          version: installedVersion || String(previous[installedId]?.version || "").trim(),
        },
      }));
    };
    window.addEventListener("maia:marketplace-agent-installed", onInstalled as EventListener);
    return () => {
      window.removeEventListener("maia:marketplace-agent-installed", onInstalled as EventListener);
    };
  }, []);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const [rows, connectorCredentials, installedAgents, connectorCatalog] = await Promise.all([
          listMarketplaceAgents({
            q: query.trim() || undefined,
            pricing: pricingFilter === "all" ? undefined : pricingFilter,
            sort_by: "installs",
            limit: 60,
          }),
          listConnectorCredentials(),
          listAgents(),
          listConnectorCatalog(),
        ]);
        const publicConnectorIds = (connectorCatalog || [])
          .filter((row) => String(row?.auth?.kind || "").trim().toLowerCase() === "none")
          .map((row) => String(row.id || "").trim())
          .filter(Boolean);
        setAgents(rows || []);
        setAvailableConnectorIds(
          Array.from(
            new Set(
              [
                ...(connectorCredentials || [])
                  .map((row) => String(row.connector_id || "").trim())
                  .filter(Boolean),
                ...publicConnectorIds,
              ],
            ),
          ),
        );
        setInstalledAgentIds(
          (installedAgents || [])
            .map((agent) => String(agent.agent_id || "").trim())
            .filter(Boolean),
        );
        const nextInstalledVersionById: Record<string, string> = {};
        const nextInstalledRecordsById: Record<string, InstalledAgentRecord> = {};
        for (const installed of installedAgents || []) {
          const installedId = String(installed.agent_id || "").trim();
          if (!installedId) {
            continue;
          }
          const installedVersion = String(installed.version || "").trim();
          nextInstalledVersionById[installedId] = installedVersion;
          nextInstalledRecordsById[installedId] = {
            ...(installed as unknown as InstalledAgentRecord),
            agent_id: installedId,
            version: installedVersion,
          };
        }
        setInstalledAgentVersionById(nextInstalledVersionById);
        setInstalledAgentRecordById(nextInstalledRecordsById);
      } catch (nextError) {
        const message = String(nextError || "Failed to load marketplace.");
        setError(message);
      } finally {
        setLoading(false);
      }
    };
    const timer = window.setTimeout(() => {
      void load();
    }, 250);
    return () => window.clearTimeout(timer);
  }, [pricingFilter, query]);

  useEffect(() => {
    if (!selectedAgentId) {
      setSelectedAgentDetail(null);
      return;
    }
    const loadDetail = async () => {
      try {
        const detail = await getMarketplaceAgent(selectedAgentId);
        setSelectedAgentDetail(detail);
      } catch (nextError) {
        toast.error(`Unable to load install details: ${String(nextError)}`);
        setSelectedAgentId(null);
      }
    };
    void loadDetail();
  }, [selectedAgentId]);

  const filteredAgents = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return agents.filter((agent) => {
      if (pricingFilter !== "all" && agent.pricing_tier !== pricingFilter) {
        return false;
      }
      if (!normalizedQuery) {
        return true;
      }
      return (
        agent.name.toLowerCase().includes(normalizedQuery) ||
        agent.description.toLowerCase().includes(normalizedQuery) ||
        (agent.tags || []).some((tag) => tag.toLowerCase().includes(normalizedQuery))
      );
    });
  }, [agents, pricingFilter, query]);

  useEffect(() => {
    if (!onFilteredCountChange) {
      return;
    }
    onFilteredCountChange(filteredAgents.length);
  }, [filteredAgents.length, onFilteredCountChange]);

  const installSelectedAgent = async (
    agentId: string,
    payload: {
      version?: string | null;
      connector_mapping: Record<string, string>;
      gate_policies?: Record<string, boolean>;
    },
  ): Promise<{
    success: boolean;
    missingConnectors?: string[];
    error?: string;
    triggerFamily?: string | null;
    alreadyInstalled?: boolean;
    autoMappedConnectors?: Record<string, string>;
  }> => {
    setInstalling(true);
    try {
      const result = await installMarketplaceAgent(agentId, payload);
      if (!result.success) {
        if (result.missing_connectors?.length) {
          toast.error(`Missing connectors: ${result.missing_connectors.join(", ")}`);
        } else {
          toast.error(result.error || "Install failed.");
        }
        return {
          success: false,
          missingConnectors: result.missing_connectors || [],
          error: result.error || "Install failed.",
          triggerFamily: null,
          alreadyInstalled: false,
          autoMappedConnectors: {},
        };
      }
      setInstalledAgentIds((previous) =>
        previous.includes(agentId) ? previous : [...previous, agentId],
      );
      const installedRecord = result.installed_agent;
      const installedVersion = String(installedRecord?.version || "").trim();
      if (installedVersion) {
        setInstalledAgentVersionById((previous) => ({
          ...previous,
          [agentId]: installedVersion,
        }));
      }
      setInstalledAgentRecordById((previous) => ({
        ...previous,
        [agentId]: {
          ...(previous[agentId] || { agent_id: agentId, version: "" }),
          ...(installedRecord || {}),
          agent_id: agentId,
          version: installedVersion || String(previous[agentId]?.version || payload.version || "").trim(),
        },
      }));
      window.dispatchEvent(
        new CustomEvent("maia:marketplace-agent-installed", {
          detail: {
            agentId,
            version: installedVersion || String(payload.version || "").trim(),
          },
        }),
      );
      const triggerFamily = String(
        (result as unknown as Record<string, unknown>).trigger_family || "",
      ).trim();
      if (result.already_installed) {
        toast.success("Agent already installed.");
      } else {
        toast.success("Agent installed.");
      }
      return {
        success: true,
        triggerFamily: triggerFamily || null,
        alreadyInstalled: Boolean(result.already_installed),
        autoMappedConnectors: result.auto_mapped_connectors || {},
      };
    } catch (nextError) {
      const message = `Install failed: ${String(nextError)}`;
      toast.error(message);
      return {
        success: false,
        error: message,
        triggerFamily: null,
        alreadyInstalled: false,
        autoMappedConnectors: {},
      };
    } finally {
      setInstalling(false);
    }
  };

  const openConnectorSetup = (connectorId: string) => {
    openConnectorOverlay(connectorId, { fromPath: window.location.pathname });
  };

  const handleQuickInstall = async (agent: MarketplaceAgentSummary) => {
    if (!agent?.agent_id) {
      return;
    }
    const result = await installSelectedAgent(agent.agent_id, {
      version: agent.version,
      connector_mapping: {},
      gate_policies: {},
    });
    if (result.success && openedFromWorkflow) {
      navigateToPath(buildWorkflowPickerPath(agent.agent_id));
    }
  };

  return (
    <div className="h-full overflow-y-auto bg-[#f6f6f7] p-5">
      <div className="mx-auto max-w-[1320px] space-y-4">
        {!hideTopControls ? (
          <section className="rounded-[22px] border border-black/[0.08] bg-white/92 px-4 py-3 shadow-[0_14px_36px_rgba(15,23,42,0.1)] backdrop-blur-md">
            <MarketplaceHeaderControls
              query={query}
              onQueryChange={setQuery}
              pricingFilter={pricingFilter}
              onPricingFilterChange={setPricingFilter}
              resultCount={filteredAgents.length}
            />
          </section>
        ) : null}

        {error ? (
          <section className="rounded-2xl border border-[#fca5a5] bg-[#fff1f2] p-4 text-[13px] text-[#9f1239]">
            {error}
          </section>
        ) : null}

        {loading ? (
          <section className="rounded-2xl border border-black/[0.08] bg-white p-6 text-[14px] text-[#667085]">
            Loading marketplace agents...
          </section>
        ) : (
          <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {filteredAgents.map((agent) => {
              const installed = installedAgentIds.includes(agent.agent_id);
              const requiredConnectors = Array.isArray(agent.required_connectors)
                ? agent.required_connectors
                : [];
              const connectorSummary = readConnectorStatusSummary(agent);
              const connectorsReady = connectorSummary.missing === 0;
              const complexity = getSetupComplexity(requiredConnectors.length);
              const outputFormat = inferOutputFormatLabel(agent);
              const showInstallNow = !installed && connectorsReady;
              const installedVersion = String(
                installedAgentRecordById[agent.agent_id]?.version ||
                  installedAgentVersionById[agent.agent_id] ||
                  "",
              ).trim();
              const hasUpdate =
                installed &&
                installedVersion &&
                String(agent.version || "").trim() !== installedVersion;
              return (
                <article
                  key={agent.id}
                  className="rounded-[22px] border border-black/[0.08] bg-white p-5 shadow-[0_14px_36px_rgba(15,23,42,0.08)]"
                >
                  <p className="text-[12px] text-[#667085]">
                    {agent.verified ? "Verified publisher" : "Community publisher"}
                  </p>
                  <h2 className="mt-1 text-[18px] font-semibold text-[#111827]">{agent.name}</h2>
                  <p className="mt-2 text-[13px] leading-[1.5] text-[#475467]">{agent.description}</p>
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
                    <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${setupComplexityClass(complexity)}`}>
                      Setup: {complexity}
                    </span>
                    <span className="rounded-full border border-[#d0d5dd] bg-[#f8fafc] px-2.5 py-1 text-[11px] font-semibold text-[#344054]">
                      Output: {outputFormat}
                    </span>
                    <span className="inline-flex items-center gap-1 rounded-full border border-[#d0d5dd] bg-white px-2 py-0.5 text-[11px] font-semibold text-[#344054]">
                      <ConnectorStatusPill status={connectorSummary.status} compact />
                      <span>
                        {connectorSummary.missing > 0
                          ? `${connectorSummary.missing} missing`
                          : connectorSummary.connected > 0
                            ? "Connected"
                            : "Not required"}
                      </span>
                    </span>
                    {showInstallNow ? (
                      <span className="rounded-full border border-[#bbf7d0] bg-[#ecfdf3] px-2.5 py-1 text-[11px] font-semibold text-[#166534]">
                        Ready to install
                      </span>
                    ) : null}
                    {hasUpdate ? (
                      <span className="rounded-full border border-[#c4b5fd] bg-[#f5f3ff] px-2.5 py-1 text-[11px] font-semibold text-[#7c3aed]">
                        Update available
                      </span>
                    ) : null}
                  </div>
                  <div className="mt-4 flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        if (installed) {
                          return;
                        }
                        if (connectorsReady) {
                          void handleQuickInstall(agent);
                          return;
                        }
                        setSelectedAgentId(agent.agent_id);
                      }}
                      className={`rounded-full px-4 py-2 text-[12px] font-semibold ${
                        installed
                          ? "border border-[#bbf7d0] bg-[#ecfdf3] text-[#166534]"
                          : "bg-[#7c3aed] text-white shadow-[0_1px_3px_rgba(124,58,237,0.3)]"
                      }`}
                    >
                      {installed ? "Installed" : "Install"}
                    </button>
                    {!installed && connectorsReady ? (
                      <button
                        type="button"
                        onClick={() => setSelectedAgentId(agent.agent_id)}
                        className="rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[12px] font-semibold text-[#344054]"
                      >
                        Customize
                      </button>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => setSelectedDetailAgentId(agent.agent_id)}
                      className="rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[12px] font-semibold text-[#344054]"
                    >
                      View detail
                    </button>
                  </div>
                </article>
              );
            })}
          </section>
        )}
      </div>

      {selectedDetailAgentId ? (
        <AppRouteOverlayModal
          title="Agent Details"
          subtitle="Inspect capabilities, connectors, schedule, and reviews without leaving marketplace."
          onClose={() => setSelectedDetailAgentId(null)}
        >
          <MarketplaceAgentDetailPage
            agentId={selectedDetailAgentId}
            onInstalledAgentChange={({ agentId, version }) => {
              setInstalledAgentIds((previous) =>
                previous.includes(agentId) ? previous : [...previous, agentId],
              );
              setInstalledAgentVersionById((previous) => ({
                ...previous,
                [agentId]: version,
              }));
              setInstalledAgentRecordById((previous) => ({
                ...previous,
                [agentId]: {
                  ...(previous[agentId] || { agent_id: agentId, version: "" }),
                  agent_id: agentId,
                  version,
                },
              }));
            }}
          />
        </AppRouteOverlayModal>
      ) : null}

      <AgentInstallModal
        open={Boolean(selectedAgentDetail)}
        agent={selectedAgentDetail}
        availableConnectorIds={availableConnectorIds}
        installing={installing}
        onOpenConnectorSetup={openConnectorSetup}
        onClose={() => {
          if (installing) {
            return;
          }
          setSelectedAgentId(null);
          setSelectedAgentDetail(null);
        }}
        onInstall={installSelectedAgent}
      />
    </div>
  );
}
