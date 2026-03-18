import { IntegrationsSettings } from "../settings/tabs/IntegrationsSettings";
import { useSettingsController } from "../settings/useSettingsController";

type ConnectorGoogleAdvancedSettingsProps = {
  visible: boolean;
  controller: ReturnType<typeof useSettingsController>;
};

export function ConnectorGoogleAdvancedSettings({
  visible,
  controller,
}: ConnectorGoogleAdvancedSettingsProps) {
  if (!visible) {
    return null;
  }

  return (
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
      onSaveGoogleOAuthServices={(services) =>
        controller.handleSaveGoogleOAuthServices(services)
      }
      onGoogleAuthModeChange={(mode) =>
        void controller.handleGoogleWorkspaceAuthModeChange(mode)
      }
      onAnalyzeGoogleLink={(link) => controller.handleAnalyzeGoogleWorkspaceLink(link)}
      onCheckGoogleLinkAccess={(payload) =>
        controller.handleCheckGoogleWorkspaceLinkAccess(payload)
      }
      onSaveGoogleLinkAlias={(alias, link) =>
        controller.handleSaveGoogleWorkspaceLinkAlias(alias, link)
      }
      ga4PropertyId={controller.ga4PropertyId}
      ga4PropertyIdInput={controller.ga4PropertyIdInput}
      onGa4PropertyIdInputChange={controller.setGa4PropertyIdInput}
      onSaveGa4PropertyId={() => controller.handleSaveGa4PropertyId()}
    />
  );
}
