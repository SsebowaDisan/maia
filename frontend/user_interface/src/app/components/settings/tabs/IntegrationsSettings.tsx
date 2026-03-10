import { useEffect, useMemo, useRef, useState } from "react";

import type { AgentLiveEvent, GoogleOAuthStatus } from "../../../../api/client";
import type {
  GoogleServiceAccountStatus,
  GoogleWorkspaceAliasRecord,
  GoogleWorkspaceLinkAccessResult,
  GoogleWorkspaceLinkAnalyzeResult,
} from "../../../../api/integrations";
import type { GoogleToolHealthItem } from "../types";
import { toneFromBoolean } from "../ui/StatusChip";
import { GoogleAdvancedSection } from "./integrations/GoogleAdvancedSection";
import { GooglePrimarySections } from "./integrations/GooglePrimarySections";
import { GoogleServicesModal } from "./integrations/GoogleServicesModal";
import {
  GOOGLE_SERVICE_DEFS,
  DEFAULT_SERVICES,
  buildSuggestedAlias,
  hasAllScopes,
  normalizeAliasText,
  normalizeServiceIds,
  sameList,
  scopesFromServices,
  serviceIdsFromScopes,
  serviceLabel,
} from "./integrations/googleServices";

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
  ga4PropertyId: string;
  ga4PropertyIdInput: string;
  onGa4PropertyIdInputChange: (value: string) => void;
  onSaveGa4PropertyId: () => Promise<{ ok: boolean; message: string }>;
  onAnalyzeGoogleLink: (link: string) => Promise<GoogleWorkspaceLinkAnalyzeResult>;
  onCheckGoogleLinkAccess: (payload: {
    link: string;
    action: "read" | "edit";
  }) => Promise<GoogleWorkspaceLinkAccessResult>;
  onSaveGoogleLinkAlias: (alias: string, link: string) => Promise<GoogleWorkspaceAliasRecord[]>;
};

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
    ga4PropertyId,
    ga4PropertyIdInput,
    onGa4PropertyIdInputChange,
    onSaveGa4PropertyId,
    onAnalyzeGoogleLink,
    onCheckGoogleLinkAccess,
    onSaveGoogleLinkAlias,
  } = props;

  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [modalConnectPending, setModalConnectPending] = useState(false);
  const [showServicesModal, setShowServicesModal] = useState(false);
  const [showAliases, setShowAliases] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [oauthManualUrl, setOauthManualUrl] = useState("");
  const [selectedServices, setSelectedServices] = useState<string[]>(DEFAULT_SERVICES);
  const [draftServices, setDraftServices] = useState<string[]>(DEFAULT_SERVICES);
  const [serviceEmailCopied, setServiceEmailCopied] = useState(false);
  const [linkInput, setLinkInput] = useState("");
  const [aliasInput, setAliasInput] = useState("");
  const [analysisResult, setAnalysisResult] = useState<GoogleWorkspaceLinkAnalyzeResult | null>(null);
  const [accessResult, setAccessResult] = useState<GoogleWorkspaceLinkAccessResult | null>(null);
  const copyServiceEmailTimerRef = useRef<number | null>(null);

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

  const clearCopyServiceEmailTimer = () => {
    if (copyServiceEmailTimerRef.current !== null) {
      window.clearTimeout(copyServiceEmailTimerRef.current);
      copyServiceEmailTimerRef.current = null;
    }
  };

  const showServiceEmailCopiedFeedback = () => {
    clearCopyServiceEmailTimer();
    setServiceEmailCopied(true);
    copyServiceEmailTimerRef.current = window.setTimeout(() => {
      setServiceEmailCopied(false);
      copyServiceEmailTimerRef.current = null;
    }, 1600);
  };

  useEffect(
    () => () => {
      clearCopyServiceEmailTimer();
    },
    [],
  );

  useEffect(() => {
    setServiceEmailCopied(false);
    clearCopyServiceEmailTimer();
  }, [serviceAccountEmail]);

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

  const handleModalContinueToGoogle = async () => {
    if (busy || modalConnectPending || draftServices.length === 0) {
      return;
    }
    setModalConnectPending(true);
    try {
      const ok = await startGoogleConnect(draftServices);
      if (ok) {
        setShowServicesModal(false);
      }
    } finally {
      setModalConnectPending(false);
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
      setServiceEmailCopied(false);
      setMessage("Service-account email is not available yet.");
      return;
    }
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(serviceAccountEmail);
        showServiceEmailCopiedFeedback();
        setMessage("Service-account email copied.");
        return;
      }
      setServiceEmailCopied(false);
      setMessage(`Clipboard is unavailable. Service-account email: ${serviceAccountEmail}`);
    } catch {
      setServiceEmailCopied(false);
      setMessage(`Could not copy automatically. Service-account email: ${serviceAccountEmail}`);
    }
  };

  const handleSaveGa4PropertyId = async () => {
    setBusy(true);
    try {
      const result = await onSaveGa4PropertyId();
      setMessage(result.message);
    } catch (error) {
      setMessage(`Could not save GA4 property ID: ${String(error)}`);
    } finally {
      setBusy(false);
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

  const handleToggleDraftService = (serviceId: string, checked: boolean) => {
    setDraftServices((previous) => {
      if (checked) {
        return normalizeServiceIds([...previous, serviceId]);
      }
      return previous.filter((item) => item !== serviceId);
    });
  };

  return (
    <>
      <GooglePrimarySections
        statusChipLabel={statusChip.label}
        statusChipTone={statusChip.tone}
        connected={googleOAuthStatus.connected}
        connectedEmail={googleOAuthStatus.email || ""}
        oauthBlocked={oauthBlocked}
        canManageOAuthApp={canManageOAuthApp}
        oauthManagedByEnv={oauthManagedByEnv}
        workspaceOwnerUserId={workspaceOwnerUserId}
        busy={busy}
        serviceDefinitions={GOOGLE_SERVICE_DEFS}
        draftServices={draftServices}
        selectedServices={selectedServices}
        draftScopesCount={draftScopes.length}
        enabledServiceSummary={enabledServiceSummary}
        hasServiceChanges={hasServiceChanges}
        connectStepDone={connectStepDone}
        grantStepDone={grantStepDone}
        aliasStepDone={aliasStepDone}
        nextAction={nextAction}
        serviceAccountEmail={serviceAccountEmail}
        serviceAccountReady={serviceAccountReady}
        inServiceAccountMode={inServiceAccountMode}
        showAliases={showAliases}
        googleWorkspaceAliases={googleWorkspaceAliases}
        linkInput={linkInput}
        aliasInput={aliasInput}
        analysisResult={analysisResult}
        accessResult={accessResult}
        onOpenServicesModal={() => setShowServicesModal(true)}
        onDisconnectGoogle={onDisconnectGoogle}
        onToggleDraftService={handleToggleDraftService}
        onUpdateAccess={handleUpdateAccess}
        onResetDraftServices={() => setDraftServices(selectedServices)}
        onToggleAliases={() => setShowAliases((value) => !value)}
        onShowAliases={() => setShowAliases(true)}
        onCopyServiceEmail={handleCopyServiceEmail}
        serviceEmailCopied={serviceEmailCopied}
        onShareComplete={handleShareComplete}
        onLinkInputChange={setLinkInput}
        onAliasInputChange={setAliasInput}
        onAddAlias={handleAddAlias}
        ga4PropertyId={ga4PropertyId}
        ga4PropertyIdInput={ga4PropertyIdInput}
        onGa4PropertyIdInputChange={onGa4PropertyIdInputChange}
        onSaveGa4PropertyId={handleSaveGa4PropertyId}
      />

      <GoogleAdvancedSection
        showAdvanced={showAdvanced}
        oauthReady={oauthReady}
        canManageOAuthApp={canManageOAuthApp}
        oauthManagedByEnv={oauthManagedByEnv}
        oauthSetupRequestPending={oauthSetupRequestPending}
        workspaceOwnerUserId={workspaceOwnerUserId}
        oauthClientIdInput={oauthClientIdInput}
        oauthClientSecretInput={oauthClientSecretInput}
        oauthRedirectUriInput={oauthRedirectUriInput}
        oauthRedirectUri={oauthRedirectUri}
        oauthConfigSaving={oauthConfigSaving}
        busy={busy}
        oauthManualUrl={oauthManualUrl}
        liveEvents={liveEvents}
        googleOAuthStatus={googleOAuthStatus}
        onToggleAdvanced={() => setShowAdvanced((value) => !value)}
        onOAuthClientIdInputChange={onOAuthClientIdInputChange}
        onOAuthClientSecretInputChange={onOAuthClientSecretInputChange}
        onOAuthRedirectUriInputChange={onOAuthRedirectUriInputChange}
        onSaveGoogleOAuthConfig={onSaveGoogleOAuthConfig}
        onRequestGoogleOAuthSetup={onRequestGoogleOAuthSetup}
        onGoogleAuthModeChange={onGoogleAuthModeChange}
      />

      <GoogleServicesModal
        open={showServicesModal}
        busy={busy}
        modalConnectPending={modalConnectPending}
        draftServices={draftServices}
        draftScopesCount={draftScopes.length}
        serviceDefinitions={GOOGLE_SERVICE_DEFS}
        onClose={() => setShowServicesModal(false)}
        onCancel={() => {
          setDraftServices(selectedServices);
          setShowServicesModal(false);
        }}
        onContinue={handleModalContinueToGoogle}
        onToggleDraftService={handleToggleDraftService}
      />

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
