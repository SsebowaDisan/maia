import { useCallback, useEffect, useMemo, useState } from "react";
import {
  RefreshCw,
  Shield,
  X,
} from "lucide-react";

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
import {
  MANUAL_CONNECTOR_DEFINITIONS,
  type ConnectorDefinition,
} from "../components/settings/connectorDefinitions";
import {
  GOOGLE_SERVICE_DEFS,
  normalizeServiceIds,
  serviceIdsFromScopes,
  type GoogleServiceDefinition,
} from "../components/settings/tabs/integrations/googleServices";
import { IntegrationsSettings } from "../components/settings/tabs/IntegrationsSettings";
import { useSettingsController } from "../components/settings/useSettingsController";
import { ConnectorDetailPanel } from "../components/connectors/ConnectorDetailPanel";
import { ConnectorBrandIcon } from "../components/connectors/ConnectorBrandIcon";
import { ToolPermissionMatrix } from "../components/connectors/ToolPermissionMatrix";
import type { ConnectorSubService, ConnectorSummary } from "../types/connectorSummary";

type ConnectorHealthEntry = {
  ok: boolean;
  message: string;
};

type ConnectorCardView = {
  id: string;
  label: string;
  description: string;
  authType: ConnectorSummary["authType"];
  status: ConnectorSummary["status"];
  statusMessage: string;
  actionsCount: number;
  tools: string[];
  subServices?: ConnectorSubService[];
};

type ConnectorListFilter = "needs_setup" | "connected" | "attention" | "all";
type ConnectorSuiteKey = "google_workspace" | "microsoft_365" | "standalone";
type ConnectorSuiteFilter = "all" | ConnectorSuiteKey;
type ConnectorSuiteSection = {
  key: ConnectorSuiteKey;
  label: string;
  description: string;
  cards: ConnectorCardView[];
};

const SUITE_DEFINITIONS: Omit<ConnectorSuiteSection, "cards">[] = [
  {
    key: "google_workspace",
    label: "Google Suite",
    description: "Manage Google services from one connected suite.",
  },
  {
    key: "microsoft_365",
    label: "Microsoft 365",
    description: "Manage Outlook, OneDrive, and related Microsoft services together.",
  },
  {
    key: "standalone",
    label: "Standalone Connectors",
    description: "Independent services that are configured separately.",
  },
];

function humanizeConnectorId(id: string): string {
  return id
    .split(/[_-]+/g)
    .filter(Boolean)
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");
}

function normalizeAuthType(raw: unknown): ConnectorSummary["authType"] {
  const normalized = String(raw || "").trim().toLowerCase();
  if (normalized === "oauth2") {
    return "oauth2";
  }
  if (normalized === "api_key" || normalized === "apikey") {
    return "api_key";
  }
  if (normalized === "basic") {
    return "basic";
  }
  if (normalized === "none") {
    return "none";
  }
  return "none";
}

function inferAuthType(
  definition: ConnectorDefinition | null,
  authHint: unknown,
): ConnectorSummary["authType"] {
  const hinted = normalizeAuthType(authHint);
  if (hinted !== "none") {
    return hinted;
  }
  if (!definition) {
    return "none";
  }
  const keys = definition.fields.map((field) => String(field.key || "").toUpperCase());
  if (keys.some((key) => key.includes("PASSWORD"))) {
    return "basic";
  }
  if (
    keys.some(
      (key) =>
        key.includes("TOKEN") || key.includes("API_KEY") || key.endsWith("_KEY"),
    )
  ) {
    return "api_key";
  }
  return definition.fields.length ? "api_key" : "none";
}

function resolveStatus(
  authType: ConnectorSummary["authType"],
  health: ConnectorHealthEntry | null,
  credential: ConnectorCredentialRecord | null,
): { status: ConnectorCardView["status"]; statusMessage: string } {
  if (authType === "none") {
    return {
      status: "Connected",
      statusMessage: "Public connector (no credentials required).",
    };
  }
  const message = String(health?.message || "").trim();
  const normalizedMessage = message.toLowerCase();
  const cleanMessage =
    normalizedMessage === "configured" ? "Connected and ready." : message;
  if (health?.ok) {
    return {
      status: "Connected",
      statusMessage: cleanMessage || "Connection healthy.",
    };
  }
  if (credential) {
    if (/(expired|refresh|unauthorized|forbidden|invalid)/i.test(cleanMessage)) {
      return {
        status: "Expired",
        statusMessage: cleanMessage || "Credential needs refresh.",
      };
    }
    return {
      status: "Not connected",
      statusMessage: cleanMessage || "Credential stored but test failed.",
    };
  }
  return {
    status: "Not connected",
    statusMessage: cleanMessage || "No credential configured yet.",
  };
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

function serviceStatusPillClass(status: ConnectorSubService["status"]): string {
  if (status === "Connected") {
    return "border-[#c7ead8] bg-[#edf9f2] text-[#166534]";
  }
  if (status === "Needs permission") {
    return "border-[#fbd38d] bg-[#fff7ed] text-[#9a3412]";
  }
  return "border-[#d0d5dd] bg-[#f8fafc] text-[#667085]";
}

function matchesFilter(
  status: ConnectorCardView["status"],
  filter: ConnectorListFilter,
): boolean {
  if (filter === "all") {
    return true;
  }
  if (filter === "connected") {
    return status === "Connected";
  }
  if (filter === "attention") {
    return status === "Expired";
  }
  return status === "Not connected";
}

function primaryActionLabel(status: ConnectorCardView["status"]): string {
  if (status === "Connected") {
    return "Manage";
  }
  if (status === "Expired") {
    return "Reconnect";
  }
  return "Connect";
}

function resolveConnectorSuite(connectorId: string): ConnectorSuiteKey {
  const id = String(connectorId || "").trim().toLowerCase();
  if (
    GOOGLE_CONNECTOR_IDS.has(id) ||
    id.startsWith("google_") ||
    id.startsWith("gmail_") ||
    id === "googleworkspace"
  ) {
    return "google_workspace";
  }
  if (
    id === "m365" ||
    id.startsWith("m365_") ||
    id.startsWith("microsoft_") ||
    id.startsWith("office_") ||
    id.startsWith("outlook_") ||
    id.startsWith("onedrive_")
  ) {
    return "microsoft_365";
  }
  return "standalone";
}

function uniqueIds(values: string[]): string[] {
  return Array.from(
    new Set(values.map((item) => String(item || "").trim()).filter(Boolean)),
  );
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
  return (
    text.includes("no binding found") ||
    text.includes("not found") ||
    text.includes("request failed: 404")
  );
}

function isNotFoundError(error: unknown): boolean {
  const text = String(error || "").toLowerCase();
  return text.includes("404") || text.includes("not found");
}

const GOOGLE_CONNECTOR_IDS = new Set([
  "google_workspace",
  "google_calendar",
  "google_analytics",
  "google_ads",
  "google_maps",
  "google_api_hub",
  "google_docs",
  "google_sheets",
  "google_drive",
  "gmail",
  "gmail_playwright",
  "gcalendar",
  "gdrive",
  "gdocs",
  "gsheets",
]);

const PRIMARY_GOOGLE_SERVICE_IDS = [
  "gmail",
  "calendar",
  "drive",
  "docs",
  "sheets",
  "analytics",
] as const;

const GOOGLE_SERVICE_CONNECTOR_MAP: Record<
  GoogleServiceDefinition["id"],
  string[]
> = {
  gmail: ["gmail", "gmail_playwright", "google_workspace"],
  calendar: ["google_calendar", "gcalendar"],
  drive: ["google_workspace", "google_drive", "gdrive"],
  docs: ["google_workspace", "google_docs", "gdocs"],
  sheets: ["google_workspace", "google_sheets", "gsheets"],
  analytics: ["google_analytics"],
};

function buildGoogleSubServices(
  enabledServiceIds: string[],
  selectedServiceIds: string[],
  statusHints?: Partial<
    Record<GoogleServiceDefinition["id"], ConnectorSubService["status"]>
  >,
): ConnectorSubService[] {
  const enabled = new Set(normalizeServiceIds(enabledServiceIds));
  const selected = new Set(normalizeServiceIds(selectedServiceIds));
  const preferred = new Set<string>(PRIMARY_GOOGLE_SERVICE_IDS);
  const hintedIds = Object.keys(statusHints || {});
  const extras = uniqueIds([...enabled, ...selected, ...hintedIds]).filter(
    (id) => !preferred.has(id),
  );
  const orderedIds = [...PRIMARY_GOOGLE_SERVICE_IDS, ...extras];

  return orderedIds
    .map((id) => GOOGLE_SERVICE_DEFS.find((definition) => definition.id === id))
    .filter((definition): definition is (typeof GOOGLE_SERVICE_DEFS)[number] => Boolean(definition))
    .map((definition) => ({
      id: definition.id,
      label: definition.label,
      description: definition.description,
      status:
        statusHints?.[definition.id] ||
        (enabled.has(definition.id)
          ? "Connected"
          : selected.has(definition.id)
            ? "Needs permission"
            : "Disabled"),
    }));
}

function suiteAccentClass(suite: ConnectorSuiteKey): string {
  if (suite === "google_workspace") {
    return "bg-[#7c3aed]";
  }
  if (suite === "microsoft_365") {
    return "bg-[#0f766e]";
  }
  return "bg-[#6b7280]";
}

function suiteFilterLabel(value: ConnectorSuiteFilter): string {
  if (value === "all") {
    return "All suites";
  }
  const match = SUITE_DEFINITIONS.find((suite) => suite.key === value);
  return match ? match.label : value;
}

export function ConnectorsPage() {
  const connectorsController = useSettingsController("connectors");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [plugins, setPlugins] = useState<ConnectorPluginManifest[]>([]);
  const [healthMap, setHealthMap] = useState<Record<string, ConnectorHealthEntry>>({});
  const [credentialMap, setCredentialMap] = useState<
    Record<string, ConnectorCredentialRecord>
  >({});
  const [catalogDescriptions, setCatalogDescriptions] = useState<
    Record<string, string>
  >({});
  const [catalogAuthKinds, setCatalogAuthKinds] = useState<Record<string, string>>({});
  const [agents, setAgents] = useState<AgentSummaryRecord[]>([]);
  const [selectedConnectorId, setSelectedConnectorId] = useState<string | null>(null);
  const [permissionMatrix, setPermissionMatrix] = useState<Record<string, string[]>>({});
  const [savingPermissionFor, setSavingPermissionFor] = useState<string | null>(null);
  const [permissionError, setPermissionError] = useState("");
  const [activeFilter, setActiveFilter] = useState<ConnectorListFilter>("needs_setup");
  const [activeSuite, setActiveSuite] = useState<ConnectorSuiteFilter>("all");
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

  const googleServiceStatusHints = useMemo<
    Partial<Record<GoogleServiceDefinition["id"], ConnectorSubService["status"]>>
  >(() => {
    const hints: Partial<
      Record<GoogleServiceDefinition["id"], ConnectorSubService["status"]>
    > = {};
    for (const [serviceId, connectorIds] of Object.entries(
      GOOGLE_SERVICE_CONNECTOR_MAP,
    ) as Array<[GoogleServiceDefinition["id"], string[]]>) {
      const hasHealthyConnector = connectorIds.some(
        (connectorId) => Boolean(healthMap[connectorId]?.ok),
      );
      if (hasHealthyConnector) {
        hints[serviceId] = "Connected";
        continue;
      }
      const hasStoredCredential = connectorIds.some((connectorId) =>
        Boolean(credentialMap[connectorId]),
      );
      if (hasStoredCredential) {
        hints[serviceId] = "Needs permission";
      }
    }
    return hints;
  }, [credentialMap, healthMap]);

  const googleSubServices = useMemo(
    () =>
      buildGoogleSubServices(
        googleEnabledServiceIds,
        googleSelectedServiceIds,
        googleServiceStatusHints,
      ),
    [googleEnabledServiceIds, googleSelectedServiceIds, googleServiceStatusHints],
  );

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
        pluginRowsResult.status === "fulfilled" && Array.isArray(pluginRowsResult.value)
          ? pluginRowsResult.value
          : [];
      const healthRows =
        healthRowsResult.status === "fulfilled" && Array.isArray(healthRowsResult.value)
          ? healthRowsResult.value
          : [];
      const credentialRows =
        credentialRowsResult.status === "fulfilled" && Array.isArray(credentialRowsResult.value)
          ? credentialRowsResult.value
          : [];
      const agentRows =
        agentRowsResult.status === "fulfilled" && Array.isArray(agentRowsResult.value)
          ? agentRowsResult.value
          : [];
      const connectorCatalog =
        connectorCatalogResult.status === "fulfilled" &&
        Array.isArray(connectorCatalogResult.value)
          ? connectorCatalogResult.value
          : [];

      const hardFailure =
        pluginRowsResult.status === "rejected" &&
        healthRowsResult.status === "rejected" &&
        credentialRowsResult.status === "rejected";
      if (hardFailure) {
        throw pluginRowsResult.reason || healthRowsResult.reason || credentialRowsResult.reason;
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

      const nextCatalogDescriptions: Record<string, string> = {};
      const nextCatalogAuthKinds: Record<string, string> = {};
      for (const row of connectorCatalog || []) {
        const connectorId = String(row?.id || "").trim();
        if (!connectorId) {
          continue;
        }
        nextCatalogDescriptions[connectorId] = String(row?.description || "").trim();
        nextCatalogAuthKinds[connectorId] = String(row?.auth?.kind || "").trim();
      }

      const allConnectorIds = uniqueIds([
        ...(pluginRows || []).map((plugin) => plugin.connector_id),
        ...Object.keys(nextHealthMap),
        ...Object.keys(nextCredentialMap),
        ...Object.keys(nextCatalogDescriptions),
        "google_workspace",
      ]);

      const defaultAllowedAgentIds = (agentRows || []).map(
        (agent) => agent.agent_id,
      );
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
            if (isBindingMissingError(bindingError)) {
              return [connectorId, defaultAllowedAgentIds] as const;
            }
            if (isNotFoundError(bindingError)) {
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
      setCatalogAuthKinds(nextCatalogAuthKinds);
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
    const params = new URLSearchParams(window.location.search);
    const requestedConnectorId = String(params.get("connector") || "").trim();
    if (!requestedConnectorId) {
      return;
    }
    setSelectedConnectorId(requestedConnectorId);
  }, []);

  const cards = useMemo<ConnectorCardView[]>(() => {
    const manualMap = new Map<string, ConnectorDefinition>(
      MANUAL_CONNECTOR_DEFINITIONS.map((definition) => [definition.id, definition]),
    );
    const pluginMap = new Map<string, ConnectorPluginManifest>(
      plugins.map((plugin) => [plugin.connector_id, plugin]),
    );
    const allConnectorIds = uniqueIds([
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
        const actionCount = Array.isArray(plugin?.actions)
          ? plugin.actions.length
          : 0;
        const tools = uniqueIds(
          (plugin?.actions || []).flatMap((action) =>
            Array.isArray(action.tool_ids) ? action.tool_ids : [],
          ),
        );
        const authType = inferAuthType(manual, catalogAuthKinds[connectorId]);
        const statusState = resolveStatus(authType, health, credential);
        const catalogDescription = catalogDescriptions[connectorId] || "";
        const subServices =
          connectorId === "google_workspace" ? googleSubServices : undefined;
        const fallbackDescription =
          connectorId === "google_workspace"
            ? "Connect Gmail, Calendar, Drive, Docs, and Sheets in one place."
            : "Connector is registered and ready for setup.";
        return {
          id: connectorId,
          label: String(
            plugin?.label || manual?.label || humanizeConnectorId(connectorId),
          ),
          description: String(
            catalogDescription ||
              manual?.description ||
              (actionCount > 0
                ? `${actionCount} runtime actions available.`
                : fallbackDescription),
          ),
          authType,
          status: statusState.status,
          statusMessage: statusState.statusMessage,
          actionsCount: actionCount,
          tools,
          subServices,
        };
      })
      .sort((left, right) => left.label.localeCompare(right.label));
  }, [
    catalogAuthKinds,
    catalogDescriptions,
    credentialMap,
    googleSubServices,
    healthMap,
    plugins,
  ]);

  const stats = useMemo(
    () => ({
      connected: cards.filter((card) => card.status === "Connected").length,
      needsSetup: cards.filter((card) => card.status === "Not connected").length,
      attention: cards.filter((card) => card.status === "Expired").length,
      total: cards.length,
    }),
    [cards],
  );

  const filteredCards = useMemo(
    () => cards.filter((card) => matchesFilter(card.status, activeFilter)),
    [activeFilter, cards],
  );

  const suiteCounts = useMemo<Record<ConnectorSuiteKey, number>>(() => {
    const counts: Record<ConnectorSuiteKey, number> = {
      google_workspace: 0,
      microsoft_365: 0,
      standalone: 0,
    };
    for (const card of filteredCards) {
      counts[resolveConnectorSuite(card.id)] += 1;
    }
    return counts;
  }, [filteredCards]);

  const filteredSections = useMemo<ConnectorSuiteSection[]>(() => {
    const grouped: Record<ConnectorSuiteKey, ConnectorCardView[]> = {
      google_workspace: [],
      microsoft_365: [],
      standalone: [],
    };
    for (const card of filteredCards) {
      grouped[resolveConnectorSuite(card.id)].push(card);
    }
    return SUITE_DEFINITIONS
      .map((definition) => ({
        ...definition,
        cards: grouped[definition.key].sort((left, right) =>
          left.label.localeCompare(right.label),
        ),
      }))
      .filter((section) => activeSuite === "all" || section.key === activeSuite)
      .filter((section) => section.cards.length > 0);
  }, [activeSuite, filteredCards]);

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
        subServices: card.subServices,
      })),
    [cards],
  );

  const selectedConnector = useMemo<ConnectorSummary | null>(() => {
    if (!selectedConnectorId) {
      return null;
    }
    return (
      connectorSummariesForMatrix.find(
        (connector) => connector.id === selectedConnectorId,
      ) || null
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

  const googleAdvancedSettings =
    selectedConnector?.id === "google_workspace" ? (
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
        onConnectGoogle={(options) =>
          connectorsController.handleGoogleOAuthConnect(options)
        }
        onDisconnectGoogle={() =>
          void connectorsController.handleGoogleOAuthDisconnect()
        }
        onOAuthClientIdInputChange={connectorsController.setOauthClientIdInput}
        onOAuthClientSecretInputChange={connectorsController.setOauthClientSecretInput}
        onOAuthRedirectUriInputChange={connectorsController.setOauthRedirectUriInput}
        onSaveGoogleOAuthConfig={() =>
          void connectorsController.handleSaveGoogleOAuthConfig()
        }
        onRequestGoogleOAuthSetup={() =>
          connectorsController.handleRequestGoogleOAuthSetup()
        }
        onSaveGoogleOAuthServices={(services) =>
          connectorsController.handleSaveGoogleOAuthServices(services)
        }
        onGoogleAuthModeChange={(mode) =>
          void connectorsController.handleGoogleWorkspaceAuthModeChange(mode)
        }
        onAnalyzeGoogleLink={(link) =>
          connectorsController.handleAnalyzeGoogleWorkspaceLink(link)
        }
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
    ) : null;

  return (
    <div className="h-full overflow-y-auto bg-[#f6f6f7] p-5">
      <div className="mx-auto flex w-full max-w-[1240px] flex-col gap-4">
        {/* ── Header ──────────────────────────────────────────────── */}
        <section className="rounded-[20px] border border-black/[0.06] bg-white px-5 py-4">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#7c3aed]">Integrations</p>
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
            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={() => setPermissionsOpen(true)}
                className="inline-flex items-center gap-2 rounded-xl border border-black/[0.06] bg-white px-3.5 py-2 text-[13px] font-medium text-[#1d1d1f] shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition-all hover:bg-[#f5f3ff] hover:text-[#7c3aed] hover:border-[#c4b5fd]"
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

        {/* ── Filters ─────────────────────────────────────────────── */}
        <section className="rounded-[20px] border border-black/[0.06] bg-white px-4 py-3.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="mr-1 text-[11px] font-semibold uppercase tracking-[0.1em] text-[#86868b]">
              Status
            </span>
            {(
              [
                ["needs_setup", "Needs setup"],
                ["connected", "Connected"],
                ["attention", "Attention"],
                ["all", "All"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setActiveFilter(value)}
                className={`rounded-full px-3 py-1.5 text-[12px] font-medium transition-all ${
                  activeFilter === value
                    ? "bg-[#7c3aed] text-white shadow-[0_1px_3px_rgba(124,58,237,0.3)]"
                    : "border border-black/[0.06] bg-white text-[#3a3a40] hover:bg-[#f5f3ff] hover:text-[#7c3aed]"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-black/[0.04] pt-3">
            <span className="mr-1 text-[11px] font-semibold uppercase tracking-[0.1em] text-[#86868b]">
              Suite
            </span>
            {(["all", ...SUITE_DEFINITIONS.map((suite) => suite.key)] as const).map(
              (value) => {
                const count =
                  value === "all"
                    ? filteredCards.length
                    : suiteCounts[value as ConnectorSuiteKey];
                const isActive = activeSuite === value;
                return (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setActiveSuite(value)}
                    className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] font-medium transition-all ${
                      isActive
                        ? "bg-[#7c3aed] text-white shadow-[0_1px_3px_rgba(124,58,237,0.3)]"
                        : "border border-black/[0.06] bg-white text-[#3a3a40] hover:bg-[#f5f3ff] hover:text-[#7c3aed]"
                    }`}
                  >
                    {value !== "all" ? (
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${isActive ? "bg-white/60" : suiteAccentClass(value as ConnectorSuiteKey)}`}
                      />
                    ) : null}
                    <span>{suiteFilterLabel(value)}</span>
                    <span
                      className={`ml-0.5 text-[10px] tabular-nums ${
                        isActive ? "text-white/70" : "text-[#86868b]"
                      }`}
                    >
                      {count}
                    </span>
                  </button>
                );
              },
            )}
          </div>
        </section>

        {/* ── Connector grid ──────────────────────────────────────── */}
        <section className="space-y-4">
          {filteredSections.map((section) => (
            <article
              key={section.key}
              className="rounded-[20px] border border-black/[0.06] bg-white p-4"
            >
              {activeSuite === "all" ? (
                <div className="mb-4 flex items-center gap-2.5 px-1">
                  <span
                    className={`inline-block h-2 w-2 shrink-0 rounded-full ${suiteAccentClass(section.key)}`}
                  />
                  <h2 className="text-[15px] font-semibold tracking-[-0.01em] text-[#1d1d1f]">
                    {section.label}
                  </h2>
                  <span className="text-[12px] text-[#86868b]">
                    {section.cards.length}
                  </span>
                  <span className="ml-2 text-[12px] text-[#c7c7cc]">{section.description}</span>
                </div>
              ) : (
                <div className="mb-4 px-1">
                  <p className="text-[12px] text-[#86868b]">{section.description}</p>
                </div>
              )}
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                {section.cards.map((connector) => (
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
                    className="group rounded-2xl border border-black/[0.06] bg-white p-4 transition-all hover:border-[#c4b5fd] hover:shadow-[0_8px_24px_rgba(124,58,237,0.08)]"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="inline-flex h-10 w-10 items-center justify-center rounded-[12px] border border-black/[0.06] bg-[#fafafa]">
                        <ConnectorBrandIcon
                          connectorId={connector.id}
                          label={connector.label}
                          size={20}
                        />
                      </div>
                      <span
                        className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${statusPillClass(connector.status)}`}
                      >
                        {connector.status}
                      </span>
                    </div>
                    <h3 className="mt-3 text-[16px] font-semibold tracking-[-0.01em] text-[#1d1d1f]">
                      {connector.label}
                    </h3>
                    <p className="mt-1 min-h-[36px] text-[12px] leading-[1.5] text-[#86868b]">
                      {connector.description}
                    </p>
                    {connector.subServices && connector.subServices.length > 0 ? (
                      <div className="mt-3 rounded-xl border border-black/[0.04] bg-[#fafafa] p-2.5">
                        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#86868b]">
                          Services
                        </p>
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {connector.subServices.map((service) => (
                            <span
                              key={service.id}
                              className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-[10px] font-medium ${serviceStatusPillClass(service.status)}`}
                              title={service.description}
                            >
                              <span className="inline-block h-1.5 w-1.5 rounded-full bg-current/70" />
                              {service.label}
                            </span>
                          ))}
                        </div>
                      </div>
                    ) : null}
                    <div className="mt-3 flex items-center justify-between">
                      <span className="text-[11px] text-[#c7c7cc]">
                        {connector.authType}
                      </span>
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          setSelectedConnectorId(connector.id);
                        }}
                        className="rounded-full bg-[#f5f3ff] px-3 py-1.5 text-[12px] font-medium text-[#7c3aed] transition-colors hover:bg-[#ede9fe]"
                      >
                        {primaryActionLabel(connector.status)}
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            </article>
          ))}
        </section>

        {filteredCards.length === 0 ? (
          <section className="rounded-2xl border border-black/[0.06] bg-white p-6 text-center text-[13px] text-[#86868b]">
            No connectors match this filter.
          </section>
        ) : null}
      </div>

      {permissionsOpen ? (
        <div className="fixed inset-0 z-[130] bg-black/30 backdrop-blur-md">
          <div className="absolute left-1/2 top-1/2 max-h-[86vh] w-[min(1080px,94vw)] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-[20px] border border-white/20 bg-white/95 backdrop-blur-2xl shadow-[0_24px_80px_-16px_rgba(0,0,0,0.22),0_8px_24px_-8px_rgba(0,0,0,0.10)]">
            <div className="flex items-start justify-between border-b border-black/[0.06] px-5 py-4 bg-white/60 backdrop-blur-xl">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#7c3aed]">
                  Access control
                </p>
                <h2 className="mt-1 text-[20px] font-semibold text-[#1d1d1f]">
                  Agent permissions
                </h2>
              </div>
              <button
                type="button"
                onClick={() => setPermissionsOpen(false)}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[#86868b] transition-colors hover:bg-black/[0.05] hover:text-[#1d1d1f]"
                aria-label="Close permissions"
              >
                <X size={15} />
              </button>
            </div>
            <div className="space-y-3 overflow-y-auto px-5 py-4">
              {savingPermissionFor ? (
                <p className="text-[12px] text-[#667085]">
                  Saving permission update for {savingPermissionFor}...
                </p>
              ) : null}
              {permissionError ? (
                <p className="rounded-xl border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-[12px] text-[#9f1239]">
                  {permissionError}
                </p>
              ) : null}
              <ToolPermissionMatrix
                agents={matrixAgents}
                connectors={connectorSummariesForMatrix}
                value={permissionMatrix}
                onChange={(next) => {
                  void handlePermissionMatrixChange(next);
                }}
              />
            </div>
          </div>
        </div>
      ) : null}

      <ConnectorDetailPanel
        connector={selectedConnector}
        open={Boolean(selectedConnector)}
        onClose={() => setSelectedConnectorId(null)}
        onRefresh={refresh}
        advancedSettings={googleAdvancedSettings}
      />
    </div>
  );
}
