import type { Dispatch, SetStateAction } from "react";

import {
  getComputerUseActiveModel,
  getSettings,
  getGoogleOAuthStatus,
  listConnectorCredentials,
  listConnectorHealth,
  type ConnectorCredentialRecord,
  type GoogleOAuthStatus,
} from "../../../../api/client";
import {
  getBraveIntegrationStatus,
  getGoogleAnalyticsProperty,
  getGoogleServiceAccountStatus,
  getMapsIntegrationStatus,
  getOllamaIntegrationStatus,
  getOllamaQuickstart,
  listGoogleWorkspaceLinkAliases,
  type GoogleServiceAccountStatus,
  type GoogleWorkspaceAliasRecord,
  type IntegrationStatus,
  type OllamaQuickstart,
  type OllamaStatus,
} from "../../../../api/integrations";

type RefreshConnectorStatusDeps = {
  setLoading: Dispatch<SetStateAction<boolean>>;
  setHealthMap: Dispatch<SetStateAction<Record<string, { ok: boolean; message: string }>>>;
  setCredentialMap: Dispatch<SetStateAction<Record<string, ConnectorCredentialRecord>>>;
  setGoogleOAuthStatus: Dispatch<SetStateAction<GoogleOAuthStatus>>;
  setOauthRedirectUriInput: Dispatch<SetStateAction<string>>;
  setGoogleServiceAccountStatus: Dispatch<SetStateAction<GoogleServiceAccountStatus>>;
  setGoogleWorkspaceAliases: Dispatch<SetStateAction<GoogleWorkspaceAliasRecord[]>>;
  setGa4PropertyId: Dispatch<SetStateAction<string>>;
  setGa4PropertyIdInput: Dispatch<SetStateAction<string>>;
  setMapsStatus: Dispatch<SetStateAction<IntegrationStatus>>;
  setBraveStatus: Dispatch<SetStateAction<IntegrationStatus>>;
  setComputerUseModelSaved: Dispatch<SetStateAction<string>>;
  setComputerUseModelInput: Dispatch<SetStateAction<string>>;
  setComputerUseModelActive: Dispatch<SetStateAction<string>>;
  setComputerUseModelSource: Dispatch<SetStateAction<string>>;
  setStatusMessage: Dispatch<SetStateAction<string>>;
  syncOllama: (status: OllamaStatus, quickstart: OllamaQuickstart | null) => void;
};

function mapConnectorHealth(rows: Awaited<ReturnType<typeof listConnectorHealth>>) {
  const nextHealthMap: Record<string, { ok: boolean; message: string }> = {};
  for (const item of rows) {
    const connectorId = String(item.connector_id || "");
    if (!connectorId) {
      continue;
    }
    nextHealthMap[connectorId] = {
      ok: Boolean(item.ok),
      message: String(item.message || ""),
    };
  }
  return nextHealthMap;
}

function mapConnectorCredentials(rows: Awaited<ReturnType<typeof listConnectorCredentials>>) {
  const nextCredentialMap: Record<string, ConnectorCredentialRecord> = {};
  for (const row of rows) {
    nextCredentialMap[row.connector_id] = row;
  }
  return nextCredentialMap;
}

export function createRefreshConnectorStatus(deps: RefreshConnectorStatusDeps) {
  return async () => {
    deps.setLoading(true);
    try {
      const [
        healthRows,
        credentialRows,
        oauthRow,
        mapsRow,
        braveRow,
        ollamaRow,
        serviceAccountRow,
        aliasRows,
        ga4PropertyRow,
        settingsRow,
        activeModelRow,
      ] = await Promise.all([
        listConnectorHealth(),
        listConnectorCredentials(),
        getGoogleOAuthStatus(),
        getMapsIntegrationStatus(),
        getBraveIntegrationStatus(),
        getOllamaIntegrationStatus(),
        getGoogleServiceAccountStatus(),
        listGoogleWorkspaceLinkAliases(),
        getGoogleAnalyticsProperty(),
        getSettings(),
        getComputerUseActiveModel(),
      ]);

      const quickstartRow = await getOllamaQuickstart(ollamaRow.base_url || undefined);
      const savedPropertyId = String(ga4PropertyRow.property_id || "").trim();
      const savedComputerUseModel = String(
        settingsRow?.values?.["agent.computer_use_model"] || "",
      ).trim();

      deps.setHealthMap(mapConnectorHealth(healthRows));
      deps.setCredentialMap(mapConnectorCredentials(credentialRows));
      deps.setGoogleOAuthStatus(oauthRow);
      deps.setOauthRedirectUriInput((previous) =>
        previous.trim()
          ? previous
          : String(oauthRow.oauth_redirect_uri || "http://localhost:8000/api/agent/oauth/google/callback"),
      );
      deps.setGoogleServiceAccountStatus(serviceAccountRow);
      deps.setGoogleWorkspaceAliases(Array.isArray(aliasRows.aliases) ? aliasRows.aliases : []);
      deps.setGa4PropertyId(savedPropertyId);
      deps.setGa4PropertyIdInput((prev) => (prev.trim() ? prev : savedPropertyId));
      deps.setMapsStatus(mapsRow);
      deps.setBraveStatus(braveRow);
      deps.setComputerUseModelSaved(savedComputerUseModel);
      deps.setComputerUseModelInput(savedComputerUseModel);
      deps.setComputerUseModelActive(String(activeModelRow?.model || "").trim());
      deps.setComputerUseModelSource(String(activeModelRow?.source || "").trim());
      deps.syncOllama(ollamaRow as OllamaStatus, quickstartRow as OllamaQuickstart | null);
      deps.setStatusMessage("Connector status synced.");
    } catch (error) {
      deps.setStatusMessage(`Failed to load connector status: ${String(error)}`);
    } finally {
      deps.setLoading(false);
    }
  };
}
