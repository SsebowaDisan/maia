import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";

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
import { MANUAL_CONNECTOR_DEFINITIONS, type ConnectorDefinition } from "../components/settings/connectorDefinitions";
import { IntegrationsSettings } from "../components/settings/tabs/IntegrationsSettings";
import { useSettingsController } from "../components/settings/useSettingsController";
import { ConnectorDetailPanel } from "../components/connectors/ConnectorDetailPanel";
import { ToolPermissionMatrix } from "../components/connectors/ToolPermissionMatrix";

type ConnectorHealthEntry = {
  ok: boolean;
  message: string;
};

type ConnectorSummary = {
  id: string;
  name: string;
  description: string;
  authType: "oauth2" | "api_key" | "basic" | "none";
  status: "Connected" | "Not connected" | "Expired";
  tools: string[];
};

type ConnectorCardView = {
  id: string;
  label: string;
  description: string;
  authType: "oauth2" | "api_key" | "basic" | "none";
  status: "Connected" | "Not connected" | "Expired";
  statusMessage: string;
  actionsCount: number;
  tools: string[];
};

function humanizeConnectorId(id: string): string {
  return id
    .split(/[_-]+/g)
    .filter(Boolean)
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");
}

function inferAuthType(definition: ConnectorDefinition | null): ConnectorCardView["authType"] {
  if (!definition) {
    return "none";
  }
  const keys = definition.fields.map((field) => String(field.key || "").toUpperCase());
  if (keys.some((key) => key.includes("PASSWORD"))) {
    return "basic";
  }
  if (keys.some((key) => key.includes("TOKEN") || key.includes("API_KEY") || key.endsWith("_KEY"))) {
    return "api_key";
  }
  return definition.fields.length ? "api_key" : "none";
}

function resolveStatus(
  health: ConnectorHealthEntry | null,
  credential: ConnectorCredentialRecord | null,
): { status: ConnectorCardView["status"]; statusMessage: string } {
  const message = String(health?.message || "").trim();
  if (health?.ok) {
    return { status: "Connected", statusMessage: message || "Connection healthy." };
  }
  if (credential) {
    if (/(expired|refresh|unauthorized|forbidden|invalid)/i.test(message)) {
      return { status: "Expired", statusMessage: message || "Credential needs refresh." };
    }
    return { status: "Not connected", statusMessage: message || "Credential stored but test failed." };
  }
  return { status: "Not connected", statusMessage: message || "No credential configured yet." };
}

function statusPillClass(status: ConnectorCardView["status"]): string {
  if (status === "Connected") {
    return "border-[#c7ead8] bg-[#edf9f2] text-[#166534]";
  }
  if (status === "Expired") {
    return "border-[#fbd38d] bg-[#fff7ed] text-[#9a3412]";
  }
  return "border-[#d0d5dd] bg-[#f8fafc] text-[#475467]";
}

function uniqueIds(values: string[]): string[] {
  return Array.from(new Set(values.map((item) => String(item || "").trim()).filter(Boolean)));
}

function sameIdList(left: string[], right: string[]): boolean {
  const a = [...uniqueIds(left)].sort();
  const b = [...uniqueIds(right)].sort();
  if (a.length !== b.length) {
    return false;
  }
  return a.every((value, index) => value === b[index]);
}

function findChangedConnectorId(
  previous: Record<string, string[]>,
  next: Record<string, string[]>,
): string | null {
  const keys = uniqueIds([...Object.keys(previous), ...Object.keys(next)]);
  for (const key of keys) {
    if (!sameIdList(previous[key] || [], next[key] || [])) {
      return key;
    }
  }
  return null;
}

function isBindingMissingError(error: unknown): boolean {
  const text = String(error || "").toLowerCase();
  return text.includes("no binding found") || text.includes("not found") || text.includes("request failed: 404");
}

export function ConnectorsPage() {
  const connectorsController = useSettingsController("connectors");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [plugins, setPlugins] = useState<ConnectorPluginManifest[]>([]);
  const [healthMap, setHealthMap] = useState<Record<string, ConnectorHealthEntry>>({});
  const [credentialMap, setCredentialMap] = useState<Record<string, ConnectorCredentialRecord>>({});
  const [catalogDescriptions, setCatalogDescriptions] = useState<Record<string, string>>({});
  const [agents, setAgents] = useState<AgentSummaryRecord[]>([]);
  const [selectedConnectorId, setSelectedConnectorId] = useState<string | null>(null);
  const [permissionMatrix, setPermissionMatrix] = useState<Record<string, string[]>>({});
  const [savingPermissionFor, setSavingPermissionFor] = useState<string | null>(null);
  const [permissionError, setPermissionError] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    setPermissionError("");
    try {
      const [pluginRows, healthRows, credentialRows, agentRows, connectorCatalog] = await Promise.all([
        listConnectorPlugins(),
        listConnectorHealth(),
        listConnectorCredentials(),
        listAgents(),
        listConnectorCatalog(),
      ]);

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

      const nextCatalogDescriptions: Record<string, string> = {};
      for (const row of connectorCatalog || []) {
        const connectorId = String(row?.id || "").trim();
        if (!connectorId) {
          continue;
        }
        nextCatalogDescriptions[connectorId] = String(row?.description || "").trim();
      }

      const allConnectorIds = uniqueIds([
        ...MANUAL_CONNECTOR_DEFINITIONS.map((definition) => definition.id),
        ...(pluginRows || []).map((plugin) => plugin.connector_id),
        ...Object.keys(nextHealthMap),
        ...Object.keys(nextCredentialMap),
        ...Object.keys(nextCatalogDescriptions),
      ]);

      const defaultAllowedAgentIds = (agentRows || []).map((agent) => agent.agent_id);
      const bindingEntries = await Promise.all(
        allConnectorIds.map(async (connectorId) => {
          try {
            const binding = await getConnectorBinding(connectorId);
            const allowed = uniqueIds(binding.allowed_agent_ids || []);
            return [connectorId, allowed.length > 0 ? allowed : defaultAllowedAgentIds] as const;
          } catch (bindingError) {
            if (isBindingMissingError(bindingError)) {
              return [connectorId, defaultAllowedAgentIds] as const;
            }
            throw bindingError;
          }
        }),
      );

      setPlugins(Array.isArray(pluginRows) ? pluginRows : []);
      setHealthMap(nextHealthMap);
      setCredentialMap(nextCredentialMap);
      setCatalogDescriptions(nextCatalogDescriptions);
      setAgents(Array.isArray(agentRows) ? agentRows : []);
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

  const cards = useMemo<ConnectorCardView[]>(() => {
    const manualMap = new Map<string, ConnectorDefinition>(
      MANUAL_CONNECTOR_DEFINITIONS.map((definition) => [definition.id, definition]),
    );
    const pluginMap = new Map<string, ConnectorPluginManifest>(
      plugins.map((plugin) => [plugin.connector_id, plugin]),
    );
    const allConnectorIds = uniqueIds([
      ...manualMap.keys(),
      ...pluginMap.keys(),
      ...Object.keys(healthMap),
      ...Object.keys(credentialMap),
      ...Object.keys(catalogDescriptions),
    ]);

    return allConnectorIds
      .map((connectorId) => {
        const manual = manualMap.get(connectorId) || null;
        const plugin = pluginMap.get(connectorId) || null;
        const health = healthMap[connectorId] || null;
        const credential = credentialMap[connectorId] || null;
        const statusState = resolveStatus(health, credential);
        const actionCount = Array.isArray(plugin?.actions) ? plugin.actions.length : 0;
        const tools = uniqueIds(
          (plugin?.actions || []).flatMap((action) =>
            Array.isArray(action.tool_ids) ? action.tool_ids : [],
          ),
        );
        const catalogDescription = catalogDescriptions[connectorId] || "";
        return {
          id: connectorId,
          label: String(plugin?.label || manual?.label || humanizeConnectorId(connectorId)),
          description: String(
            catalogDescription ||
              manual?.description ||
              (actionCount > 0
                ? `${actionCount} runtime actions available for this connector.`
                : "Connector is registered and ready for credential setup."),
          ),
          authType: inferAuthType(manual),
          status: statusState.status,
          statusMessage: statusState.statusMessage,
          actionsCount: actionCount,
          tools,
        };
      })
      .sort((left, right) => left.label.localeCompare(right.label));
  }, [catalogDescriptions, credentialMap, healthMap, plugins]);

  const matrixAgents = useMemo(
    () =>
      agents.map((agent) => ({
        id: agent.agent_id,
        name: agent.name,
      })),
    [agents],
  );

  const connectorSummariesForMatrix = useMemo<ConnectorSummary[]>(
    () =>
      cards.map((card) => ({
        id: card.id,
        name: card.label,
        description: card.description,
        authType: card.authType,
        status: card.status,
        tools: card.tools,
      })),
    [cards],
  );

  const selectedConnector = useMemo<ConnectorSummary | null>(() => {
    if (!selectedConnectorId) {
      return null;
    }
    return (
      connectorSummariesForMatrix.find((connector) => connector.id === selectedConnectorId) ||
      null
    );
  }, [connectorSummariesForMatrix, selectedConnectorId]);

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

  return (
    <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
      <div className="mx-auto flex w-full max-w-[1240px] flex-col gap-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5 shadow-[0_20px_60px_rgba(15,23,42,0.10)]">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[#667085]">Connectors</p>
              <h1 className="mt-1 text-[34px] font-semibold tracking-[-0.02em] text-[#101828]">Connector Control Center</h1>
              <p className="mt-2 text-[15px] leading-[1.55] text-[#475467]">
                Connect services, monitor health, and prepare connector access for agent workflows.
              </p>
            </div>
            <button
              type="button"
              onClick={() => void refresh()}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[13px] font-semibold text-[#111827] transition hover:border-black/[0.24] disabled:cursor-not-allowed disabled:opacity-60"
            >
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
              Refresh
            </button>
          </div>
        </section>

        {error ? (
          <div className="rounded-2xl border border-[#fecaca] bg-[#fff5f5] px-4 py-3 text-[13px] text-[#9f1239]">{error}</div>
        ) : null}

        <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {cards.map((connector) => (
            <article
              key={connector.id}
              role="button"
              tabIndex={0}
              onClick={() => setSelectedConnectorId(connector.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  setSelectedConnectorId(connector.id);
                }
              }}
              className="rounded-[22px] border border-black/[0.08] bg-white p-5 shadow-[0_14px_36px_rgba(15,23,42,0.08)]"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="truncate text-[18px] font-semibold tracking-[-0.01em] text-[#101828]">{connector.label}</h2>
                  <p className="mt-2 text-[13px] leading-[1.55] text-[#475467]">{connector.description}</p>
                </div>
                <div className="h-9 w-9 shrink-0 rounded-xl border border-black/[0.08] bg-[#f8fafc] text-center text-[13px] font-semibold leading-9 text-[#344054]">
                  {connector.label.slice(0, 1).toUpperCase()}
                </div>
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${statusPillClass(connector.status)}`}>
                  {connector.status}
                </span>
                <span className="rounded-full border border-[#d0d5dd] bg-white px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#475467]">
                  {connector.authType}
                </span>
                <span className="rounded-full border border-[#d0d5dd] bg-[#f8fafc] px-2.5 py-1 text-[11px] font-semibold text-[#475467]">
                  {connector.actionsCount} action{connector.actionsCount === 1 ? "" : "s"}
                </span>
              </div>
              <p className="mt-3 text-[12px] text-[#667085]">{connector.statusMessage}</p>
            </article>
          ))}
        </section>

        <section className="rounded-[24px] border border-black/[0.08] bg-white p-5 shadow-[0_14px_36px_rgba(15,23,42,0.08)]">
          <div className="mb-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#667085]">Tool access</p>
            <h3 className="mt-1 text-[20px] font-semibold tracking-[-0.02em] text-[#101828]">Agent permission matrix</h3>
            {savingPermissionFor ? (
              <p className="mt-1 text-[12px] text-[#667085]">Saving permission update for {savingPermissionFor}...</p>
            ) : null}
            {permissionError ? (
              <p className="mt-1 text-[12px] text-[#9f1239]">{permissionError}</p>
            ) : null}
          </div>
          <ToolPermissionMatrix
            agents={matrixAgents}
            connectors={connectorSummariesForMatrix}
            value={permissionMatrix}
            onChange={(next) => {
              void handlePermissionMatrixChange(next);
            }}
          />
        </section>

        <section className="rounded-[24px] border border-black/[0.08] bg-white p-5 shadow-[0_14px_36px_rgba(15,23,42,0.08)]">
          <div className="mb-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#667085]">
              OAuth and Access
            </p>
            <h3 className="mt-1 text-[20px] font-semibold tracking-[-0.02em] text-[#101828]">
              Connected Services
            </h3>
            <p className="mt-1 text-[13px] leading-[1.55] text-[#667085]">
              Manage Google OAuth, service-account access, GA4 property, and workspace aliases directly here.
            </p>
          </div>

          <IntegrationsSettings
            googleOAuthStatus={connectorsController.googleOAuthStatus}
            googleServiceAccountStatus={connectorsController.googleServiceAccountStatus}
            googleWorkspaceAliases={connectorsController.googleWorkspaceAliases}
            oauthStatus={connectorsController.oauthStatus}
            oauthClientIdInput={connectorsController.oauthClientIdInput}
            oauthClientSecretInput={connectorsController.oauthClientSecretInput}
            oauthRedirectUriInput={connectorsController.oauthRedirectUriInput}
            oauthConfigSaving={connectorsController.oauthConfigSaving}
            googleToolHealth={connectorsController.googleToolHealth}
            liveEvents={connectorsController.liveEvents}
            onConnectGoogle={(options) => connectorsController.handleGoogleOAuthConnect(options)}
            onDisconnectGoogle={() => void connectorsController.handleGoogleOAuthDisconnect()}
            onOAuthClientIdInputChange={connectorsController.setOauthClientIdInput}
            onOAuthClientSecretInputChange={connectorsController.setOauthClientSecretInput}
            onOAuthRedirectUriInputChange={connectorsController.setOauthRedirectUriInput}
            onSaveGoogleOAuthConfig={() => void connectorsController.handleSaveGoogleOAuthConfig()}
            onRequestGoogleOAuthSetup={() => connectorsController.handleRequestGoogleOAuthSetup()}
            onSaveGoogleOAuthServices={(services) =>
              connectorsController.handleSaveGoogleOAuthServices(services)
            }
            onGoogleAuthModeChange={(mode) =>
              void connectorsController.handleGoogleWorkspaceAuthModeChange(mode)
            }
            onAnalyzeGoogleLink={(link) => connectorsController.handleAnalyzeGoogleWorkspaceLink(link)}
            onCheckGoogleLinkAccess={(payload) =>
              connectorsController.handleCheckGoogleWorkspaceLinkAccess(payload)
            }
            onSaveGoogleLinkAlias={(alias, link) =>
              connectorsController.handleSaveGoogleWorkspaceLinkAlias(alias, link)
            }
            ga4PropertyId={connectorsController.ga4PropertyId}
            ga4PropertyIdInput={connectorsController.ga4PropertyIdInput}
            onGa4PropertyIdInputChange={connectorsController.setGa4PropertyIdInput}
            onSaveGa4PropertyId={() => connectorsController.handleSaveGa4PropertyId()}
          />
        </section>
      </div>

      <ConnectorDetailPanel
        connector={selectedConnector}
        open={Boolean(selectedConnector)}
        onClose={() => setSelectedConnectorId(null)}
        onRefresh={refresh}
      />
    </div>
  );
}
