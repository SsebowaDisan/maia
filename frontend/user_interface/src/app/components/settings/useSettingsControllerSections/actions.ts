import type { Dispatch, SetStateAction } from "react";

import {
  deleteConnectorCredentials,
  disconnectGoogleOAuth,
  getComputerUseActiveModel,
  patchSettings,
  requestGoogleOAuthSetup,
  saveGoogleOAuthConfig,
  startGoogleOAuth,
  upsertConnectorCredentials,
} from "../../../../api/client";
import {
  analyzeGoogleWorkspaceLink,
  checkGoogleWorkspaceLinkAccess,
  saveGoogleAnalyticsProperty,
  saveGoogleOAuthServices,
  saveGoogleWorkspaceAuthMode,
  saveGoogleWorkspaceLinkAlias,
  type GoogleWorkspaceAliasRecord,
  type GoogleWorkspaceLinkAccessResult,
  type GoogleWorkspaceLinkAnalyzeResult,
} from "../../../../api/integrations";
import type { ConnectorDefinition } from "../connectorDefinitions";

type SharedActionDeps = {
  refreshConnectorStatus: () => Promise<void>;
  setStatusMessage: Dispatch<SetStateAction<string>>;
};

type ConnectorActionDeps = SharedActionDeps & {
  draftValues: Record<string, Record<string, string>>;
  setDraftValues: Dispatch<SetStateAction<Record<string, Record<string, string>>>>;
  setSavingConnectorId: Dispatch<SetStateAction<string | null>>;
};

export function createConnectorActions(deps: ConnectorActionDeps) {
  const handleDraftChange = (connectorId: string, key: string, value: string) => {
    deps.setDraftValues((prev) => ({
      ...prev,
      [connectorId]: {
        ...(prev[connectorId] || {}),
        [key]: value,
      },
    }));
  };

  const handleSaveConnector = async (connector: ConnectorDefinition) => {
    const draft = deps.draftValues[connector.id] || {};
    const payload: Record<string, string> = {};
    for (const field of connector.fields) {
      const value = String(draft[field.key] || "").trim();
      if (!value) {
        continue;
      }
      payload[field.key] = value;
    }
    if (!Object.keys(payload).length) {
      deps.setStatusMessage(`No values entered for ${connector.label}.`);
      return;
    }
    deps.setSavingConnectorId(connector.id);
    try {
      await upsertConnectorCredentials(connector.id, payload);
      deps.setDraftValues((prev) => ({ ...prev, [connector.id]: {} }));
      await deps.refreshConnectorStatus();
      deps.setStatusMessage(`${connector.label} credentials saved.`);
    } catch (error) {
      deps.setStatusMessage(`Failed to save ${connector.label}: ${String(error)}`);
    } finally {
      deps.setSavingConnectorId(null);
    }
  };

  const handleClearConnector = async (connector: ConnectorDefinition) => {
    deps.setSavingConnectorId(connector.id);
    try {
      await deleteConnectorCredentials(connector.id);
      await deps.refreshConnectorStatus();
      deps.setStatusMessage(`${connector.label} credentials removed.`);
    } catch (error) {
      deps.setStatusMessage(`Failed to clear ${connector.label}: ${String(error)}`);
    } finally {
      deps.setSavingConnectorId(null);
    }
  };

  return {
    handleDraftChange,
    handleSaveConnector,
    handleClearConnector,
  };
}

type GoogleActionDeps = SharedActionDeps & {
  oauthClientIdInput: string;
  oauthClientSecretInput: string;
  oauthRedirectUriInput: string;
  ga4PropertyIdInput: string;
  setOauthStatus: Dispatch<SetStateAction<string>>;
  setOauthClientSecretInput: Dispatch<SetStateAction<string>>;
  setOauthConfigSaving: Dispatch<SetStateAction<boolean>>;
  setGa4PropertyId: Dispatch<SetStateAction<string>>;
};

export function createGoogleActions(deps: GoogleActionDeps) {
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
        deps.setOauthStatus(message);
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
      deps.setOauthStatus(message);
      return { ok: opened, authorize_url: authorizeUrl, message };
    } catch (error) {
      const message = `OAuth setup error: ${String(error)}`;
      deps.setOauthStatus(message);
      return { ok: false, message };
    }
  };

  const handleGoogleOAuthDisconnect = async () => {
    try {
      const result = await disconnectGoogleOAuth();
      deps.setOauthStatus(
        result.revoked ? "Google OAuth disconnected and token revoked." : "Google OAuth disconnected locally.",
      );
      await deps.refreshConnectorStatus();
    } catch (error) {
      deps.setOauthStatus(`OAuth disconnect error: ${String(error)}`);
    }
  };

  const handleSaveGoogleOAuthConfig = async () => {
    const clientId = deps.oauthClientIdInput.trim();
    const clientSecret = deps.oauthClientSecretInput.trim();
    const redirectUri = deps.oauthRedirectUriInput.trim();
    if (!clientId || !clientSecret) {
      deps.setOauthStatus("Google OAuth client ID and client secret are required.");
      return;
    }
    deps.setOauthConfigSaving(true);
    try {
      await saveGoogleOAuthConfig({
        clientId,
        clientSecret,
        redirectUri: redirectUri || undefined,
      });
      deps.setOauthClientSecretInput("");
      await deps.refreshConnectorStatus();
      deps.setOauthStatus("OAuth app credentials saved. Next step: connect Google account.");
    } catch (error) {
      deps.setOauthStatus(`Failed to save OAuth app credentials: ${String(error)}`);
    } finally {
      deps.setOauthConfigSaving(false);
    }
  };

  const handleRequestGoogleOAuthSetup = async (): Promise<{
    ok: boolean;
    message: string;
  }> => {
    try {
      const result = await requestGoogleOAuthSetup();
      const ownerHint = String(result.workspace_owner_user_id || "").trim();
      await deps.refreshConnectorStatus();
      const ownerText = ownerHint ? ` Workspace owner: ${ownerHint}.` : "";
      const message = `Setup request submitted.${ownerText}`;
      deps.setOauthStatus(message);
      return { ok: true, message };
    } catch (error) {
      const message = `Could not submit setup request: ${String(error)}`;
      deps.setOauthStatus(message);
      return { ok: false, message };
    }
  };

  const handleGoogleWorkspaceAuthModeChange = async (mode: "oauth" | "service_account") => {
    try {
      await saveGoogleWorkspaceAuthMode(mode);
      await deps.refreshConnectorStatus();
      deps.setStatusMessage(
        mode === "service_account"
          ? "Google auth mode set to service account."
          : "Google auth mode set to OAuth.",
      );
    } catch (error) {
      deps.setStatusMessage(`Failed to update Google auth mode: ${String(error)}`);
    }
  };

  const handleSaveGoogleOAuthServices = async (
    services: string[],
  ): Promise<{ ok: boolean; services: string[]; message: string }> => {
    try {
      const result = await saveGoogleOAuthServices(services);
      await deps.refreshConnectorStatus();
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

  const handleSaveGa4PropertyId = async (): Promise<{ ok: boolean; message: string }> => {
    const raw = deps.ga4PropertyIdInput.trim();
    if (!raw) {
      return { ok: false, message: "Enter a GA4 property ID." };
    }
    try {
      const result = await saveGoogleAnalyticsProperty(raw);
      deps.setGa4PropertyId(String(result.property_id || raw));
      return { ok: true, message: `GA4 property ID saved: ${result.property_id}` };
    } catch (error) {
      return { ok: false, message: `Could not save GA4 property ID: ${String(error)}` };
    }
  };

  return {
    handleGoogleOAuthConnect,
    handleGoogleOAuthDisconnect,
    handleSaveGoogleOAuthConfig,
    handleRequestGoogleOAuthSetup,
    handleGoogleWorkspaceAuthModeChange,
    handleSaveGoogleOAuthServices,
    handleSaveGa4PropertyId,
  };
}

type WorkspaceActionDeps = {
  setGoogleWorkspaceAliases: Dispatch<SetStateAction<GoogleWorkspaceAliasRecord[]>>;
};

export function createWorkspaceActions(deps: WorkspaceActionDeps) {
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
    deps.setGoogleWorkspaceAliases(aliases);
    return aliases;
  };

  return {
    handleAnalyzeGoogleWorkspaceLink,
    handleCheckGoogleWorkspaceLinkAccess,
    handleSaveGoogleWorkspaceLinkAlias,
  };
}

type ComputerUseActionDeps = SharedActionDeps & {
  computerUseModelInput: string;
  setComputerUseModelSaving: Dispatch<SetStateAction<boolean>>;
  setComputerUseModelSaved: Dispatch<SetStateAction<string>>;
  setComputerUseModelInput: Dispatch<SetStateAction<string>>;
  setComputerUseModelActive: Dispatch<SetStateAction<string>>;
  setComputerUseModelSource: Dispatch<SetStateAction<string>>;
};

export function createComputerUseActions(deps: ComputerUseActionDeps) {
  const persistComputerUseModel = async (nextValue: string) => {
    const normalized = String(nextValue || "").trim();
    deps.setComputerUseModelSaving(true);
    try {
      const updated = await patchSettings({
        "agent.computer_use_model": normalized,
      });
      const savedValue = String(updated?.values?.["agent.computer_use_model"] || "").trim();
      deps.setComputerUseModelSaved(savedValue);
      deps.setComputerUseModelInput(savedValue);
      const activeModel = await getComputerUseActiveModel();
      deps.setComputerUseModelActive(String(activeModel?.model || "").trim());
      deps.setComputerUseModelSource(String(activeModel?.source || "").trim());
      deps.setStatusMessage(
        savedValue
          ? "Computer Use model override saved."
          : "Computer Use model override cleared.",
      );
    } catch (error) {
      deps.setStatusMessage(`Failed to save Computer Use model override: ${String(error)}`);
    } finally {
      deps.setComputerUseModelSaving(false);
    }
  };

  const handleSaveComputerUseModel = async () => {
    await persistComputerUseModel(deps.computerUseModelInput);
  };

  const handleClearComputerUseModel = async () => {
    await persistComputerUseModel("");
  };

  return {
    handleSaveComputerUseModel,
    handleClearComputerUseModel,
  };
}
