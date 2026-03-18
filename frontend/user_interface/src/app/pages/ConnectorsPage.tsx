import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw, Shield } from "lucide-react";

import {
  getConnectorBinding,
  listAgents,
  listConnectorCatalog,
  listConnectorCredentials,
  listConnectorHealth,
  listConnectorPlugins,
  patchConnectorBinding,
  type AgentSummaryRecord,
  type ConnectorCredentialRecord,
  type ConnectorPluginManifest,
} from "../../api/client";
import { ConnectorCatalogFilters } from "../components/connectors/ConnectorCatalogFilters";
import { ConnectorDetailPanel } from "../components/connectors/ConnectorDetailPanel";
import { ConnectorGoogleAdvancedSettings } from "../components/connectors/ConnectorGoogleAdvancedSettings";
import { ConnectorPermissionsModal } from "../components/connectors/ConnectorPermissionsModal";
import { ConnectorSuiteSection } from "../components/connectors/ConnectorSuiteSection";
import {
  buildConnectorStats,
  buildConnectorSummaries,
  buildFilteredSections,
  buildSuiteCounts,
  findChangedConnectorId,
  isBindingMissingError,
  isNotFoundError,
  uniqueIds,
  type ConnectorCatalogRow,
  type ConnectorHealthEntry,
  type ConnectorListFilter,
  type ConnectorSuiteFilter,
} from "../components/connectors/catalogModel";
import {
  MANUAL_CONNECTOR_DEFINITIONS,
  type ConnectorDefinition,
} from "../components/settings/connectorDefinitions";
import {
  normalizeServiceIds,
  serviceIdsFromScopes,
} from "../components/settings/tabs/integrations/googleServices";
import { useSettingsController } from "../components/settings/useSettingsController";
import type { ConnectorSummary } from "../types/connectorSummary";
import { normalizeConnectorSetupId } from "../utils/connectorOverlay";

export function ConnectorsPage() {
  const connectorsController = useSettingsController("connectors");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [plugins, setPlugins] = useState<ConnectorPluginManifest[]>([]);
  const [catalogRows, setCatalogRows] = useState<ConnectorCatalogRow[]>([]);
  const [healthMap, setHealthMap] = useState<Record<string, ConnectorHealthEntry>>({});
  const [credentialMap, setCredentialMap] = useState<
    Record<string, ConnectorCredentialRecord>
  >({});
  const [agents, setAgents] = useState<AgentSummaryRecord[]>([]);
  const [selectedConnectorId, setSelectedConnectorId] = useState<string | null>(null);
  const [permissionMatrix, setPermissionMatrix] = useState<Record<string, string[]>>({});
  const [savingPermissionFor, setSavingPermissionFor] = useState<string | null>(null);
  const [permissionError, setPermissionError] = useState("");
  const [activeFilter, setActiveFilter] =
    useState<ConnectorListFilter>("needs_setup");
  const [activeSuite, setActiveSuite] =
    useState<ConnectorSuiteFilter>("all");
  const [permissionsOpen, setPermissionsOpen] = useState(false);

  const googleEnabledServiceIds = useMemo(
    () =>
      normalizeServiceIds(
        Array.isArray(connectorsController.googleOAuthStatus.enabled_services)
          ? connectorsController.googleOAuthStatus.enabled_services
          : serviceIdsFromScopes(connectorsController.googleOAuthStatus.scopes || []),
      ),
    [
      connectorsController.googleOAuthStatus.enabled_services,
      connectorsController.googleOAuthStatus.scopes,
    ],
  );

  const googleSelectedServiceIds = useMemo(() => {
    const selected = normalizeServiceIds(
      Array.isArray(connectorsController.googleOAuthStatus.oauth_selected_services)
        ? connectorsController.googleOAuthStatus.oauth_selected_services
        : [],
    );
    return selected.length > 0 ? selected : googleEnabledServiceIds;
  }, [
    connectorsController.googleOAuthStatus.oauth_selected_services,
    googleEnabledServiceIds,
  ]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    setPermissionError("");
    try {
      const [
        pluginRowsResult,
        healthRowsResult,
        credentialRowsResult,
        agentRowsResult,
        connectorCatalogResult,
      ] = await Promise.allSettled([
        listConnectorPlugins(),
        listConnectorHealth(),
        listConnectorCredentials(),
        listAgents(),
        listConnectorCatalog(),
      ]);

      const pluginRows =
        pluginRowsResult.status === "fulfilled" &&
        Array.isArray(pluginRowsResult.value)
          ? pluginRowsResult.value
          : [];
      const healthRows =
        healthRowsResult.status === "fulfilled" &&
        Array.isArray(healthRowsResult.value)
          ? healthRowsResult.value
          : [];
      const credentialRows =
        credentialRowsResult.status === "fulfilled" &&
        Array.isArray(credentialRowsResult.value)
          ? credentialRowsResult.value
          : [];
      const agentRows =
        agentRowsResult.status === "fulfilled" &&
        Array.isArray(agentRowsResult.value)
          ? agentRowsResult.value
          : [];
      const nextCatalogRows =
        connectorCatalogResult.status === "fulfilled" &&
        Array.isArray(connectorCatalogResult.value)
          ? connectorCatalogResult.value
          : [];

      const hardFailure =
        pluginRowsResult.status === "rejected" &&
        healthRowsResult.status === "rejected" &&
        credentialRowsResult.status === "rejected";
      if (hardFailure) {
        throw (
          pluginRowsResult.reason ||
          healthRowsResult.reason ||
          credentialRowsResult.reason
        );
      }

      const nextHealthMap: Record<string, ConnectorHealthEntry> = {};
      for (const row of healthRows) {
        const connectorId = String(row?.connector_id || "").trim();
        if (!connectorId) {
          continue;
        }
        nextHealthMap[connectorId] = {
          ok: Boolean(row?.ok),
          message: String(row?.message || ""),
        };
      }

      const nextCredentialMap: Record<string, ConnectorCredentialRecord> = {};
      for (const row of credentialRows) {
        const connectorId = String(row?.connector_id || "").trim();
        if (!connectorId) {
          continue;
        }
        nextCredentialMap[connectorId] = row;
      }

      const allConnectorIds = uniqueIds([
        ...MANUAL_CONNECTOR_DEFINITIONS.map((definition) => definition.id),
        ...pluginRows.map((plugin) => plugin.connector_id),
        ...Object.keys(nextHealthMap),
        ...Object.keys(nextCredentialMap),
        ...nextCatalogRows
          .map((row) => String((row as Record<string, unknown>)?.id || "").trim())
          .filter(Boolean),
      ]);

      const defaultAllowedAgentIds = agentRows.map((agent) => agent.agent_id);
      const bindingEntries = await Promise.all(
        allConnectorIds.map(async (connectorId) => {
          try {
            const binding = await getConnectorBinding(connectorId);
            const allowed = uniqueIds(binding.allowed_agent_ids || []);
            return [
              connectorId,
              allowed.length > 0 ? allowed : defaultAllowedAgentIds,
            ] as const;
          } catch (bindingError) {
            if (
              isBindingMissingError(bindingError) ||
              isNotFoundError(bindingError)
            ) {
              return [connectorId, defaultAllowedAgentIds] as const;
            }
            throw bindingError;
          }
        }),
      );

      setPlugins(pluginRows);
      setCatalogRows(nextCatalogRows as ConnectorCatalogRow[]);
      setHealthMap(nextHealthMap);
      setCredentialMap(nextCredentialMap);
      setAgents(agentRows);
      setPermissionMatrix(Object.fromEntries(bindingEntries));
    } catch (loadError) {
      setError(`Failed to load connectors: ${String(loadError)}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const syncFromUrl = () => {
      const params = new URLSearchParams(window.location.search);
      const requestedConnectorId = normalizeConnectorSetupId(
        params.get("connector"),
      );
      setSelectedConnectorId(requestedConnectorId || null);
    };
    syncFromUrl();
    window.addEventListener("popstate", syncFromUrl);
    return () => {
      window.removeEventListener("popstate", syncFromUrl);
    };
  }, []);

  const updateConnectorQueryParam = useCallback((connectorId: string | null) => {
    if (typeof window === "undefined") {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    if (connectorId) {
      params.set("connector", normalizeConnectorSetupId(connectorId));
    } else {
      params.delete("connector");
    }
    const nextQuery = params.toString();
    const nextPath = nextQuery ? `/connectors?${nextQuery}` : "/connectors";
    window.history.replaceState({}, "", nextPath);
  }, []);

  const openConnectorDetail = useCallback(
    (connectorId: string) => {
      const normalizedConnectorId = normalizeConnectorSetupId(connectorId);
      if (!normalizedConnectorId) {
        return;
      }
      setSelectedConnectorId(normalizedConnectorId);
      updateConnectorQueryParam(normalizedConnectorId);
    },
    [updateConnectorQueryParam],
  );

  const closeConnectorDetail = useCallback(() => {
    setSelectedConnectorId(null);
    updateConnectorQueryParam(null);
  }, [updateConnectorQueryParam]);

  const cards = useMemo<ConnectorSummary[]>(
    () =>
      buildConnectorSummaries({
        manualDefinitions: MANUAL_CONNECTOR_DEFINITIONS as ConnectorDefinition[],
        plugins,
        healthMap,
        credentialMap,
        catalogRows,
        googleEnabledServiceIds,
        googleSelectedServiceIds,
      }),
    [
      catalogRows,
      credentialMap,
      googleEnabledServiceIds,
      googleSelectedServiceIds,
      healthMap,
      plugins,
    ],
  );

  const stats = useMemo(() => buildConnectorStats(cards), [cards]);

  const filteredCards = useMemo(
    () =>
      cards.filter((card) =>
        activeFilter === "all"
          ? true
          : activeFilter === "connected"
            ? card.status === "Connected"
            : activeFilter === "attention"
              ? card.status === "Expired" || card.status === "Needs permission"
              : card.status === "Not connected",
      ),
    [activeFilter, cards],
  );

  const suiteCounts = useMemo(
    () => buildSuiteCounts(filteredCards),
    [filteredCards],
  );

  const filteredSections = useMemo(
    () =>
      buildFilteredSections({
        cards,
        activeFilter,
        activeSuite,
      }),
    [activeFilter, activeSuite, cards],
  );

  const matrixAgents = useMemo(
    () =>
      agents.map((agent) => ({
        id: agent.agent_id,
        name: agent.name,
      })),
    [agents],
  );

  const selectedConnector = useMemo<ConnectorSummary | null>(() => {
    if (!selectedConnectorId) {
      return null;
    }
    const directMatch =
      cards.find((connector) => connector.id === selectedConnectorId) || null;
    if (directMatch) {
      return directMatch;
    }
    // Alias resolution — try common alternate IDs
    const aliases: Record<string, string[]> = {
      m365: ["microsoft_365"], microsoft_365: ["m365"],
      google_workspace: ["gmail", "google_drive"],
    };
    for (const alt of aliases[selectedConnectorId] || []) {
      const match = cards.find((c) => c.id === alt);
      if (match) return match;
    }
    return null;
  }, [cards, selectedConnectorId]);

  const handlePermissionMatrixChange = useCallback(
    async (nextMatrix: Record<string, string[]>) => {
      const changedConnectorId = findChangedConnectorId(permissionMatrix, nextMatrix);
      setPermissionMatrix(nextMatrix);
      setPermissionError("");
      if (!changedConnectorId) {
        return;
      }
      setSavingPermissionFor(changedConnectorId);
      try {
        await patchConnectorBinding(changedConnectorId, {
          allowed_agent_ids: uniqueIds(nextMatrix[changedConnectorId] || []),
        });
      } catch (persistError) {
        setPermissionError(`Failed to save permissions: ${String(persistError)}`);
      } finally {
        setSavingPermissionFor(null);
      }
    },
    [permissionMatrix],
  );

  const googleAdvancedSettings = (
    <ConnectorGoogleAdvancedSettings
      visible={selectedConnector?.id === "google_workspace"}
      controller={connectorsController}
    />
  );

  return (
    <div className="h-full overflow-y-auto bg-[#f6f6f7] p-5">
      <div className="mx-auto flex w-full max-w-[1240px] flex-col gap-4">
        <section className="rounded-[20px] border border-black/[0.06] bg-white px-5 py-4">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#7c3aed]">
                Integrations
              </p>
              <h1 className="mt-1 text-[26px] font-semibold tracking-[-0.02em] text-[#1d1d1f]">
                Connectors
              </h1>
              <div className="mt-3 flex items-center gap-4 text-[12px] text-[#86868b]">
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-[#22c55e]" />
                  {stats.connected} connected
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-[#d4d4d8]" />
                  {stats.needsSetup} needs setup
                </span>
                {stats.attention > 0 ? (
                  <span className="inline-flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-[#f59e0b]" />
                    {stats.attention} attention
                  </span>
                ) : null}
                <span className="text-[#c7c7cc]">{stats.total} total</span>
              </div>
            </div>

            <div className="shrink-0 flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPermissionsOpen(true)}
                className="inline-flex items-center gap-2 rounded-xl border border-black/[0.06] bg-white px-3.5 py-2 text-[13px] font-medium text-[#1d1d1f] shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition-all hover:bg-[#f5f3ff] hover:border-[#c4b5fd] hover:text-[#7c3aed]"
              >
                <Shield size={14} />
                Permissions
              </button>
              <button
                type="button"
                onClick={() => void refresh()}
                disabled={loading}
                className="inline-flex items-center gap-2 rounded-xl border border-black/[0.06] bg-white px-3.5 py-2 text-[13px] font-medium text-[#1d1d1f] shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition-all hover:bg-[#f5f5f7] disabled:cursor-not-allowed disabled:opacity-50"
              >
                <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
                Refresh
              </button>
            </div>
          </div>
        </section>

        {error ? (
          <div className="rounded-2xl border border-[#fecaca] bg-[#fff5f5] px-4 py-3 text-[13px] text-[#9f1239]">
            {error}
          </div>
        ) : null}

        <ConnectorCatalogFilters
          activeFilter={activeFilter}
          activeSuite={activeSuite}
          filteredCount={filteredCards.length}
          suiteCounts={suiteCounts}
          onFilterChange={setActiveFilter}
          onSuiteChange={setActiveSuite}
        />

        <section className="space-y-4">
          {filteredSections.map((section) => (
            <ConnectorSuiteSection
              key={section.key}
              section={section}
              activeSuite={activeSuite}
              onOpenConnector={openConnectorDetail}
            />
          ))}
        </section>

        {filteredCards.length === 0 ? (
          <section className="rounded-2xl border border-black/[0.06] bg-white p-6 text-center text-[13px] text-[#86868b]">
            No connectors match this filter.
          </section>
        ) : null}
      </div>

      <ConnectorPermissionsModal
        open={permissionsOpen}
        connectors={cards}
        agents={matrixAgents}
        value={permissionMatrix}
        savingConnectorId={savingPermissionFor}
        error={permissionError}
        onClose={() => setPermissionsOpen(false)}
        onChange={(next) => {
          void handlePermissionMatrixChange(next);
        }}
      />

      <ConnectorDetailPanel
        connector={selectedConnector}
        open={Boolean(selectedConnector)}
        onClose={closeConnectorDetail}
        onRefresh={refresh}
        advancedSettings={googleAdvancedSettings}
        permissionAgents={matrixAgents}
        permissionValue={permissionMatrix}
        permissionSaving={
          Boolean(selectedConnector) && savingPermissionFor === selectedConnector?.id
        }
        permissionError={permissionError}
        onPermissionChange={handlePermissionMatrixChange}
      />
    </div>
  );
}
