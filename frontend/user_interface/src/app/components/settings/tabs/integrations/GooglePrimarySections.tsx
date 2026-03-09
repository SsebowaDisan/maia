import type {
  GoogleWorkspaceAliasRecord,
  GoogleWorkspaceLinkAccessResult,
  GoogleWorkspaceLinkAnalyzeResult,
} from "../../../../../api/integrations";
import { SettingsRow } from "../../ui/SettingsRow";
import { SettingsSection } from "../../ui/SettingsSection";
import { StatusChip } from "../../ui/StatusChip";
import type { GoogleServiceDefinition } from "./googleServices";

type GooglePrimarySectionsProps = {
  statusChipLabel: string;
  statusChipTone: "success" | "warning" | "neutral";
  connected: boolean;
  connectedEmail: string;
  oauthBlocked: boolean;
  canManageOAuthApp: boolean;
  oauthManagedByEnv: boolean;
  workspaceOwnerUserId: string;
  busy: boolean;
  serviceDefinitions: GoogleServiceDefinition[];
  draftServices: string[];
  selectedServices: string[];
  draftScopesCount: number;
  enabledServiceSummary: string;
  hasServiceChanges: boolean;
  connectStepDone: boolean;
  grantStepDone: boolean;
  aliasStepDone: boolean;
  nextAction: "connect" | "grant" | "alias" | "done";
  serviceAccountEmail: string;
  serviceAccountReady: boolean;
  inServiceAccountMode: boolean;
  showAliases: boolean;
  googleWorkspaceAliases: GoogleWorkspaceAliasRecord[];
  linkInput: string;
  aliasInput: string;
  analysisResult: GoogleWorkspaceLinkAnalyzeResult | null;
  accessResult: GoogleWorkspaceLinkAccessResult | null;
  onOpenServicesModal: () => void;
  onDisconnectGoogle: () => void;
  onToggleDraftService: (serviceId: string, checked: boolean) => void;
  onUpdateAccess: () => Promise<void>;
  onResetDraftServices: () => void;
  onToggleAliases: () => void;
  onShowAliases: () => void;
  onCopyServiceEmail: () => Promise<void>;
  serviceEmailCopied: boolean;
  onShareComplete: () => void;
  onLinkInputChange: (value: string) => void;
  onAliasInputChange: (value: string) => void;
  onAddAlias: () => Promise<void>;
};

function GooglePrimarySections({
  statusChipLabel,
  statusChipTone,
  connected,
  connectedEmail,
  oauthBlocked,
  canManageOAuthApp,
  oauthManagedByEnv,
  workspaceOwnerUserId,
  busy,
  serviceDefinitions,
  draftServices,
  selectedServices,
  draftScopesCount,
  enabledServiceSummary,
  hasServiceChanges,
  connectStepDone,
  grantStepDone,
  aliasStepDone,
  nextAction,
  serviceAccountEmail,
  serviceAccountReady,
  inServiceAccountMode,
  showAliases,
  googleWorkspaceAliases,
  linkInput,
  aliasInput,
  analysisResult,
  accessResult,
  onOpenServicesModal,
  onDisconnectGoogle,
  onToggleDraftService,
  onUpdateAccess,
  onResetDraftServices,
  onToggleAliases,
  onShowAliases,
  onCopyServiceEmail,
  serviceEmailCopied,
  onShareComplete,
  onLinkInputChange,
  onAliasInputChange,
  onAddAlias,
}: GooglePrimarySectionsProps) {
  return (
    <>
      <SettingsSection
        title="Google"
        subtitle="Connect your Google account and choose what Maia can access."
        actions={<StatusChip label={statusChipLabel} tone={statusChipTone} />}
      >
        <div className="px-5 py-5 sm:px-6 sm:py-6">
          {!connected ? (
            <div className="rounded-2xl border border-[#ececf0] bg-[#fafafc] p-5">
              <p className="text-[20px] font-semibold text-[#1d1d1f]">Connect Google</p>
              <p className="mt-1 text-[13px] text-[#6e6e73]">
                Choose what Maia can access, then sign in to Google.
              </p>
              {oauthBlocked && !canManageOAuthApp && !oauthManagedByEnv ? (
                <div className="mt-3 rounded-xl border border-[#d2b37b] bg-[#faf5ea] px-3 py-2 text-[12px] text-[#7c5a1f]">
                  Admin setup required. Workspace owner '{workspaceOwnerUserId || "unassigned"}' needs to configure OAuth once.
                </div>
              ) : null}
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  disabled={busy}
                  onClick={onOpenServicesModal}
                  className="rounded-xl bg-[#1d1d1f] px-4 py-2 text-[13px] font-semibold text-white hover:bg-[#2f2f34] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Connect Google
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={onOpenServicesModal}
                  className="text-[12px] font-semibold text-[#6e6e73] underline-offset-2 hover:text-[#1d1d1f] hover:underline"
                >
                  What will Maia access?
                </button>
              </div>
            </div>
          ) : (
            <div className="rounded-2xl border border-[#ececf0] bg-[#fafafc] p-5">
              <p className="text-[20px] font-semibold text-[#1d1d1f]">Connected</p>
              <p className="mt-1 text-[13px] text-[#6e6e73]">
                {connectedEmail || "Google account connected."}
              </p>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={onOpenServicesModal}
                  className="rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Manage access
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={onDisconnectGoogle}
                  className="rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Disconnect
                </button>
              </div>
            </div>
          )}
        </div>
      </SettingsSection>

      <SettingsSection
        title="Access"
        subtitle="Turn features on or off. You can change this anytime."
      >
        {serviceDefinitions.map((service, index) => {
          const checked = draftServices.includes(service.id);
          return (
            <SettingsRow
              key={service.id}
              title={service.label}
              description={service.description}
              right={<StatusChip tone={checked ? "success" : "neutral"} label={checked ? "On" : "Off"} />}
              noDivider={index === serviceDefinitions.length - 1}
            >
              <label className="inline-flex cursor-pointer items-center gap-2 text-[12px] text-[#1d1d1f]">
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(event) => onToggleDraftService(service.id, event.target.checked)}
                  className="h-4 w-4 rounded border-[#d2d2d7]"
                />
                Enable {service.label}
              </label>
            </SettingsRow>
          );
        })}
        <SettingsRow
          title="Access changes"
          description={`Scopes requested: ${draftScopesCount}`}
          right={
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={busy || draftServices.length === 0}
                onClick={() => void onUpdateAccess()}
                className="rounded-xl bg-[#1d1d1f] px-4 py-2 text-[13px] font-semibold text-white hover:bg-[#2f2f34] disabled:cursor-not-allowed disabled:opacity-60"
              >
                Update access
              </button>
              {hasServiceChanges ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={onResetDraftServices}
                  className="rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Cancel changes
                </button>
              ) : null}
            </div>
          }
          noDivider
        >
          <p className="text-[12px] text-[#6e6e73]">Enabled services: {enabledServiceSummary}</p>
        </SettingsRow>
      </SettingsSection>

      {nextAction !== "done" ? (
        <SettingsSection title="Setup" subtitle="Finish these three steps to complete Google onboarding.">
          <SettingsRow
            title="Progress"
            description="Step 1: Connect. Step 2: Grant access. Step 3: Save first alias."
            right={
              <div className="flex items-center gap-2">
                <StatusChip tone={connectStepDone ? "success" : "neutral"} label="1" />
                <StatusChip tone={grantStepDone ? "success" : "neutral"} label="2" />
                <StatusChip tone={aliasStepDone ? "success" : "neutral"} label="3" />
              </div>
            }
            noDivider
          >
            <div className="flex flex-wrap gap-2">
              {!connectStepDone ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={onOpenServicesModal}
                  className="rounded-xl bg-[#1d1d1f] px-4 py-2 text-[13px] font-semibold text-white hover:bg-[#2f2f34] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Connect Google
                </button>
              ) : null}
              {connectStepDone && !grantStepDone ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void onUpdateAccess()}
                  className="rounded-xl bg-[#1d1d1f] px-4 py-2 text-[13px] font-semibold text-white hover:bg-[#2f2f34] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Update access
                </button>
              ) : null}
              {connectStepDone && grantStepDone && !aliasStepDone ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={onShowAliases}
                  className="rounded-xl bg-[#1d1d1f] px-4 py-2 text-[13px] font-semibold text-white hover:bg-[#2f2f34] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Add first alias
                </button>
              ) : null}
            </div>
          </SettingsRow>
        </SettingsSection>
      ) : null}

      <SettingsSection
        title="Service account sharing"
        subtitle="For company sharing workflows, copy this email and share resources with it."
      >
        <SettingsRow
          title="Service account email"
          description={serviceAccountEmail || "No service-account email configured yet."}
          right={
            <div className="flex items-center gap-2">
              <StatusChip
                label={serviceAccountReady ? (inServiceAccountMode ? "Active" : "Available") : "Not configured"}
                tone={serviceAccountReady ? "success" : "warning"}
              />
              <button
                type="button"
                disabled={busy || !serviceAccountReady}
                onClick={() => void onCopyServiceEmail()}
                className={`rounded-xl border px-3 py-2 text-[12px] font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
                  serviceEmailCopied
                    ? "border-[#b7d7bd] bg-[#eff8f1] text-[#1f6b2b]"
                    : "border-[#d2d2d7] bg-white text-[#1d1d1f] hover:bg-[#f5f5f7]"
                }`}
              >
                {serviceEmailCopied ? "Copied" : "Copy service email"}
              </button>
              <button
                type="button"
                disabled={busy || !serviceAccountReady}
                onClick={onShareComplete}
                className="rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:cursor-not-allowed disabled:opacity-60"
              >
                I shared it, add link
              </button>
            </div>
          }
          noDivider
        >
          <p className="text-[12px] text-[#6e6e73]">
            Share the target Drive file, Doc, Sheet, or GA4 property with this email when using company-wide access.
          </p>
          <p className="mt-1 text-[12px] text-[#6e6e73]">
            Next: share in Google, click "I shared it, add link", then paste the link to save an alias.
          </p>
        </SettingsRow>
      </SettingsSection>

      <SettingsSection
        title="Aliases"
        subtitle="Save a Drive, Docs, Sheets, or GA4 link as a short name for prompts."
      >
        <SettingsRow
          title="Alias shortcuts"
          description="Collapsed by default for focus. Expand when you need it."
          right={
            <button
              type="button"
              onClick={onToggleAliases}
              className="rounded-xl border border-[#d2d2d7] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7]"
            >
              {showAliases ? "Hide" : "Show"}
            </button>
          }
          noDivider={!showAliases}
        />
        {showAliases ? (
          <>
            <SettingsRow
              title="Add alias"
              description="Paste a link. Maia auto-detects and checks access, then saves the alias."
              noDivider={googleWorkspaceAliases.length === 0}
            >
              <div className="grid gap-2 sm:grid-cols-[1fr_220px_auto]">
                <input
                  value={linkInput}
                  onChange={(event) => onLinkInputChange(event.target.value)}
                  placeholder="Paste Google link"
                  className="w-full rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] text-[#1d1d1f]"
                />
                <input
                  value={aliasInput}
                  onChange={(event) => onAliasInputChange(event.target.value)}
                  placeholder="Alias (optional)"
                  className="w-full rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] text-[#1d1d1f]"
                />
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void onAddAlias()}
                  className="rounded-lg bg-[#1d1d1f] px-3 py-2 text-[12px] font-semibold text-white hover:bg-[#2f2f34] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Save alias
                </button>
              </div>
              {accessResult ? (
                <p className={`mt-2 text-[12px] ${accessResult.ready ? "text-[#2d5937]" : "text-[#7c5a1f]"}`}>
                  {accessResult.ready
                    ? `Ready (${accessResult.required_role})`
                    : `Needs ${accessResult.required_role} access`}
                </p>
              ) : analysisResult ? (
                <p className="mt-2 text-[12px] text-[#6e6e73]">
                  {analysisResult.detected ? "Resource detected." : analysisResult.message || "Could not detect resource."}
                </p>
              ) : null}
            </SettingsRow>
            {googleWorkspaceAliases.map((row, index) => (
              <SettingsRow
                key={`${row.alias}-${row.resource_id}-${index}`}
                title={row.alias}
                description={`${row.resource_type} - ${row.resource_id}`}
                right={<StatusChip label="Saved" tone="neutral" />}
                noDivider={index === googleWorkspaceAliases.length - 1}
              />
            ))}
          </>
        ) : null}
      </SettingsSection>
    </>
  );
}

export { GooglePrimarySections };
