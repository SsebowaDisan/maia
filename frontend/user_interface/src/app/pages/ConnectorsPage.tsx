import { useCallback, useEffect, useMemo, useState } from "react";
import { PlugZap, RefreshCw, Search, Shield } from "lucide-react";

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
import { ConnectorBrandIcon } from "../components/connectors/ConnectorBrandIcon";
import { ConnectorDetailPanel } from "../components/connectors/ConnectorDetailPanel";
import { ConnectorGoogleAdvancedSettings } from "../components/connectors/ConnectorGoogleAdvancedSettings";
import { ConnectorPermissionsModal } from "../components/connectors/ConnectorPermissionsModal";
import {
  buildConnectorStats,
  buildConnectorSummaries,
  findChangedConnectorId,
  isBindingMissingError,
  isNotFoundError,
  uniqueIds,
  type ConnectorCatalogRow,
  type ConnectorHealthEntry,
  type ConnectorListFilter,
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
    useState<ConnectorListFilter>("all");
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

  const [searchQuery, setSearchQuery] = useState("");
  const searchedCards = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return filteredCards;
    return filteredCards.filter((c) =>
      `${c.name} ${c.description} ${c.category}`.toLowerCase().includes(q),
    );
  }, [filteredCards, searchQuery]);

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto w-full max-w-[960px]">
        {/* Header */}
        <div className="mb-6 flex items-start gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[#f5f3ff]">
            <PlugZap size={22} className="text-[#7c3aed]" />
          </div>
          <div className="min-w-0 flex-1">
            <h1 className="text-[18px] font-semibold text-[#1d1d1f]">Which connector would you like to use?</h1>
            <p className="mt-1 text-[13px] text-[#86868b]">
              Connectors enhance your access to user data, app usage insights, and discoverability metrics.
            </p>
          </div>
        </div>

        {/* Search */}
        <div className="relative mb-5">
          <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#aeaeb2]" />
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search"
            className="w-full rounded-xl border border-black/[0.08] bg-white py-2.5 pl-10 pr-4 text-[14px] text-[#1d1d1f] outline-none placeholder:text-[#aeaeb2] focus:border-[#7c3aed]/40 focus:ring-2 focus:ring-[#7c3aed]/10"
          />
        </div>

        {error ? (
          <div className="mb-4 rounded-lg border border-[#fecaca] bg-[#fff5f5] px-3 py-2 text-[12px] text-[#9f1239]">
            {error}
          </div>
        ) : null}

        {/* Connector icon grid — reference design */}
        <div className="rounded-2xl border border-black/[0.06] bg-white">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4">
            {searchedCards.map((card, idx) => {
              const isConnected = card.status === "Connected";
              const needsAttention = card.status === "Expired" || card.status === "Needs permission";
              const isLastRow = idx >= searchedCards.length - (searchedCards.length % 4 || 4);
              const isLastInRow = (idx + 1) % 4 === 0;
              return (
                <button
                  key={card.id}
                  type="button"
                  onClick={() => openConnectorDetail(card.id)}
                  className={`group flex flex-col items-center gap-3 px-4 py-5 text-center transition-colors hover:bg-[#f8f8fa] ${
                    !isLastInRow ? "border-r border-black/[0.04]" : ""
                  } ${!isLastRow ? "border-b border-black/[0.04]" : ""}`}
                >
                  {/* Brand icon */}
                  <div className="transition-transform group-hover:scale-105">
                    <ConnectorBrandIcon
                      connectorId={card.id}
                      brandSlug={card.brandSlug || card.id}
                      label={card.name}
                      size={44}
                    />
                  </div>

                  {/* Name */}
                  <p className="text-[13px] font-semibold text-[#1d1d1f]">{card.name}</p>

                  {/* Action */}
                  <span className={`text-[12px] font-medium ${
                    isConnected
                      ? "text-[#059669]"
                      : needsAttention
                        ? "text-[#d97706]"
                        : "text-[#7c3aed]"
                  }`}>
                    {isConnected ? "Connected" : needsAttention ? "Reconnect" : "Select"}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {searchedCards.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-12 text-center">
            <p className="text-[14px] font-medium text-[#344054]">No connectors found</p>
            <button type="button" onClick={() => { setSearchQuery(""); setActiveFilter("all"); }} className="text-[12px] font-medium text-[#7c3aed] hover:underline">
              Clear search
            </button>
          </div>
        ) : null}

        {/* Footer actions */}
        <div className="mt-4 flex items-center justify-between">
          <button
            type="button"
            onClick={() => setPermissionsOpen(true)}
            className="text-[12px] font-medium text-[#86868b] transition hover:text-[#1d1d1f]"
          >
            <Shield size={12} className="mr-1 inline" />
            Manage permissions
          </button>
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={loading}
            className="text-[12px] font-medium text-[#86868b] transition hover:text-[#1d1d1f] disabled:opacity-50"
          >
            <RefreshCw size={12} className={`mr-1 inline ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
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
