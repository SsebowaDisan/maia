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
} from "../../../api/client";
import {
  clearMapsIntegrationKey,
  getBraveIntegrationStatus,
  getMapsIntegrationStatus,
  getOllamaIntegrationStatus,
  getOllamaQuickstart,
  saveMapsIntegrationKey,
  type IntegrationStatus,
  type OllamaQuickstart,
  type OllamaStatus,
} from "../../../api/integrations";
import type { ConnectorDefinition } from "./connectorDefinitions";
import { useOllamaSettings } from "./useOllamaSettings";

export function useSettingsController(activeTab: string) {
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
  const [braveKeyInput, setBraveKeyInput] = useState("");
  const [liveEvents, setLiveEvents] = useState<AgentLiveEvent[]>([]);
  const ollama = useOllamaSettings();

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
      const [healthRows, credentialRows, oauthRow, mapsRow, braveRow, ollamaRow] = await Promise.all([
        listConnectorHealth(),
        listConnectorCredentials(),
        getGoogleOAuthStatus(),
        getMapsIntegrationStatus(),
        getBraveIntegrationStatus(),
        getOllamaIntegrationStatus(),
      ]);
      const quickstartRow = await getOllamaQuickstart(ollamaRow.base_url || undefined);

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

      const nextCredentialMap: Record<string, ConnectorCredentialRecord> = {};
      for (const row of credentialRows) {
        nextCredentialMap[row.connector_id] = row;
      }

      setHealthMap(nextHealthMap);
      setCredentialMap(nextCredentialMap);
      setGoogleOAuthStatus(oauthRow);
      setMapsStatus(mapsRow);
      setBraveStatus(braveRow);
      ollama.syncFromStatus(ollamaRow as OllamaStatus, quickstartRow as OllamaQuickstart | null);
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
    if (!params.get("tab")) {
      params.set("tab", activeTab);
    }
    const nextSearch = params.toString();
    const nextUrl = `${window.location.pathname}${nextSearch ? `?${nextSearch}` : ""}`;
    window.history.replaceState({}, "", nextUrl);
    void refreshIntegrations();
  }, [activeTab]);

  useEffect(() => {
    const unsubscribe = subscribeAgentEvents({
      replay: 30,
      onEvent: (event) => {
        ollama.handleLiveEvent(event, refreshIntegrations);
        setLiveEvents((previous) => [event, ...previous].slice(0, 80));
      },
      onError: () => {
        setOauthStatus((prev) => prev || "Live events stream disconnected. It will reconnect on page refresh.");
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
        result.revoked ? "Google OAuth disconnected and token revoked." : "Google OAuth disconnected locally.",
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

  const handleSaveBraveKey = async () => {
    const key = braveKeyInput.trim();
    if (!key) {
      setStatusMessage("Brave API key is required.");
      return;
    }
    setSavingConnectorId("brave_search");
    try {
      await upsertConnectorCredentials("brave_search", { BRAVE_SEARCH_API_KEY: key });
      setBraveKeyInput("");
      await refreshIntegrations();
      setStatusMessage("Brave Search API key saved.");
    } catch (error) {
      setStatusMessage(`Failed to save Brave Search API key: ${String(error)}`);
    } finally {
      setSavingConnectorId(null);
    }
  };

  const handleClearBraveKey = async () => {
    setSavingConnectorId("brave_search");
    try {
      await deleteConnectorCredentials("brave_search");
      setBraveKeyInput("");
      await refreshIntegrations();
      setStatusMessage("Brave Search API key cleared.");
    } catch (error) {
      setStatusMessage(`Failed to clear Brave Search API key: ${String(error)}`);
    } finally {
      setSavingConnectorId(null);
    }
  };

  return {
    loading,
    healthMap,
    credentialMap,
    draftValues,
    savingConnectorId,
    statusMessage,
    oauthStatus,
    googleOAuthStatus,
    mapsStatus,
    braveStatus,
    mapsKeyInput,
    braveKeyInput,
    liveEvents,
    googleToolHealth,
    setMapsKeyInput,
    setBraveKeyInput,
    refreshIntegrations,
    handleDraftChange,
    handleSaveConnector,
    handleClearConnector,
    handleGoogleOAuthConnect,
    handleGoogleOAuthDisconnect,
    handleSaveMapsKey,
    handleClearMapsKey,
    handleSaveBraveKey,
    handleClearBraveKey,
    ollama,
  };
}
