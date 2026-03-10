import { useEffect, useMemo, useState } from "react";

import {
  deleteConnectorCredentials,
  disconnectGoogleOAuth,
  requestGoogleOAuthSetup,
  saveGoogleOAuthConfig,
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
  analyzeGoogleWorkspaceLink,
  checkGoogleWorkspaceLinkAccess,
  getBraveIntegrationStatus,
  getGoogleAnalyticsProperty,
  getGoogleServiceAccountStatus,
  listGoogleWorkspaceLinkAliases,
  getMapsIntegrationStatus,
  getOllamaIntegrationStatus,
  getOllamaQuickstart,
  saveGoogleAnalyticsProperty,
  saveGoogleWorkspaceLinkAlias,
  saveGoogleOAuthServices,
  saveGoogleWorkspaceAuthMode,
  type GoogleWorkspaceAliasRecord,
  type GoogleWorkspaceLinkAccessResult,
  type GoogleWorkspaceLinkAnalyzeResult,
  type GoogleServiceAccountStatus,
  type IntegrationStatus,
  type OllamaQuickstart,
  type OllamaStatus,
} from "../../../api/integrations";
import type { ConnectorDefinition } from "./connectorDefinitions";
import { createSettingsControllerKeyActions } from "./useSettingsControllerKeyActions";
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
  const [googleServiceAccountStatus, setGoogleServiceAccountStatus] = useState<GoogleServiceAccountStatus>({
    configured: false,
    usable: false,
    email: "",
    auth_mode: "oauth",
    message: "Service-account credentials are not configured.",
    instructions: [],
  });
  const [googleWorkspaceAliases, setGoogleWorkspaceAliases] = useState<GoogleWorkspaceAliasRecord[]>([]);
  const [ga4PropertyId, setGa4PropertyId] = useState("");
  const [ga4PropertyIdInput, setGa4PropertyIdInput] = useState("");
  const [mapsStatus, setMapsStatus] = useState<IntegrationStatus>({ configured: false, source: null });
  const [braveStatus, setBraveStatus] = useState<IntegrationStatus>({ configured: false, source: null });
  const [mapsKeyInput, setMapsKeyInput] = useState("");
  const [braveKeyInput, setBraveKeyInput] = useState("");
  const [oauthClientIdInput, setOauthClientIdInput] = useState("");
  const [oauthClientSecretInput, setOauthClientSecretInput] = useState("");
  const [oauthRedirectUriInput, setOauthRedirectUriInput] = useState("");
  const [oauthConfigSaving, setOauthConfigSaving] = useState(false);
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
      const [healthRows, credentialRows, oauthRow, mapsRow, braveRow, ollamaRow, serviceAccountRow, aliasRows, ga4PropertyRow] =
        await Promise.all([
        listConnectorHealth(),
        listConnectorCredentials(),
        getGoogleOAuthStatus(),
        getMapsIntegrationStatus(),
        getBraveIntegrationStatus(),
        getOllamaIntegrationStatus(),
        getGoogleServiceAccountStatus(),
        listGoogleWorkspaceLinkAliases(),
        getGoogleAnalyticsProperty(),
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
      setOauthRedirectUriInput((previous) =>
        previous.trim()
          ? previous
          : String(oauthRow.oauth_redirect_uri || "http://localhost:8000/api/agent/oauth/google/callback"),
      );
      setGoogleServiceAccountStatus(serviceAccountRow);
      setGoogleWorkspaceAliases(Array.isArray(aliasRows.aliases) ? aliasRows.aliases : []);
      const savedPropertyId = String(ga4PropertyRow.property_id || "").trim();
      setGa4PropertyId(savedPropertyId);
      setGa4PropertyIdInput((prev) => (prev.trim() ? prev : savedPropertyId));
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
    if (activeTab !== "integrations" || typeof window === "undefined") {
      return;
    }
    const timer = window.setInterval(() => {
      void refreshIntegrations();
    }, 20000);
    return () => {
      window.clearInterval(timer);
    };
  }, [activeTab]);

  useEffect(() => {
    const unsubscribe = subscribeAgentEvents({
      replay: 0,
      onEvent: (event) => {
        ollama.handleLiveEvent(event, refreshIntegrations);
        setLiveEvents((previous) => [event, ...previous]);
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

  const handleGoogleOAuthConnect = async (options?: {
    scopes?: string[];
    toolIds?: string[];
  }): Promise<{
    ok: boolean;
    authorize_url?: string;
    message: string;
  }> => {
    try {
      const payload = await startGoogleOAuth({
        scopes: options?.scopes,
        toolIds: options?.toolIds,
      });
      const authorizeUrl = String(payload.authorize_url || "").trim();
      if (!authorizeUrl) {
        const message = "OAuth setup failed: missing Google authorize URL.";
        setOauthStatus(message);
        return { ok: false, message };
      }
      let opened = false;
      if (typeof window !== "undefined") {
        const popup = window.open(authorizeUrl, "_blank", "noopener,noreferrer");
        if (popup && !popup.closed) {
          popup.focus();
          opened = true;
        } else {
          window.location.assign(authorizeUrl);
          opened = true;
        }
      }
      const message = "Google sign-in started.";
      setOauthStatus(message);
      return { ok: opened, authorize_url: authorizeUrl, message };
    } catch (error) {
      const message = `OAuth setup error: ${String(error)}`;
      setOauthStatus(message);
      return { ok: false, message };
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

  const handleSaveGoogleOAuthConfig = async () => {
    const clientId = oauthClientIdInput.trim();
    const clientSecret = oauthClientSecretInput.trim();
    const redirectUri = oauthRedirectUriInput.trim();
    if (!clientId || !clientSecret) {
      setOauthStatus("Google OAuth client ID and client secret are required.");
      return;
    }
    setOauthConfigSaving(true);
    try {
      await saveGoogleOAuthConfig({
        clientId,
        clientSecret,
        redirectUri: redirectUri || undefined,
      });
      setOauthClientSecretInput("");
      await refreshIntegrations();
      setOauthStatus("OAuth app credentials saved. Next step: connect Google account.");
    } catch (error) {
      setOauthStatus(`Failed to save OAuth app credentials: ${String(error)}`);
    } finally {
      setOauthConfigSaving(false);
    }
  };

  const handleRequestGoogleOAuthSetup = async (): Promise<{
    ok: boolean;
    message: string;
  }> => {
    try {
      const result = await requestGoogleOAuthSetup();
      const ownerHint = String(result.workspace_owner_user_id || "").trim();
      await refreshIntegrations();
      const ownerText = ownerHint ? ` Workspace owner: ${ownerHint}.` : "";
      const message = `Setup request submitted.${ownerText}`;
      setOauthStatus(message);
      return { ok: true, message };
    } catch (error) {
      const message = `Could not submit setup request: ${String(error)}`;
      setOauthStatus(message);
      return { ok: false, message };
    }
  };

  const handleGoogleWorkspaceAuthModeChange = async (mode: "oauth" | "service_account") => {
    try {
      await saveGoogleWorkspaceAuthMode(mode);
      await refreshIntegrations();
      setStatusMessage(
        mode === "service_account"
          ? "Google auth mode set to service account."
          : "Google auth mode set to OAuth.",
      );
    } catch (error) {
      setStatusMessage(`Failed to update Google auth mode: ${String(error)}`);
    }
  };

  const handleSaveGoogleOAuthServices = async (
    services: string[],
  ): Promise<{ ok: boolean; services: string[]; message: string }> => {
    try {
      const result = await saveGoogleOAuthServices(services);
      await refreshIntegrations();
      const saved = Array.isArray(result.services) ? result.services : [];
      return {
        ok: true,
        services: saved,
        message: saved.length > 0 ? "Google services saved." : "Google services cleared.",
      };
    } catch (error) {
      return {
        ok: false,
        services: [],
        message: `Could not save Google services: ${String(error)}`,
      };
    }
  };

  const handleAnalyzeGoogleWorkspaceLink = async (
    link: string,
  ): Promise<GoogleWorkspaceLinkAnalyzeResult> => {
    return analyzeGoogleWorkspaceLink(link.trim());
  };

  const handleCheckGoogleWorkspaceLinkAccess = async (payload: {
    link: string;
    action: "read" | "edit";
  }): Promise<GoogleWorkspaceLinkAccessResult> => {
    return checkGoogleWorkspaceLinkAccess({ link: payload.link.trim(), action: payload.action });
  };

  const handleSaveGoogleWorkspaceLinkAlias = async (
    alias: string,
    link: string,
  ): Promise<GoogleWorkspaceAliasRecord[]> => {
    const response = await saveGoogleWorkspaceLinkAlias({ alias: alias.trim(), link: link.trim() });
    const aliases = Array.isArray(response.aliases) ? response.aliases : [];
    setGoogleWorkspaceAliases(aliases);
    return aliases;
  };
  const handleSaveGa4PropertyId = async (): Promise<{ ok: boolean; message: string }> => {
    const raw = ga4PropertyIdInput.trim();
    if (!raw) {
      return { ok: false, message: "Enter a GA4 property ID." };
    }
    try {
      const result = await saveGoogleAnalyticsProperty(raw);
      setGa4PropertyId(String(result.property_id || raw));
      return { ok: true, message: `GA4 property ID saved: ${result.property_id}` };
    } catch (error) {
      return { ok: false, message: `Could not save GA4 property ID: ${String(error)}` };
    }
  };

  const {
    handleSaveMapsKey,
    handleClearMapsKey,
    handleSaveBraveKey,
    handleClearBraveKey,
  } = createSettingsControllerKeyActions({
    mapsKeyInput,
    braveKeyInput,
    refreshIntegrations,
    setMapsKeyInput,
    setBraveKeyInput,
    setStatusMessage,
    setSavingConnectorId,
  });

  return {
    loading,
    healthMap,
    credentialMap,
    draftValues,
    savingConnectorId,
    statusMessage,
    oauthStatus,
    googleOAuthStatus,
    googleServiceAccountStatus,
    googleWorkspaceAliases,
    ga4PropertyId,
    ga4PropertyIdInput,
    setGa4PropertyIdInput,
    handleSaveGa4PropertyId,
    mapsStatus,
    braveStatus,
    mapsKeyInput,
    braveKeyInput,
    oauthClientIdInput,
    oauthClientSecretInput,
    oauthRedirectUriInput,
    oauthConfigSaving,
    liveEvents,
    googleToolHealth,
    setMapsKeyInput,
    setBraveKeyInput,
    setOauthClientIdInput,
    setOauthClientSecretInput,
    setOauthRedirectUriInput,
    refreshIntegrations,
    handleDraftChange,
    handleSaveConnector,
    handleClearConnector,
    handleGoogleOAuthConnect,
    handleGoogleOAuthDisconnect,
    handleSaveGoogleOAuthConfig,
    handleRequestGoogleOAuthSetup,
    handleSaveGoogleOAuthServices,
    handleGoogleWorkspaceAuthModeChange,
    handleAnalyzeGoogleWorkspaceLink,
    handleCheckGoogleWorkspaceLinkAccess,
    handleSaveGoogleWorkspaceLinkAlias,
    handleSaveMapsKey,
    handleClearMapsKey,
    handleSaveBraveKey,
    handleClearBraveKey,
    ollama,
  };
}
