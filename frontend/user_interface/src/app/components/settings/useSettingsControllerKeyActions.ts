import type { Dispatch, SetStateAction } from "react";
import {
  clearMapsIntegrationKey,
  saveMapsIntegrationKey,
} from "../../../api/integrations";
import {
  deleteConnectorCredentials,
  upsertConnectorCredentials,
} from "../../../api/client";

type CreateSettingsControllerKeyActionsParams = {
  mapsKeyInput: string;
  braveKeyInput: string;
  refreshIntegrations: () => Promise<void>;
  setMapsKeyInput: Dispatch<SetStateAction<string>>;
  setBraveKeyInput: Dispatch<SetStateAction<string>>;
  setStatusMessage: Dispatch<SetStateAction<string>>;
  setSavingConnectorId: Dispatch<SetStateAction<string | null>>;
};

function createSettingsControllerKeyActions({
  mapsKeyInput,
  braveKeyInput,
  refreshIntegrations,
  setMapsKeyInput,
  setBraveKeyInput,
  setStatusMessage,
  setSavingConnectorId,
}: CreateSettingsControllerKeyActionsParams) {
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
    handleSaveMapsKey,
    handleClearMapsKey,
    handleSaveBraveKey,
    handleClearBraveKey,
  };
}

export { createSettingsControllerKeyActions };
