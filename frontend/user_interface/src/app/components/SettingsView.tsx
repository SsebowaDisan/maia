import { useEffect, useMemo, useState } from "react";

import {
  deleteConnectorCredentials,
  disconnectGoogleOAuth,
  getGoogleOAuthStatus,
  listConnectorCredentials,
  listConnectorHealth,
  startGoogleOAuth,
  subscribeAgentEvents,
  upsertConnectorCredentials,
  type AgentLiveEvent,
  type ConnectorCredentialRecord,
  type GoogleOAuthStatus,
} from "../../api/client";
import {
  clearMapsIntegrationKey,
  getBraveIntegrationStatus,
  getMapsIntegrationStatus,
  saveMapsIntegrationKey,
  type IntegrationStatus,
} from "../../api/integrations";
import {
  MANUAL_CONNECTOR_DEFINITIONS,
  type ConnectorDefinition,
} from "./settings/connectorDefinitions";
import { ManualConnectorCard } from "./settings/ManualConnectorCard";

type SettingsTab = "general" | "integrations";

function statusChip(ok: boolean | null) {
  if (ok === null) {
    return "border-[#d2d2d7] bg-white text-[#6e6e73]";
  }
  return ok
    ? "border-[#5f8a68] bg-[#f0f7f1] text-[#2d5937]"
    : "border-[#be7b7b] bg-[#f9efef] text-[#7a3030]";
}

function oauthBadge(connected: boolean) {
  return connected
    ? "border-[#5f8a68] bg-[#f0f7f1] text-[#2d5937]"
    : "border-[#be7b7b] bg-[#f9efef] text-[#7a3030]";
}

export function SettingsView() {
  const [activeSettingsTab, setActiveSettingsTab] = useState<SettingsTab>("integrations");
  const [healthMap, setHealthMap] = useState<Record<string, { ok: boolean; message: string }>>({});
  const [credentialMap, setCredentialMap] = useState<Record<string, ConnectorCredentialRecord>>({});
  const [draftValues, setDraftValues] = useState<Record<string, Record<string, string>>>({});
  const [loading, setLoading] = useState(false);
  const [savingConnectorId, setSavingConnectorId] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [oauthStatus, setOauthStatus] = useState("");
  const [googleOAuthStatus, setGoogleOAuthStatus] = useState<GoogleOAuthStatus>({
    connected: false,
    scopes: [],
  });
  const [mapsStatus, setMapsStatus] = useState<IntegrationStatus>({ configured: false, source: null });
  const [braveStatus, setBraveStatus] = useState<IntegrationStatus>({ configured: false, source: null });
  const [mapsKeyInput, setMapsKeyInput] = useState("");
  const [liveEvents, setLiveEvents] = useState<AgentLiveEvent[]>([]);

  const integrationCount = useMemo(() => MANUAL_CONNECTOR_DEFINITIONS.length, []);
  const googleToolHealth = useMemo(() => {
    const ids = ["gmail", "google_calendar", "google_workspace", "google_analytics"];
    return ids.map((id) => ({
      id,
      label: id.replace(/_/g, " "),
      ok: healthMap[id]?.ok ?? false,
      message: healthMap[id]?.message ?? "",
    }));
  }, [healthMap]);

  const refreshIntegrations = async () => {
    setLoading(true);
    try {
      const [healthRows, credentialRows, oauthRow, mapsRow, braveRow] = await Promise.all([
        listConnectorHealth(),
        listConnectorCredentials(),
        getGoogleOAuthStatus(),
        getMapsIntegrationStatus(),
        getBraveIntegrationStatus(),
      ]);

      const nextHealthMap: Record<string, { ok: boolean; message: string }> = {};
      for (const item of healthRows) {
        const connectorId = String(item.connector_id || "");
        if (!connectorId) {
          continue;
        }
        nextHealthMap[connectorId] = {
          ok: Boolean(item.ok),
          message: String(item.message || ""),
        };
      }
      setHealthMap(nextHealthMap);

      const nextCredentialMap: Record<string, ConnectorCredentialRecord> = {};
      for (const row of credentialRows) {
        nextCredentialMap[row.connector_id] = row;
      }
      setCredentialMap(nextCredentialMap);
      setGoogleOAuthStatus(oauthRow);
      setMapsStatus(mapsRow);
      setBraveStatus(braveRow);
      setStatusMessage("Integration status synced.");
    } catch (error) {
      setStatusMessage(`Failed to load integration status: ${String(error)}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refreshIntegrations();
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const oauthResult = params.get("oauth");
    if (!oauthResult) {
      return;
    }
    const oauthCode = params.get("code") || "";
    const oauthMessage = params.get("message") || "";
    if (oauthResult === "success") {
      setOauthStatus("Google OAuth connected successfully.");
    } else {
      const pieces = [oauthCode, oauthMessage].filter(Boolean).join(" - ");
      setOauthStatus(`Google OAuth failed${pieces ? `: ${pieces}` : "."}`);
    }
    params.delete("oauth");
    params.delete("code");
    params.delete("message");
    const nextSearch = params.toString();
    const nextUrl = `${window.location.pathname}${nextSearch ? `?${nextSearch}` : ""}`;
    window.history.replaceState({}, "", nextUrl);
    void refreshIntegrations();
  }, []);

  useEffect(() => {
    const unsubscribe = subscribeAgentEvents({
      replay: 30,
      onEvent: (event) => {
        setLiveEvents((previous) => [event, ...previous].slice(0, 80));
      },
      onError: () => {
        setOauthStatus((prev) =>
          prev || "Live events stream disconnected. It will reconnect on page refresh.",
        );
      },
    });
    return () => {
      unsubscribe();
    };
  }, []);

  const handleDraftChange = (connectorId: string, key: string, value: string) => {
    setDraftValues((prev) => ({
      ...prev,
      [connectorId]: {
        ...(prev[connectorId] || {}),
        [key]: value,
      },
    }));
  };

  const handleSaveConnector = async (connector: ConnectorDefinition) => {
    const draft = draftValues[connector.id] || {};
    const payload: Record<string, string> = {};
    for (const field of connector.fields) {
      const value = String(draft[field.key] || "").trim();
      if (!value) {
        continue;
      }
      payload[field.key] = value;
    }

    if (!Object.keys(payload).length) {
      setStatusMessage(`No values entered for ${connector.label}.`);
      return;
    }

    setSavingConnectorId(connector.id);
    try {
      await upsertConnectorCredentials(connector.id, payload);
      setDraftValues((prev) => ({ ...prev, [connector.id]: {} }));
      await refreshIntegrations();
      setStatusMessage(`${connector.label} credentials saved.`);
    } catch (error) {
      setStatusMessage(`Failed to save ${connector.label}: ${String(error)}`);
    } finally {
      setSavingConnectorId(null);
    }
  };

  const handleClearConnector = async (connector: ConnectorDefinition) => {
    setSavingConnectorId(connector.id);
    try {
      await deleteConnectorCredentials(connector.id);
      await refreshIntegrations();
      setStatusMessage(`${connector.label} credentials removed.`);
    } catch (error) {
      setStatusMessage(`Failed to clear ${connector.label}: ${String(error)}`);
    } finally {
      setSavingConnectorId(null);
    }
  };

  const handleGoogleOAuthConnect = async () => {
    try {
      const payload = await startGoogleOAuth();
      window.location.assign(payload.authorize_url);
    } catch (error) {
      setOauthStatus(`OAuth setup error: ${String(error)}`);
    }
  };

  const handleGoogleOAuthDisconnect = async () => {
    try {
      const result = await disconnectGoogleOAuth();
      setOauthStatus(
        result.revoked
          ? "Google OAuth disconnected and token revoked."
          : "Google OAuth disconnected locally.",
      );
      await refreshIntegrations();
    } catch (error) {
      setOauthStatus(`OAuth disconnect error: ${String(error)}`);
    }
  };

  const handleSaveMapsKey = async () => {
    const key = mapsKeyInput.trim();
    if (!key) {
      setStatusMessage("Maps API key is required.");
      return;
    }
    try {
      await saveMapsIntegrationKey(key);
      setMapsKeyInput("");
      await refreshIntegrations();
      setStatusMessage("Maps API key saved.");
    } catch (error) {
      setStatusMessage(`Failed to save Maps API key: ${String(error)}`);
    }
  };

  const handleClearMapsKey = async () => {
    try {
      await clearMapsIntegrationKey();
      setMapsKeyInput("");
      await refreshIntegrations();
      setStatusMessage("Stored Maps API key cleared.");
    } catch (error) {
      setStatusMessage(`Failed to clear Maps API key: ${String(error)}`);
    }
  };

  return (
    <div className="flex-1 flex flex-col bg-white overflow-hidden">
      <div className="border-b border-[#e5e5e5] px-8 pt-6 pb-3">
        <div className="flex items-center justify-between gap-6">
          <div className="flex items-center gap-8">
            <button
              onClick={() => setActiveSettingsTab("general")}
              className={`pb-2 text-[13px] transition-all border-b-2 ${
                activeSettingsTab === "general"
                  ? "text-[#1d1d1f] border-[#1d1d1f]"
                  : "text-[#86868b] border-transparent hover:text-[#1d1d1f]"
              }`}
            >
              General
            </button>
            <button
              onClick={() => setActiveSettingsTab("integrations")}
              className={`pb-2 text-[13px] transition-all border-b-2 ${
                activeSettingsTab === "integrations"
                  ? "text-[#1d1d1f] border-[#1d1d1f]"
                  : "text-[#86868b] border-transparent hover:text-[#1d1d1f]"
              }`}
            >
              Integrations
            </button>
          </div>

          {activeSettingsTab === "integrations" ? (
            <button
              onClick={() => void refreshIntegrations()}
              className="px-4 py-2 rounded-lg border border-[#d2d2d7] bg-white text-[13px] font-medium text-[#1d1d1f] hover:bg-[#f5f5f7] transition"
            >
              Refresh
            </button>
          ) : null}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto p-8 space-y-6">
          {activeSettingsTab === "general" ? (
            <div className="rounded-2xl border border-[#e5e5e5] bg-[#fafafa] p-6">
              <h2 className="text-[17px] font-semibold text-[#1d1d1f]">General Settings</h2>
              <p className="mt-3 text-[13px] text-[#6e6e73] leading-relaxed">
                Integration credentials and OAuth are managed in the Integrations tab.
              </p>
            </div>
          ) : null}

          {activeSettingsTab === "integrations" ? (
            <>
              <section className="rounded-2xl border border-[#e5e5e5] bg-[#fafafa] p-6">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-[17px] font-semibold text-[#1d1d1f]">Google OAuth</h2>
                    <p className="mt-2 text-[13px] text-[#6e6e73]">
                      OAuth is the source of truth for Gmail, Calendar, Drive, Docs, Sheets, and GA4.
                    </p>
                  </div>
                  <div
                    className={`rounded-full border px-3 py-1 text-[12px] font-semibold ${oauthBadge(googleOAuthStatus.connected)}`}
                  >
                    {googleOAuthStatus.connected ? "Connected" : "Not connected"}
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <button
                    onClick={() => void handleGoogleOAuthConnect()}
                    className="rounded-xl border border-[#d2d2d7] bg-white px-4 py-2 text-[13px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7]"
                  >
                    Connect Google
                  </button>
                  <button
                    onClick={() => void handleGoogleOAuthDisconnect()}
                    className="rounded-xl border border-[#d2d2d7] bg-white px-4 py-2 text-[13px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7]"
                  >
                    Disconnect
                  </button>
                  {googleOAuthStatus.email ? (
                    <span className="text-[12px] text-[#525259]">{googleOAuthStatus.email}</span>
                  ) : null}
                  {googleOAuthStatus.scopes.length > 0 ? (
                    <span className="text-[12px] text-[#6e6e73]">
                      {googleOAuthStatus.scopes.length} scope(s)
                    </span>
                  ) : null}
                  {oauthStatus ? <span className="text-[12px] text-[#6e6e73]">{oauthStatus}</span> : null}
                </div>
                <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {googleToolHealth.map((item) => (
                    <div key={item.id} className="rounded-lg border border-[#ececf0] bg-white px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-[12px] font-semibold text-[#1d1d1f] capitalize">{item.label}</p>
                        <span
                          className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${statusChip(item.ok)}`}
                        >
                          {item.ok ? "Ready" : "Missing"}
                        </span>
                      </div>
                      {item.message ? (
                        <p className="mt-1 text-[11px] text-[#6e6e73]">{item.message}</p>
                      ) : null}
                    </div>
                  ))}
                </div>
              </section>

              <section className="rounded-2xl border border-[#e5e5e5] bg-[#fafafa] p-6">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h3 className="text-[16px] font-semibold text-[#1d1d1f]">Google Maps API</h3>
                    <p className="mt-1 text-[13px] text-[#6e6e73]">
                      Used for Places, Geocode, and Distance Matrix in company discovery workflows.
                    </p>
                  </div>
                  <span
                    className={`rounded-full border px-3 py-1 text-[12px] font-semibold ${statusChip(
                      mapsStatus.configured,
                    )}`}
                  >
                    {mapsStatus.configured ? "Configured" : "Missing"}
                  </span>
                </div>
                {mapsStatus.source === "env" ? (
                  <p className="mt-4 text-[12px] text-[#3a3a3c]">Configured via server env.</p>
                ) : (
                  <div className="mt-4 space-y-3">
                    <input
                      type="password"
                      value={mapsKeyInput}
                      onChange={(event) => setMapsKeyInput(event.target.value)}
                      className="w-full rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[13px] text-[#1d1d1f] placeholder:text-[#a1a1a6] focus:outline-none focus:border-[#8e8e93]"
                      placeholder="Paste Google Maps API key"
                      autoComplete="off"
                    />
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        onClick={() => void handleSaveMapsKey()}
                        className="rounded-xl bg-[#1d1d1f] px-4 py-2 text-[13px] font-semibold text-white hover:bg-[#2f2f34]"
                      >
                        Save key
                      </button>
                      <button
                        onClick={() => void handleClearMapsKey()}
                        className="rounded-xl border border-[#d2d2d7] bg-white px-4 py-2 text-[13px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7]"
                      >
                        Clear stored key
                      </button>
                    </div>
                  </div>
                )}
              </section>

              <section className="rounded-2xl border border-[#e5e5e5] bg-[#fafafa] p-6">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h3 className="text-[16px] font-semibold text-[#1d1d1f]">Brave Search</h3>
                    <p className="mt-1 text-[13px] text-[#6e6e73]">
                      Primary web research provider for live agent search workflows.
                    </p>
                  </div>
                  <span
                    className={`rounded-full border px-3 py-1 text-[12px] font-semibold ${statusChip(
                      braveStatus.configured,
                    )}`}
                  >
                    {braveStatus.configured ? "Configured" : "Missing"}
                  </span>
                </div>
                <p className="mt-3 text-[12px] text-[#525259]">
                  {braveStatus.source === "env"
                    ? "Configured via server env."
                    : "Set BRAVE_SEARCH_API_KEY on the backend environment."}
                </p>
              </section>

              <section className="rounded-2xl border border-[#e5e5e5] bg-[#fafafa] p-6">
                <p className="text-[12px] font-semibold text-[#1d1d1f]">Recent events</p>
                <p className="mt-1 text-[12px] text-[#6e6e73]">
                  Streaming last {Math.min(liveEvents.length, 80)} OAuth/tool events.
                </p>
                <div className="mt-3 max-h-56 overflow-y-auto space-y-2 pr-1">
                  {liveEvents.length === 0 ? (
                    <p className="text-[12px] text-[#8e8e93]">No events yet.</p>
                  ) : (
                    liveEvents.map((event, index) => (
                      <div
                        key={`${event.type}-${event.timestamp || index}`}
                        className="rounded-lg border border-[#ececf0] bg-white px-3 py-2"
                      >
                        <p className="text-[12px] font-semibold text-[#1d1d1f]">{event.type}</p>
                        <p className="text-[12px] text-[#6e6e73]">{event.message}</p>
                      </div>
                    ))
                  )}
                </div>
              </section>

              <section className="rounded-2xl border border-[#e5e5e5] bg-[#fafafa] p-6">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-[17px] font-semibold text-[#1d1d1f]">
                      Manual connector credentials
                    </h2>
                    <p className="mt-2 text-[13px] text-[#6e6e73]">
                      Configure {integrationCount} non-OAuth providers. Google OAuth-managed connectors
                      are intentionally removed from manual token input.
                    </p>
                  </div>
                </div>
                {statusMessage ? (
                  <p className="mt-4 text-[12px] text-[#525259]">{statusMessage}</p>
                ) : null}
              </section>

              {MANUAL_CONNECTOR_DEFINITIONS.map((connector) => {
                const health = healthMap[connector.id];
                const stored = credentialMap[connector.id];
                const currentDraft = draftValues[connector.id] || {};
                const busy = savingConnectorId === connector.id;

                return (
                  <ManualConnectorCard
                    key={connector.id}
                    connector={connector}
                    health={health}
                    stored={stored}
                    currentDraft={currentDraft}
                    busy={busy}
                    onDraftChange={(fieldKey, value) => handleDraftChange(connector.id, fieldKey, value)}
                    onSave={() => void handleSaveConnector(connector)}
                    onClear={() => void handleClearConnector(connector)}
                  />
                );
              })}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
