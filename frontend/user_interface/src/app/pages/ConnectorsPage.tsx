import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";

import {
  listConnectorCredentials,
  listConnectorHealth,
  listConnectorPlugins,
  type ConnectorCredentialRecord,
  type ConnectorPluginManifest,
} from "../../api/client";
import { MANUAL_CONNECTOR_DEFINITIONS, type ConnectorDefinition } from "../components/settings/connectorDefinitions";
import { ConnectorDetailPanel } from "../components/connectors/ConnectorDetailPanel";
import { ToolPermissionMatrix } from "../components/connectors/ToolPermissionMatrix";
import { AGENT_OS_AGENTS, type ConnectorSummary } from "./agentOsData";

type ConnectorHealthEntry = {
  ok: boolean;
  message: string;
};

type ConnectorCardView = {
  id: string;
  label: string;
  description: string;
  authType: "oauth2" | "api_key" | "basic" | "none";
  status: "Connected" | "Not connected" | "Expired";
  statusMessage: string;
  actionsCount: number;
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

export function ConnectorsPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [plugins, setPlugins] = useState<ConnectorPluginManifest[]>([]);
  const [healthMap, setHealthMap] = useState<Record<string, ConnectorHealthEntry>>({});
  const [credentialMap, setCredentialMap] = useState<Record<string, ConnectorCredentialRecord>>({});
  const [selectedConnectorId, setSelectedConnectorId] = useState<string | null>(null);
  const [permissionMatrix, setPermissionMatrix] = useState<Record<string, string[]>>(() => {
    const baseline: Record<string, string[]> = {};
    for (const connector of AGENT_OS_CONNECTORS_FOR_MATRIX) {
      baseline[connector.id] = AGENT_OS_AGENTS
        .filter((agent) => agent.tools.some((tool) => connector.tools.includes(tool)))
        .map((agent) => agent.id);
    }
    return baseline;
  });

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [pluginRows, healthRows, credentialRows] = await Promise.all([
        listConnectorPlugins(),
        listConnectorHealth(),
        listConnectorCredentials(),
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

      setPlugins(Array.isArray(pluginRows) ? pluginRows : []);
      setHealthMap(nextHealthMap);
      setCredentialMap(nextCredentialMap);
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
    const allConnectorIds = new Set<string>([
      ...manualMap.keys(),
      ...pluginMap.keys(),
      ...Object.keys(healthMap),
      ...Object.keys(credentialMap),
    ]);

    return Array.from(allConnectorIds)
      .map((connectorId) => {
        const manual = manualMap.get(connectorId) || null;
        const plugin = pluginMap.get(connectorId) || null;
        const health = healthMap[connectorId] || null;
        const credential = credentialMap[connectorId] || null;
        const statusState = resolveStatus(health, credential);
        const actionCount = Array.isArray(plugin?.actions) ? plugin.actions.length : 0;
        return {
          id: connectorId,
          label: String(plugin?.label || manual?.label || humanizeConnectorId(connectorId)),
          description: String(
            manual?.description ||
              (actionCount > 0
                ? `${actionCount} runtime actions available for this connector.`
                : "Connector is registered and ready for credential setup."),
          ),
          authType: inferAuthType(manual),
          status: statusState.status,
          statusMessage: statusState.statusMessage,
          actionsCount: actionCount,
        };
      })
      .sort((left, right) => left.label.localeCompare(right.label));
  }, [credentialMap, healthMap, plugins]);

  const connectorSummariesForMatrix = useMemo<ConnectorSummary[]>(
    () =>
      cards.map((card) => ({
        id: card.id,
        name: card.label,
        description: card.description,
        authType: card.authType,
        status: card.status,
        tools: [],
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

  return (
    <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
      <div className="mx-auto flex w-full max-w-[1240px] flex-col gap-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5 shadow-[0_20px_60px_rgba(15,23,42,0.10)]">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[#667085]">Connectors</p>
              <h1 className="mt-1 text-[34px] font-semibold tracking-[-0.02em] text-[#101828]">Integration Control Center</h1>
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
          </div>
          <ToolPermissionMatrix
            agents={AGENT_OS_AGENTS}
            connectors={connectorSummariesForMatrix}
            value={permissionMatrix}
            onChange={setPermissionMatrix}
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

const AGENT_OS_CONNECTORS_FOR_MATRIX: Array<Pick<ConnectorSummary, "id" | "tools">> = [
  { id: "google_workspace", tools: ["gmail.send", "gdrive.read_file", "gcalendar.create_event"] },
  { id: "slack", tools: ["slack.send_message", "slack.list_channels"] },
  { id: "salesforce", tools: ["crm.get_deal", "crm.update_deal", "crm.list_deals_by_stage"] },
  { id: "notion", tools: ["notion.read_page", "notion.create_page", "notion.update_page"] },
  { id: "github", tools: ["vcs.create_pr", "vcs.list_issues", "vcs.create_issue"] },
];
