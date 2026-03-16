import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BarChart3,
  Building2,
  CalendarDays,
  ChartSpline,
  MailCheck,
  MessageCircle,
  ReceiptText,
  RefreshCw,
  Search,
  Shield,
  X,
  type LucideIcon,
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
} from "../components/settings/tabs/integrations/googleServices";
import { IntegrationsSettings } from "../components/settings/tabs/IntegrationsSettings";
import { useSettingsController } from "../components/settings/useSettingsController";
import { ConnectorDetailPanel } from "../components/connectors/ConnectorDetailPanel";
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
type ConnectorSuiteSection = {
  key: ConnectorSuiteKey;
  label: string;
  description: string;
  cards: ConnectorCardView[];
};

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
    return {
      status: "Not connected",
      statusMessage: message || "Credential stored but test failed.",
    };
  }
  return {
    status: "Not connected",
    statusMessage: message || "No credential configured yet.",
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
    id.startsWith("google_") ||
    id === "googleworkspace" ||
    id === "google_workspace" ||
    id === "gmail" ||
    id === "gcalendar" ||
    id === "gdrive" ||
    id === "gdocs" ||
    id === "gsheets"
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

const PRIMARY_GOOGLE_SERVICE_IDS = ["gmail", "calendar", "drive", "docs", "sheets"] as const;
const CONNECTOR_ICON_MAP: Record<string, LucideIcon> = {
  bing_search: Search,
  email_validation: MailCheck,
  google_ads: ChartSpline,
  google_calendar: CalendarDays,
  google_workspace: CalendarDays,
  m365: Building2,
  invoice: ReceiptText,
  slack: MessageCircle,
  hubspot: BarChart3,
};

function buildGoogleSubServices(
  enabledServiceIds: string[],
  selectedServiceIds: string[],
): ConnectorSubService[] {
  const enabled = new Set(normalizeServiceIds(enabledServiceIds));
  const selected = new Set(normalizeServiceIds(selectedServiceIds));
  const preferred = new Set<string>(PRIMARY_GOOGLE_SERVICE_IDS);
  const extras = uniqueIds([...enabled, ...selected]).filter((id) => !preferred.has(id));
  const orderedIds = [...PRIMARY_GOOGLE_SERVICE_IDS, ...extras];

  return orderedIds
    .map((id) => GOOGLE_SERVICE_DEFS.find((definition) => definition.id === id))
    .filter((definition): definition is (typeof GOOGLE_SERVICE_DEFS)[number] => Boolean(definition))
    .map((definition) => ({
      id: definition.id,
      label: definition.label,
      description: definition.description,
      status: enabled.has(definition.id)
        ? "Connected"
        : selected.has(definition.id)
          ? "Needs permission"
          : "Disabled",
    }));
}

function renderConnectorAvatar(connectorId: string, label: string) {
  const Icon = CONNECTOR_ICON_MAP[String(connectorId || "").trim().toLowerCase()];
  if (Icon) {
    return <Icon size={16} strokeWidth={2.1} className="text-[#344054]" />;
  }
  return (
    <span className="text-[13px] font-semibold text-[#344054]">
      {String(label || "?").slice(0, 1).toUpperCase()}
    </span>
  );
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

  const googleSubServices = useMemo(
    () => buildGoogleSubServices(googleEnabledServiceIds, googleSelectedServiceIds),
    [googleEnabledServiceIds, googleSelectedServiceIds],
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
        const statusState = resolveStatus(health, credential);
        const actionCount = Array.isArray(plugin?.actions)
          ? plugin.actions.length
          : 0;
        const tools = uniqueIds(
          (plugin?.actions || []).flatMap((action) =>
            Array.isArray(action.tool_ids) ? action.tool_ids : [],
          ),
        );
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
          authType: inferAuthType(manual, catalogAuthKinds[connectorId]),
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

  const filteredSections = useMemo<ConnectorSuiteSection[]>(() => {
    const grouped: Record<ConnectorSuiteKey, ConnectorCardView[]> = {
      google_workspace: [],
      microsoft_365: [],
      standalone: [],
    };
    for (const card of filteredCards) {
      grouped[resolveConnectorSuite(card.id)].push(card);
    }
    const definitions: Omit<ConnectorSuiteSection, "cards">[] = [
      {
        key: "google_workspace",
        label: "Google Workspace",
        description: "Connect once, then enable Google services inside this suite.",
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
    return definitions
      .map((definition) => ({
        ...definition,
        cards: grouped[definition.key].sort((left, right) =>
          left.label.localeCompare(right.label),
        ),
      }))
      .filter((section) => section.cards.length > 0);
  }, [filteredCards]);

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
    <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
      <div className="mx-auto flex w-full max-w-[1240px] flex-col gap-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5 shadow-[0_20px_60px_rgba(15,23,42,0.10)]">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[#667085]">
                Connectors
              </p>
              <h1 className="mt-1 text-[30px] font-semibold tracking-[-0.02em] text-[#101828]">
                Connector Control Center
              </h1>
              <p className="mt-2 text-[14px] leading-[1.55] text-[#475467]">
                Focus on what needs action first, then open details only when needed.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPermissionsOpen(true)}
                className="inline-flex items-center gap-2 rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[13px] font-semibold text-[#111827] transition hover:border-black/[0.24]"
              >
                <Shield size={14} />
                Permissions
              </button>
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
          </div>
        </section>

        {error ? (
          <div className="rounded-2xl border border-[#fecaca] bg-[#fff5f5] px-4 py-3 text-[13px] text-[#9f1239]">
            {error}
          </div>
        ) : null}

        <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <article className="rounded-2xl border border-black/[0.08] bg-white px-4 py-3">
            <p className="text-[12px] text-[#667085]">Connected</p>
            <p className="mt-1 text-[26px] font-semibold tracking-[-0.02em] text-[#101828]">
              {stats.connected}
            </p>
          </article>
          <article className="rounded-2xl border border-black/[0.08] bg-white px-4 py-3">
            <p className="text-[12px] text-[#667085]">Needs setup</p>
            <p className="mt-1 text-[26px] font-semibold tracking-[-0.02em] text-[#101828]">
              {stats.needsSetup}
            </p>
          </article>
          <article className="rounded-2xl border border-black/[0.08] bg-white px-4 py-3">
            <p className="text-[12px] text-[#667085]">Attention</p>
            <p className="mt-1 text-[26px] font-semibold tracking-[-0.02em] text-[#101828]">
              {stats.attention}
            </p>
          </article>
          <article className="rounded-2xl border border-black/[0.08] bg-white px-4 py-3">
            <p className="text-[12px] text-[#667085]">Total</p>
            <p className="mt-1 text-[26px] font-semibold tracking-[-0.02em] text-[#101828]">
              {stats.total}
            </p>
          </article>
        </section>

        <section className="rounded-[22px] border border-black/[0.08] bg-white p-3">
          <div className="flex flex-wrap items-center gap-2">
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
                className={`rounded-full px-3 py-1.5 text-[12px] font-semibold ${
                  activeFilter === value
                    ? "bg-[#111827] text-white"
                    : "border border-black/[0.12] bg-white text-[#344054]"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </section>

        <section className="space-y-4">
          {filteredSections.map((section) => (
            <article
              key={section.key}
              className="rounded-[22px] border border-black/[0.08] bg-white p-4"
            >
              <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
                <div>
                  <h2 className="text-[16px] font-semibold tracking-[-0.01em] text-[#111827]">
                    {section.label}
                  </h2>
                  <p className="mt-1 text-[12px] text-[#667085]">{section.description}</p>
                </div>
                <span className="rounded-full border border-black/[0.08] bg-[#f8fafc] px-2.5 py-1 text-[11px] font-semibold text-[#475467]">
                  {section.cards.length} connector{section.cards.length === 1 ? "" : "s"}
                </span>
              </div>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
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
                    className="rounded-[20px] border border-black/[0.08] bg-white p-4 shadow-[0_10px_28px_rgba(15,23,42,0.06)]"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-black/[0.08] bg-[#f8fafc] text-[13px] font-semibold text-[#344054]">
                        {renderConnectorAvatar(connector.id, connector.label)}
                      </div>
                      <span
                        className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${statusPillClass(connector.status)}`}
                      >
                        {connector.status}
                      </span>
                    </div>
                    <h3 className="mt-3 text-[17px] font-semibold tracking-[-0.01em] text-[#101828]">
                      {connector.label}
                    </h3>
                    <p className="mt-1 min-h-[40px] text-[13px] leading-[1.5] text-[#475467]">
                      {connector.description}
                    </p>
                    <p className="mt-2 text-[12px] text-[#667085]">{connector.statusMessage}</p>
                    {connector.subServices && connector.subServices.length > 0 ? (
                      <div className="mt-3 rounded-xl border border-black/[0.08] bg-[#f8fafc] p-2.5">
                        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#667085]">
                          Services
                        </p>
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {connector.subServices.map((service) => (
                            <span
                              key={service.id}
                              className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-[10px] font-semibold ${serviceStatusPillClass(service.status)}`}
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
                      <span className="text-[11px] uppercase tracking-[0.08em] text-[#98a2b3]">
                        {connector.authType}
                      </span>
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          setSelectedConnectorId(connector.id);
                        }}
                        className="rounded-full border border-black/[0.12] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#344054]"
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
          <section className="rounded-2xl border border-black/[0.08] bg-white p-4 text-[13px] text-[#667085]">
            No connectors in this view yet.
          </section>
        ) : null}
      </div>

      {permissionsOpen ? (
        <div className="fixed inset-0 z-[130] bg-black/35 backdrop-blur-[3px]">
          <div className="absolute left-1/2 top-1/2 max-h-[86vh] w-[min(1080px,94vw)] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-[24px] border border-black/[0.08] bg-white shadow-[0_26px_68px_rgba(15,23,42,0.28)]">
            <div className="flex items-start justify-between border-b border-black/[0.08] px-5 py-4">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#667085]">
                  Access control
                </p>
                <h2 className="mt-1 text-[22px] font-semibold text-[#111827]">
                  Agent permissions by connector
                </h2>
              </div>
              <button
                type="button"
                onClick={() => setPermissionsOpen(false)}
                className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-black/[0.1] text-[#667085]"
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
