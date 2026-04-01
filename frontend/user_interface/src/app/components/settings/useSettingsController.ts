import { useEffect, useMemo, useState } from "react";

import {
  subscribeAgentEvents,
  type AgentLiveEvent,
  type ConnectorCredentialRecord,
  type GoogleOAuthStatus,
} from "../../../api/client";
import {
  type GoogleWorkspaceAliasRecord,
  type GoogleServiceAccountStatus,
  type IntegrationStatus,
} from "../../../api/integrations";
import { createSettingsControllerKeyActions } from "./useSettingsControllerKeyActions";
import { useOllamaSettings } from "./useOllamaSettings";
import {
  createComputerUseActions,
  createConnectorActions,
  createGoogleActions,
  createWorkspaceActions,
} from "./useSettingsControllerSections/actions";
import { createRefreshConnectorStatus } from "./useSettingsControllerSections/status";

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
  const [computerUseModelInput, setComputerUseModelInput] = useState("");
  const [computerUseModelSaved, setComputerUseModelSaved] = useState("");
  const [computerUseModelActive, setComputerUseModelActive] = useState("");
  const [computerUseModelSource, setComputerUseModelSource] = useState("");
  const [computerUseModelSaving, setComputerUseModelSaving] = useState(false);
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

  const refreshConnectorStatus = createRefreshConnectorStatus({
    setLoading,
    setHealthMap,
    setCredentialMap,
    setGoogleOAuthStatus,
    setOauthRedirectUriInput,
    setGoogleServiceAccountStatus,
    setGoogleWorkspaceAliases,
    setGa4PropertyId,
    setGa4PropertyIdInput,
    setMapsStatus,
    setBraveStatus,
    setComputerUseModelSaved,
    setComputerUseModelInput,
    setComputerUseModelActive,
    setComputerUseModelSource,
    setStatusMessage,
    syncOllama: ollama.syncFromStatus,
  });

  useEffect(() => {
    void refreshConnectorStatus();
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
    void refreshConnectorStatus();
  }, [activeTab]);

  useEffect(() => {
    if ((activeTab !== "integrations" && activeTab !== "connectors") || typeof window === "undefined") {
      return;
    }
    const timer = window.setInterval(() => {
      void refreshConnectorStatus();
    }, 20000);
    return () => {
      window.clearInterval(timer);
    };
  }, [activeTab]);

  useEffect(() => {
    const unsubscribe = subscribeAgentEvents({
      replay: 0,
      onEvent: (event) => {
        ollama.handleLiveEvent(event, refreshConnectorStatus);
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

  const { handleDraftChange, handleSaveConnector, handleClearConnector } = createConnectorActions({
    draftValues,
    setDraftValues,
    refreshConnectorStatus,
    setStatusMessage,
    setSavingConnectorId,
  });
  const {
    handleGoogleOAuthConnect,
    handleGoogleOAuthDisconnect,
    handleSaveGoogleOAuthConfig,
    handleRequestGoogleOAuthSetup,
    handleGoogleWorkspaceAuthModeChange,
    handleSaveGoogleOAuthServices,
    handleSaveGa4PropertyId,
  } = createGoogleActions({
    refreshConnectorStatus,
    setStatusMessage,
    oauthClientIdInput,
    oauthClientSecretInput,
    oauthRedirectUriInput,
    ga4PropertyIdInput,
    setOauthStatus,
    setOauthClientSecretInput,
    setOauthConfigSaving,
    setGa4PropertyId,
  });
  const {
    handleAnalyzeGoogleWorkspaceLink,
    handleCheckGoogleWorkspaceLinkAccess,
    handleSaveGoogleWorkspaceLinkAlias,
  } = createWorkspaceActions({
    setGoogleWorkspaceAliases,
  });
  const { handleSaveComputerUseModel, handleClearComputerUseModel } = createComputerUseActions({
    refreshConnectorStatus,
    setStatusMessage,
    computerUseModelInput,
    setComputerUseModelSaving,
    setComputerUseModelSaved,
    setComputerUseModelInput,
    setComputerUseModelActive,
    setComputerUseModelSource,
  });

  const {
    handleSaveMapsKey,
    handleClearMapsKey,
    handleSaveBraveKey,
    handleClearBraveKey,
  } = createSettingsControllerKeyActions({
    mapsKeyInput,
    braveKeyInput,
    refreshConnectorStatus,
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
    computerUseModelInput,
    computerUseModelSaved,
    computerUseModelActive,
    computerUseModelSource,
    computerUseModelSaving,
    oauthClientIdInput,
    oauthClientSecretInput,
    oauthRedirectUriInput,
    oauthConfigSaving,
    liveEvents,
    googleToolHealth,
    setMapsKeyInput,
    setBraveKeyInput,
    setComputerUseModelInput,
    setOauthClientIdInput,
    setOauthClientSecretInput,
    setOauthRedirectUriInput,
    setStatusMessage,
    refreshConnectorStatus,
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
    handleSaveComputerUseModel,
    handleClearComputerUseModel,
    ollama,
  };
}
