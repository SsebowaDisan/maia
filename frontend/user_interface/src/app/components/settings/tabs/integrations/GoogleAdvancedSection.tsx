import type { AgentLiveEvent, GoogleOAuthStatus } from "../../../../../api/client";
import { SettingsRow } from "../../ui/SettingsRow";
import { SettingsSection } from "../../ui/SettingsSection";
import { StatusChip } from "../../ui/StatusChip";

type GoogleAdvancedSectionProps = {
  showAdvanced: boolean;
  oauthReady: boolean;
  canManageOAuthApp: boolean;
  oauthManagedByEnv: boolean;
  oauthSetupRequestPending: boolean;
  workspaceOwnerUserId: string;
  oauthClientIdInput: string;
  oauthClientSecretInput: string;
  oauthRedirectUriInput: string;
  oauthRedirectUri: string;
  oauthConfigSaving: boolean;
  busy: boolean;
  oauthManualUrl: string;
  liveEvents: AgentLiveEvent[];
  googleOAuthStatus: GoogleOAuthStatus;
  onToggleAdvanced: () => void;
  onOAuthClientIdInputChange: (value: string) => void;
  onOAuthClientSecretInputChange: (value: string) => void;
  onOAuthRedirectUriInputChange: (value: string) => void;
  onSaveGoogleOAuthConfig: () => void;
  onRequestGoogleOAuthSetup: () => Promise<{ ok: boolean; message: string }>;
  onGoogleAuthModeChange: (mode: "oauth" | "service_account") => void;
};

function GoogleAdvancedSection({
  showAdvanced,
  oauthReady,
  canManageOAuthApp,
  oauthManagedByEnv,
  oauthSetupRequestPending,
  workspaceOwnerUserId,
  oauthClientIdInput,
  oauthClientSecretInput,
  oauthRedirectUriInput,
  oauthRedirectUri,
  oauthConfigSaving,
  busy,
  oauthManualUrl,
  liveEvents,
  googleOAuthStatus,
  onToggleAdvanced,
  onOAuthClientIdInputChange,
  onOAuthClientSecretInputChange,
  onOAuthRedirectUriInputChange,
  onSaveGoogleOAuthConfig,
  onRequestGoogleOAuthSetup,
  onGoogleAuthModeChange,
}: GoogleAdvancedSectionProps) {
  return (
    <SettingsSection title="Advanced" subtitle="Admin setup and diagnostics.">
      <SettingsRow
        title="Advanced controls"
        description="Hidden by default to keep onboarding simple."
        right={
          <button
            type="button"
            onClick={onToggleAdvanced}
            className="rounded-xl border border-[#d2d2d7] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7]"
          >
            {showAdvanced ? "Hide" : "Show"}
          </button>
        }
        noDivider={!showAdvanced}
      />
      {showAdvanced ? (
        <>
          <SettingsRow
            title="Admin setup"
            description={
              oauthReady
                ? "OAuth app credentials are configured."
                : canManageOAuthApp
                  ? "Save OAuth app credentials once for the workspace."
                  : "Your workspace owner must complete OAuth setup once."
            }
            right={
              <StatusChip
                label={oauthReady ? "Configured" : "Required"}
                tone={oauthReady ? "success" : "warning"}
              />
            }
          >
            {canManageOAuthApp ? (
              <>
                <div className="grid gap-2 sm:grid-cols-2">
                  <input
                    value={oauthClientIdInput}
                    onChange={(event) => onOAuthClientIdInputChange(event.target.value)}
                    placeholder="Google OAuth client ID"
                    className="w-full rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] text-[#1d1d1f]"
                  />
                  <input
                    value={oauthClientSecretInput}
                    onChange={(event) => onOAuthClientSecretInputChange(event.target.value)}
                    placeholder={
                      googleOAuthStatus.oauth_client_secret_configured
                        ? "Google OAuth client secret (configured)"
                        : "Google OAuth client secret"
                    }
                    className="w-full rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] text-[#1d1d1f]"
                  />
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <input
                    value={oauthRedirectUriInput}
                    onChange={(event) => onOAuthRedirectUriInputChange(event.target.value)}
                    placeholder={oauthRedirectUri}
                    className="min-w-[320px] flex-1 rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] text-[#1d1d1f]"
                  />
                  <button
                    type="button"
                    disabled={busy || oauthConfigSaving}
                    onClick={onSaveGoogleOAuthConfig}
                    className="rounded-lg bg-[#1d1d1f] px-3 py-2 text-[12px] font-semibold text-white hover:bg-[#2f2f34] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {oauthConfigSaving ? "Saving..." : "Save OAuth app"}
                  </button>
                </div>
                <p className="mt-2 text-[11px] text-[#6e6e73]">
                  Redirect URI must match exactly: {oauthRedirectUriInput || oauthRedirectUri}
                </p>
              </>
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                {!oauthManagedByEnv ? (
                  <button
                    type="button"
                    disabled={busy || oauthSetupRequestPending}
                    onClick={() => void onRequestGoogleOAuthSetup()}
                    className="rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {oauthSetupRequestPending ? "Request sent" : "Request owner setup"}
                  </button>
                ) : null}
                <p className="text-[12px] text-[#6e6e73]">Workspace owner: {workspaceOwnerUserId || "unassigned"}</p>
              </div>
            )}
          </SettingsRow>

          <SettingsRow
            title="Quick actions"
            description="Fallback actions for blocked popups or mode switching."
          >
            <div className="flex flex-wrap items-center gap-2">
              {oauthManualUrl ? (
                <a
                  href={oauthManualUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7]"
                >
                  Open Google login
                </a>
              ) : null}
              <button
                type="button"
                disabled={busy}
                onClick={() => onGoogleAuthModeChange("oauth")}
                className="rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7]"
              >
                Switch to OAuth mode
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => onGoogleAuthModeChange("service_account")}
                className="rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7]"
              >
                Switch to service account mode
              </button>
            </div>
          </SettingsRow>

          <SettingsRow
            title="Event stream"
            description="Recent backend events for diagnostics."
            noDivider
          >
            {liveEvents.length === 0 ? (
              <p className="text-[12px] text-[#6e6e73]">No events yet.</p>
            ) : (
              <div className="space-y-2">
                {liveEvents.slice(0, 8).map((event, index) => (
                  <div
                    key={`${event.type}-${event.timestamp || index}`}
                    className="rounded-lg border border-[#ececf0] bg-[#fafafc] px-3 py-2"
                  >
                    <p className="text-[12px] font-semibold text-[#1d1d1f]">{event.type}</p>
                    <p className="text-[12px] text-[#6e6e73]">{event.message}</p>
                  </div>
                ))}
              </div>
            )}
          </SettingsRow>
        </>
      ) : null}
    </SettingsSection>
  );
}

export { GoogleAdvancedSection };
