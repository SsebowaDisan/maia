import { useEffect, useMemo, useState } from "react";

import type { AgentLiveEvent, GoogleOAuthStatus } from "../../../../api/client";
import type {
  GoogleServiceAccountStatus,
  GoogleWorkspaceAliasRecord,
  GoogleWorkspaceLinkAccessResult,
  GoogleWorkspaceLinkAnalyzeResult,
} from "../../../../api/integrations";
import type { GoogleToolHealthItem } from "../types";
import { SettingsRow } from "../ui/SettingsRow";
import { SettingsSection } from "../ui/SettingsSection";
import { StatusChip, toneFromBoolean } from "../ui/StatusChip";

type IntegrationsSettingsProps = {
  googleOAuthStatus: GoogleOAuthStatus;
  googleServiceAccountStatus: GoogleServiceAccountStatus;
  googleWorkspaceAliases: GoogleWorkspaceAliasRecord[];
  oauthStatus: string;
  oauthClientIdInput: string;
  oauthClientSecretInput: string;
  oauthRedirectUriInput: string;
  oauthConfigSaving: boolean;
  googleToolHealth: GoogleToolHealthItem[];
  liveEvents: AgentLiveEvent[];
  onConnectGoogle: (options?: {
    scopes?: string[];
    toolIds?: string[];
  }) => Promise<{ ok: boolean; authorize_url?: string; message: string }>;
  onDisconnectGoogle: () => void;
  onOAuthClientIdInputChange: (value: string) => void;
  onOAuthClientSecretInputChange: (value: string) => void;
  onOAuthRedirectUriInputChange: (value: string) => void;
  onSaveGoogleOAuthConfig: () => void;
  onRequestGoogleOAuthSetup: () => Promise<{ ok: boolean; message: string }>;
  onSaveGoogleOAuthServices: (services: string[]) => Promise<{
    ok: boolean;
    services: string[];
    message: string;
  }>;
  onGoogleAuthModeChange: (mode: "oauth" | "service_account") => void;
  onAnalyzeGoogleLink: (link: string) => Promise<GoogleWorkspaceLinkAnalyzeResult>;
  onCheckGoogleLinkAccess: (payload: {
    link: string;
    action: "read" | "edit";
  }) => Promise<GoogleWorkspaceLinkAccessResult>;
  onSaveGoogleLinkAlias: (alias: string, link: string) => Promise<GoogleWorkspaceAliasRecord[]>;
};

type GoogleServiceDefinition = {
  id: "gmail" | "drive" | "docs" | "sheets" | "analytics";
  label: string;
  description: string;
  scopes: string[];
};

const BASE_SCOPES = ["openid", "email", "profile"] as const;

const GOOGLE_SERVICE_DEFS: GoogleServiceDefinition[] = [
  {
    id: "gmail",
    label: "Gmail",
    description: "Send, draft, and read emails.",
    scopes: [
      "https://www.googleapis.com/auth/gmail.compose",
      "https://www.googleapis.com/auth/gmail.send",
      "https://www.googleapis.com/auth/gmail.readonly",
    ],
  },
  {
    id: "drive",
    label: "Drive",
    description: "Find and manage files.",
    scopes: ["https://www.googleapis.com/auth/drive"],
  },
  {
    id: "docs",
    label: "Docs",
    description: "Create and edit documents.",
    scopes: ["https://www.googleapis.com/auth/documents"],
  },
  {
    id: "sheets",
    label: "Sheets",
    description: "Create and edit spreadsheets.",
    scopes: ["https://www.googleapis.com/auth/spreadsheets"],
  },
  {
    id: "analytics",
    label: "Analytics",
    description: "Read GA4 reporting.",
    scopes: ["https://www.googleapis.com/auth/analytics.readonly"],
  },
];

const DEFAULT_SERVICES: string[] = ["gmail", "drive", "docs", "sheets"];

function dedupe(values: string[]): string[] {
  const rows: string[] = [];
  for (const raw of values) {
    const value = String(raw || "").trim();
    if (!value || rows.includes(value)) {
      continue;
    }
    rows.push(value);
  }
  return rows;
}

function normalizeServiceIds(serviceIds: string[]): string[] {
  const allowed = new Set(GOOGLE_SERVICE_DEFS.map((item) => item.id));
  return dedupe(serviceIds).filter((value) => allowed.has(value as GoogleServiceDefinition["id"]));
}

function scopesFromServices(serviceIds: string[]): string[] {
  const selected = new Set(normalizeServiceIds(serviceIds));
  const scopes = GOOGLE_SERVICE_DEFS.filter((item) => selected.has(item.id)).flatMap((item) => item.scopes);
  return dedupe([...BASE_SCOPES, ...scopes]);
}

function hasAllScopes(requiredScopes: string[], grantedScopes: string[]): boolean {
  const granted = new Set(grantedScopes.map((item) => String(item || "").trim()).filter(Boolean));
  return requiredScopes.every((scope) => granted.has(scope));
}

function serviceIdsFromScopes(scopes: string[]): string[] {
  const granted = new Set(scopes.map((item) => String(item || "").trim()).filter(Boolean));
  return GOOGLE_SERVICE_DEFS.filter((item) => item.scopes.every((scope) => granted.has(scope))).map(
    (item) => item.id,
  );
}

function serviceLabel(id: string): string {
  const match = GOOGLE_SERVICE_DEFS.find((item) => item.id === id);
  return match ? match.label : id;
}

function normalizeAliasText(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/[^\w\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function buildSuggestedAlias(
  analysis: GoogleWorkspaceLinkAnalyzeResult | null,
  access: GoogleWorkspaceLinkAccessResult | null,
): string {
  const fromName = normalizeAliasText(String(access?.resource_name || ""));
  if (fromName) {
    return fromName.slice(0, 72);
  }

  const resourceType = String(analysis?.resource_type || access?.resource_type || "").trim();
  const resourceId = String(analysis?.resource_id || access?.resource_id || "").trim();
  const shortId = resourceId ? resourceId.slice(-6) : "";

  if (resourceType === "ga4_property" && resourceId) {
    return `ga4 property ${resourceId}`;
  }
  if (resourceType === "google_sheet") {
    return shortId ? `sheet ${shortId}` : "sheet";
  }
  if (resourceType === "google_doc") {
    return shortId ? `doc ${shortId}` : "doc";
  }
  if (resourceType === "google_drive_file") {
    return shortId ? `file ${shortId}` : "file";
  }
  if (shortId) {
    return `resource ${shortId}`;
  }
  return "google resource";
}

function sameList(left: string[], right: string[]): boolean {
  if (left.length !== right.length) {
    return false;
  }
  const a = [...left].sort();
  const b = [...right].sort();
  return a.every((value, index) => value === b[index]);
}

export function IntegrationsSettings(props: IntegrationsSettingsProps) {
  const {
    googleOAuthStatus,
    googleServiceAccountStatus,
    googleWorkspaceAliases,
    oauthStatus,
    oauthClientIdInput,
    oauthClientSecretInput,
    oauthRedirectUriInput,
    oauthConfigSaving,
    googleToolHealth,
    liveEvents,
    onConnectGoogle,
    onDisconnectGoogle,
    onOAuthClientIdInputChange,
    onOAuthClientSecretInputChange,
    onOAuthRedirectUriInputChange,
    onSaveGoogleOAuthConfig,
    onRequestGoogleOAuthSetup,
    onSaveGoogleOAuthServices,
    onGoogleAuthModeChange,
    onAnalyzeGoogleLink,
    onCheckGoogleLinkAccess,
    onSaveGoogleLinkAlias,
  } = props;

  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [showServicesModal, setShowServicesModal] = useState(false);
  const [showAliases, setShowAliases] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [oauthManualUrl, setOauthManualUrl] = useState("");
  const [selectedServices, setSelectedServices] = useState<string[]>(DEFAULT_SERVICES);
  const [draftServices, setDraftServices] = useState<string[]>(DEFAULT_SERVICES);
  const [linkInput, setLinkInput] = useState("");
  const [aliasInput, setAliasInput] = useState("");
  const [analysisResult, setAnalysisResult] = useState<GoogleWorkspaceLinkAnalyzeResult | null>(null);
  const [accessResult, setAccessResult] = useState<GoogleWorkspaceLinkAccessResult | null>(null);

  const inServiceAccountMode = googleServiceAccountStatus.auth_mode === "service_account";
  const oauthMissingEnv = Array.isArray(googleOAuthStatus.oauth_missing_env)
    ? googleOAuthStatus.oauth_missing_env.filter((item) => String(item || "").trim().length > 0)
    : [];
  const oauthReady = googleOAuthStatus.oauth_ready ?? oauthMissingEnv.length === 0;
  const canManageOAuthApp = Boolean(googleOAuthStatus.oauth_can_manage_config);
  const oauthManagedByEnv = Boolean(googleOAuthStatus.oauth_managed_by_env);
  const workspaceOwnerUserId = String(googleOAuthStatus.oauth_workspace_owner_user_id || "").trim();
  const oauthSetupRequestPending = Boolean(googleOAuthStatus.oauth_setup_request_pending);
  const oauthBlocked = !inServiceAccountMode && !oauthReady;
  const serviceAccountEmail = String(googleServiceAccountStatus.email || "").trim();
  const serviceAccountReady = Boolean(serviceAccountEmail);
  const oauthRedirectUri = String(
    googleOAuthStatus.oauth_redirect_uri || "http://localhost:8000/api/agent/oauth/google/callback",
  ).trim();

  const selectedFromStatus = useMemo(() => {
    const fromSaved = Array.isArray(googleOAuthStatus.oauth_selected_services)
      ? normalizeServiceIds(
          googleOAuthStatus.oauth_selected_services.map((item) => String(item || "").trim()),
        )
      : [];
    if (fromSaved.length > 0) {
      return fromSaved;
    }
    const fromEnabled = Array.isArray(googleOAuthStatus.enabled_services)
      ? normalizeServiceIds(
          googleOAuthStatus.enabled_services.map((item) => String(item || "").trim()),
        )
      : [];
    if (fromEnabled.length > 0) {
      return fromEnabled;
    }
    return DEFAULT_SERVICES;
  }, [googleOAuthStatus.enabled_services, googleOAuthStatus.oauth_selected_services]);

  useEffect(() => {
    setSelectedServices(selectedFromStatus);
    setDraftServices((previous) => {
      if (sameList(previous, selectedServices)) {
        return selectedFromStatus;
      }
      return previous;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedFromStatus.join("|")]);

  const draftScopes = useMemo(() => scopesFromServices(draftServices), [draftServices]);
  const selectedScopes = useMemo(() => scopesFromServices(selectedServices), [selectedServices]);
  const hasServiceChanges = !sameList(normalizeServiceIds(draftServices), normalizeServiceIds(selectedServices));
  const grantStepDone =
    googleOAuthStatus.connected && hasAllScopes(selectedScopes, googleOAuthStatus.scopes || []);
  const connectStepDone = googleOAuthStatus.connected;
  const aliasStepDone = googleWorkspaceAliases.length > 0;
  const nextAction = !connectStepDone ? "connect" : !grantStepDone ? "grant" : !aliasStepDone ? "alias" : "done";

  const statusChip = (() => {
    if (googleOAuthStatus.connected) {
      return { tone: "success" as const, label: "Connected" };
    }
    if (oauthBlocked && !canManageOAuthApp && !oauthManagedByEnv) {
      return { tone: "warning" as const, label: "Needs admin setup" };
    }
    if (oauthBlocked) {
      return { tone: "warning" as const, label: "Needs setup" };
    }
    return toneFromBoolean(false, { falseLabel: "Not connected" });
  })();

  const enabledServiceSummary = useMemo(() => {
    const rows = Array.isArray(googleOAuthStatus.enabled_services)
      ? normalizeServiceIds(googleOAuthStatus.enabled_services)
      : serviceIdsFromScopes(googleOAuthStatus.scopes || []);
    if (rows.length === 0) {
      return "No services enabled yet.";
    }
    return rows.map((id) => serviceLabel(id)).join(", ");
  }, [googleOAuthStatus.enabled_services, googleOAuthStatus.scopes]);

  const startGoogleConnect = async (serviceIds: string[]): Promise<boolean> => {
    if (oauthBlocked) {
      if (!canManageOAuthApp && !oauthManagedByEnv) {
        const result = await onRequestGoogleOAuthSetup();
        setMessage(result.message);
        return false;
      }
      setMessage("Admin setup required before users can connect Google.");
      return false;
    }
    const normalized = normalizeServiceIds(serviceIds);
    if (normalized.length === 0) {
      setMessage("Select at least one service.");
      return false;
    }

    setBusy(true);
    try {
      if (inServiceAccountMode) {
        onGoogleAuthModeChange("oauth");
      }
      const saveResult = await onSaveGoogleOAuthServices(normalized);
      if (!saveResult.ok) {
        setMessage(saveResult.message || "Could not save selected services.");
        return false;
      }
      const persisted = normalizeServiceIds(saveResult.services.length > 0 ? saveResult.services : normalized);
      setSelectedServices(persisted);
      setDraftServices(persisted);

      const connectResult = await onConnectGoogle({ scopes: scopesFromServices(persisted) });
      const authorizeUrl = String(connectResult.authorize_url || "").trim();
      if (authorizeUrl) {
        setOauthManualUrl(authorizeUrl);
      }
      setMessage(
        `${connectResult.message}${authorizeUrl ? " If needed, click Open Google login." : ""}`,
      );
      return connectResult.ok;
    } catch (error) {
      setMessage(`Could not start Google sign-in: ${String(error)}`);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const handleUpdateAccess = async () => {
    const normalizedDraft = normalizeServiceIds(draftServices);
    if (normalizedDraft.length === 0) {
      setMessage("Select at least one service.");
      return;
    }

    setBusy(true);
    try {
      const saveResult = await onSaveGoogleOAuthServices(normalizedDraft);
      if (!saveResult.ok) {
        setMessage(saveResult.message || "Could not update service access.");
        return;
      }
      const persisted = normalizeServiceIds(saveResult.services.length > 0 ? saveResult.services : normalizedDraft);
      setSelectedServices(persisted);
      setDraftServices(persisted);

      if (!googleOAuthStatus.connected) {
        setMessage("Access updated. Next step: connect Google.");
        return;
      }
      const desiredScopes = scopesFromServices(persisted);
      const alreadyGranted = hasAllScopes(desiredScopes, googleOAuthStatus.scopes || []);
      if (alreadyGranted) {
        setMessage("Access updated.");
        return;
      }

      const connectResult = await onConnectGoogle({ scopes: desiredScopes });
      const authorizeUrl = String(connectResult.authorize_url || "").trim();
      if (authorizeUrl) {
        setOauthManualUrl(authorizeUrl);
      }
      setMessage(
        `${connectResult.message}${authorizeUrl ? " If needed, click Open Google login." : ""}`,
      );
    } catch (error) {
      setMessage(`Could not update access: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const handleAddAlias = async () => {
    const link = linkInput.trim();
    if (!link) {
      setMessage("Paste a Google link first.");
      return;
    }

    setBusy(true);
    try {
      const analysis = await onAnalyzeGoogleLink(link);
      setAnalysisResult(analysis);
      if (!analysis.detected) {
        setMessage(analysis.message || "Unsupported link.");
        return;
      }
      const action: "read" | "edit" = analysis.resource_type === "ga4_property" ? "read" : "edit";
      const access = await onCheckGoogleLinkAccess({ link, action });
      setAccessResult(access);
      const aliasToSave = normalizeAliasText(aliasInput.trim() || buildSuggestedAlias(analysis, access)).slice(
        0,
        120,
      );
      if (!aliasToSave) {
        setMessage("Could not create a valid alias name.");
        return;
      }
      await onSaveGoogleLinkAlias(aliasToSave, link);
      setAliasInput(aliasToSave);
      setMessage(
        access.ready
          ? `Alias '${aliasToSave}' saved. Ready (${access.required_role}).`
          : `Alias '${aliasToSave}' saved. Needs ${access.required_role} access.`,
      );
    } catch (error) {
      setMessage(`Could not add alias: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const handleCopyServiceEmail = async () => {
    if (!serviceAccountEmail) {
      setMessage("Service-account email is not available yet.");
      return;
    }
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(serviceAccountEmail);
        setMessage("Service-account email copied.");
        return;
      }
      setMessage(`Clipboard is unavailable. Service-account email: ${serviceAccountEmail}`);
    } catch {
      setMessage(`Could not copy automatically. Service-account email: ${serviceAccountEmail}`);
    }
  };

  const handleShareComplete = () => {
    if (!serviceAccountReady) {
      setMessage("Service-account email is not available yet.");
      return;
    }
    setShowAliases(true);
    setMessage("Paste the Google link you just shared, then click Save alias.");
  };

  return (
    <>
      <SettingsSection
        title="Google"
        subtitle="Connect your Google account and choose what Maia can access."
        actions={<StatusChip label={statusChip.label} tone={statusChip.tone} />}
      >
        <div className="px-5 py-5 sm:px-6 sm:py-6">
          {!googleOAuthStatus.connected ? (
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
                  onClick={() => setShowServicesModal(true)}
                  className="rounded-xl bg-[#1d1d1f] px-4 py-2 text-[13px] font-semibold text-white hover:bg-[#2f2f34] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Connect Google
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setShowServicesModal(true)}
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
                {googleOAuthStatus.email || "Google account connected."}
              </p>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setShowServicesModal(true)}
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
        {GOOGLE_SERVICE_DEFS.map((service, index) => {
          const checked = draftServices.includes(service.id);
          return (
            <SettingsRow
              key={service.id}
              title={service.label}
              description={service.description}
              right={<StatusChip tone={checked ? "success" : "neutral"} label={checked ? "On" : "Off"} />}
              noDivider={index === GOOGLE_SERVICE_DEFS.length - 1}
            >
              <label className="inline-flex cursor-pointer items-center gap-2 text-[12px] text-[#1d1d1f]">
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(event) => {
                    const nextChecked = event.target.checked;
                    setDraftServices((previous) => {
                      if (nextChecked) {
                        return normalizeServiceIds([...previous, service.id]);
                      }
                      return previous.filter((item) => item !== service.id);
                    });
                  }}
                  className="h-4 w-4 rounded border-[#d2d2d7]"
                />
                Enable {service.label}
              </label>
            </SettingsRow>
          );
        })}
        <SettingsRow
          title="Access changes"
          description={`Scopes requested: ${draftScopes.length}`}
          right={
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={busy || draftServices.length === 0}
                onClick={() => void handleUpdateAccess()}
                className="rounded-xl bg-[#1d1d1f] px-4 py-2 text-[13px] font-semibold text-white hover:bg-[#2f2f34] disabled:cursor-not-allowed disabled:opacity-60"
              >
                Update access
              </button>
              {hasServiceChanges ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setDraftServices(selectedServices)}
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
                  onClick={() => setShowServicesModal(true)}
                  className="rounded-xl bg-[#1d1d1f] px-4 py-2 text-[13px] font-semibold text-white hover:bg-[#2f2f34] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Connect Google
                </button>
              ) : null}
              {connectStepDone && !grantStepDone ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void handleUpdateAccess()}
                  className="rounded-xl bg-[#1d1d1f] px-4 py-2 text-[13px] font-semibold text-white hover:bg-[#2f2f34] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Update access
                </button>
              ) : null}
              {connectStepDone && grantStepDone && !aliasStepDone ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setShowAliases(true)}
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
                onClick={() => void handleCopyServiceEmail()}
                className="rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:cursor-not-allowed disabled:opacity-60"
              >
                Copy service email
              </button>
              <button
                type="button"
                disabled={busy || !serviceAccountReady}
                onClick={handleShareComplete}
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
              onClick={() => setShowAliases((value) => !value)}
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
                  onChange={(event) => setLinkInput(event.target.value)}
                  placeholder="Paste Google link"
                  className="w-full rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] text-[#1d1d1f]"
                />
                <input
                  value={aliasInput}
                  onChange={(event) => setAliasInput(event.target.value)}
                  placeholder="Alias (optional)"
                  className="w-full rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] text-[#1d1d1f]"
                />
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void handleAddAlias()}
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

      <SettingsSection title="Advanced" subtitle="Admin setup and diagnostics.">
        <SettingsRow
          title="Advanced controls"
          description="Hidden by default to keep onboarding simple."
          right={
            <button
              type="button"
              onClick={() => setShowAdvanced((value) => !value)}
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
                      onClick={() => onSaveGoogleOAuthConfig()}
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

      {showServicesModal ? (
        <div
          className="fixed inset-0 z-[120] flex items-center justify-center bg-black/35 px-4"
          role="dialog"
          aria-modal="true"
          aria-label="Choose Google services"
          onClick={() => setShowServicesModal(false)}
        >
          <div
            className="w-full max-w-[560px] rounded-2xl border border-[#d2d2d7] bg-white p-5 shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <p className="text-[20px] font-semibold text-[#1d1d1f]">Choose services</p>
            <p className="mt-1 text-[13px] text-[#6e6e73]">Choose what Maia can access in your Google account.</p>
            <div className="mt-4 space-y-2">
              {GOOGLE_SERVICE_DEFS.map((service) => {
                const checked = draftServices.includes(service.id);
                return (
                  <label
                    key={`modal-${service.id}`}
                    className="flex cursor-pointer items-start gap-2 rounded-lg border border-[#ececf0] bg-[#fafafc] px-3 py-2"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(event) => {
                        const nextChecked = event.target.checked;
                        setDraftServices((previous) => {
                          if (nextChecked) {
                            return normalizeServiceIds([...previous, service.id]);
                          }
                          return previous.filter((item) => item !== service.id);
                        });
                      }}
                      className="mt-0.5 h-4 w-4 rounded border-[#d2d2d7]"
                    />
                    <span>
                      <span className="block text-[13px] font-semibold text-[#1d1d1f]">{service.label}</span>
                      <span className="block text-[12px] text-[#6e6e73]">{service.description}</span>
                    </span>
                  </label>
                );
              })}
            </div>
            <p className="mt-3 text-[11px] text-[#6e6e73]">Scopes requested: {draftScopes.length}</p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setDraftServices(selectedServices);
                  setShowServicesModal(false);
                }}
                className="rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7]"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={busy || draftServices.length === 0}
                onClick={async () => {
                  const ok = await startGoogleConnect(draftServices);
                  if (ok) {
                    setShowServicesModal(false);
                  }
                }}
                className="rounded-lg bg-[#1d1d1f] px-3 py-2 text-[12px] font-semibold text-white hover:bg-[#2f2f34] disabled:cursor-not-allowed disabled:opacity-60"
              >
                Continue to Google
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {oauthStatus ? (
        <div className="rounded-xl border border-[#ececf0] bg-white px-4 py-3">
          <p className="text-[12px] text-[#6e6e73]">{oauthStatus}</p>
        </div>
      ) : null}
      {message ? (
        <div className="rounded-xl border border-[#ececf0] bg-white px-4 py-3">
          <p className="text-[12px] text-[#6e6e73]">{message}</p>
        </div>
      ) : null}

      <div className="hidden">{googleToolHealth.length}</div>
    </>
  );
}
