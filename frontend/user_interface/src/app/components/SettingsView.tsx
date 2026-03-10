import { useEffect, useState } from "react";

import { MANUAL_CONNECTOR_DEFINITIONS } from "./settings/connectorDefinitions";
import { SettingsLayout } from "./settings/layout/SettingsLayout";
import { ApiSettings } from "./settings/tabs/ApiSettings";
import { GeneralSettings } from "./settings/tabs/GeneralSettings";
import { IntegrationsSettings } from "./settings/tabs/IntegrationsSettings";
import { ModelsSettings } from "./settings/tabs/ModelsSettings";
import { SETTINGS_TABS, type SettingsTabId } from "./settings/types";
import { useSettingsController } from "./settings/useSettingsController";

const DEFAULT_TAB: SettingsTabId = "integrations";

function isSettingsTab(value: string | null): value is SettingsTabId {
  if (!value) {
    return false;
  }
  return SETTINGS_TABS.some((item) => item.id === value);
}

function readTabFromUrl(): SettingsTabId {
  if (typeof window === "undefined") {
    return DEFAULT_TAB;
  }
  const params = new URLSearchParams(window.location.search);
  const tabValue = params.get("tab");
  return isSettingsTab(tabValue) ? tabValue : DEFAULT_TAB;
}

function syncUrlTab(tab: SettingsTabId) {
  if (typeof window === "undefined") {
    return;
  }
  const params = new URLSearchParams(window.location.search);
  if (params.get("tab") === tab) {
    return;
  }
  params.set("tab", tab);
  const nextSearch = params.toString();
  const nextUrl = `${window.location.pathname}${nextSearch ? `?${nextSearch}` : ""}`;
  window.history.replaceState({}, "", nextUrl);
}

export function SettingsView() {
  const [activeTab, setActiveTab] = useState<SettingsTabId>(readTabFromUrl);
  const controller = useSettingsController(activeTab);

  useEffect(() => {
    syncUrlTab(activeTab);
  }, [activeTab]);

  return (
    <SettingsLayout
      title="Settings"
      subtitle="Manage workspace preferences, integrations, models, and API providers."
      tabs={SETTINGS_TABS}
      activeTab={activeTab}
      onChangeTab={setActiveTab}
      headerAction={
        <button
          type="button"
          onClick={() => void controller.refreshIntegrations()}
          className="rounded-xl border border-[#d2d2d7] bg-white px-4 py-2 text-[13px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7]"
        >
          Refresh
        </button>
      }
    >
      {activeTab === "general" ? (
        <GeneralSettings
          loading={controller.loading}
          oauthConnected={controller.googleOAuthStatus.connected}
          ollamaReachable={controller.ollama.ollamaStatus.reachable}
          mapsConfigured={controller.mapsStatus.configured}
          braveConfigured={controller.braveStatus.configured}
          statusMessage={controller.statusMessage}
        />
      ) : null}

      {activeTab === "integrations" ? (
        <IntegrationsSettings
          googleOAuthStatus={controller.googleOAuthStatus}
          googleServiceAccountStatus={controller.googleServiceAccountStatus}
          googleWorkspaceAliases={controller.googleWorkspaceAliases}
          oauthStatus={controller.oauthStatus}
          oauthClientIdInput={controller.oauthClientIdInput}
          oauthClientSecretInput={controller.oauthClientSecretInput}
          oauthRedirectUriInput={controller.oauthRedirectUriInput}
          oauthConfigSaving={controller.oauthConfigSaving}
          googleToolHealth={controller.googleToolHealth}
          liveEvents={controller.liveEvents}
          onConnectGoogle={(options) => controller.handleGoogleOAuthConnect(options)}
          onDisconnectGoogle={() => void controller.handleGoogleOAuthDisconnect()}
          onOAuthClientIdInputChange={controller.setOauthClientIdInput}
          onOAuthClientSecretInputChange={controller.setOauthClientSecretInput}
          onOAuthRedirectUriInputChange={controller.setOauthRedirectUriInput}
          onSaveGoogleOAuthConfig={() => void controller.handleSaveGoogleOAuthConfig()}
          onRequestGoogleOAuthSetup={() => controller.handleRequestGoogleOAuthSetup()}
          onSaveGoogleOAuthServices={(services) => controller.handleSaveGoogleOAuthServices(services)}
          onGoogleAuthModeChange={(mode) => void controller.handleGoogleWorkspaceAuthModeChange(mode)}
          onAnalyzeGoogleLink={(link) => controller.handleAnalyzeGoogleWorkspaceLink(link)}
          onCheckGoogleLinkAccess={(payload) => controller.handleCheckGoogleWorkspaceLinkAccess(payload)}
          onSaveGoogleLinkAlias={(alias, link) =>
            controller.handleSaveGoogleWorkspaceLinkAlias(alias, link)
          }
          ga4PropertyId={controller.ga4PropertyId}
          ga4PropertyIdInput={controller.ga4PropertyIdInput}
          onGa4PropertyIdInputChange={controller.setGa4PropertyIdInput}
          onSaveGa4PropertyId={() => controller.handleSaveGa4PropertyId()}
        />
      ) : null}

      {activeTab === "models" ? (
        <ModelsSettings
          ollamaStatus={controller.ollama.ollamaStatus}
          ollamaModels={controller.ollama.ollamaModels}
          ollamaBaseUrlInput={controller.ollama.ollamaBaseUrlInput}
          ollamaModelInput={controller.ollama.ollamaModelInput}
          ollamaEmbeddingInput={controller.ollama.ollamaEmbeddingInput}
          ollamaBusyAction={controller.ollama.ollamaBusyAction}
          ollamaProgress={controller.ollama.ollamaProgress}
          ollamaMessage={controller.ollama.ollamaMessage}
          setOllamaBaseUrlInput={controller.ollama.setOllamaBaseUrlInput}
          setOllamaModelInput={controller.ollama.setOllamaModelInput}
          setOllamaEmbeddingInput={controller.ollama.setOllamaEmbeddingInput}
          onOneClickSetup={() => void controller.ollama.handleOneClickOllamaOnboarding()}
          onSaveConfig={() => void controller.ollama.handleSaveOllamaConfig()}
          onStartOllama={() => void controller.ollama.handleStartOllamaLocally()}
          onRefreshModels={() => void controller.ollama.handleRefreshOllamaModels()}
          onPullModel={(modelOverride) => void controller.ollama.handlePullOllamaModel(modelOverride)}
          onSelectModel={(model) => void controller.ollama.handleSelectOllamaModel(model)}
          onPullEmbeddingModel={(modelOverride) =>
            void controller.ollama.handlePullOllamaEmbeddingModel(modelOverride)
          }
          onSelectEmbeddingModel={(model) => void controller.ollama.handleSelectOllamaEmbeddingModel(model)}
          onApplyEmbeddingToAllCollections={() =>
            void controller.ollama.handleApplyEmbeddingToAllCollections()
          }
        />
      ) : null}

      {activeTab === "apis" ? (
        <ApiSettings
          mapsStatus={controller.mapsStatus}
          braveStatus={controller.braveStatus}
          mapsKeyInput={controller.mapsKeyInput}
          braveKeyInput={controller.braveKeyInput}
          setMapsKeyInput={controller.setMapsKeyInput}
          setBraveKeyInput={controller.setBraveKeyInput}
          onSaveMapsKey={() => void controller.handleSaveMapsKey()}
          onClearMapsKey={() => void controller.handleClearMapsKey()}
          onSaveBraveKey={() => void controller.handleSaveBraveKey()}
          onClearBraveKey={() => void controller.handleClearBraveKey()}
          connectors={MANUAL_CONNECTOR_DEFINITIONS}
          healthMap={controller.healthMap}
          credentialMap={controller.credentialMap}
          draftValues={controller.draftValues}
          savingConnectorId={controller.savingConnectorId}
          statusMessage={controller.statusMessage}
          onDraftChange={controller.handleDraftChange}
          onSaveConnector={(connector) => void controller.handleSaveConnector(connector)}
          onClearConnector={(connector) => void controller.handleClearConnector(connector)}
        />
      ) : null}
    </SettingsLayout>
  );
}
