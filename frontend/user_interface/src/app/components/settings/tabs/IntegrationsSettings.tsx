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
  onGoogleAuthModeChange: (mode: "oauth" | "service_account") => void;
  onAnalyzeGoogleLink: (link: string) => Promise<GoogleWorkspaceLinkAnalyzeResult>;
  onCheckGoogleLinkAccess: (payload: {
    link: string;
    action: "read" | "edit";
  }) => Promise<GoogleWorkspaceLinkAccessResult>;
  onSaveGoogleLinkAlias: (alias: string, link: string) => Promise<GoogleWorkspaceAliasRecord[]>;
};

type SetupStepState = "pending" | "running" | "done" | "needs_user";

type SetupStep = {
  id: string;
  label: string;
  state: SetupStepState;
};

type NextSetupAction =
  | "connect_google"
  | "open_google_login"
  | "configure_oauth_env"
  | "request_oauth_setup"
  | "switch_to_oauth"
  | "copy_service_email"
  | "quick_add_clipboard"
  | "done";

type NextSetupResolution = {
  action: NextSetupAction;
  label: string;
  description: string;
  tone: "success" | "neutral" | "warning";
};

type GoogleToolScopeDefinition = {
  id: "gmail" | "google_calendar" | "google_workspace" | "google_analytics";
  label: string;
  description: string;
  scopes: string[];
};

const GOOGLE_BASE_SCOPES = ["openid", "email", "profile"] as const;

const GOOGLE_TOOL_SCOPE_DEFS: GoogleToolScopeDefinition[] = [
  {
    id: "gmail",
    label: "Gmail",
    description: "Draft, send, and read mailbox messages for agent actions.",
    scopes: [
      "https://www.googleapis.com/auth/gmail.compose",
      "https://www.googleapis.com/auth/gmail.send",
      "https://www.googleapis.com/auth/gmail.readonly",
    ],
  },
  {
    id: "google_calendar",
    label: "Calendar",
    description: "Create and manage calendar events.",
    scopes: ["https://www.googleapis.com/auth/calendar.events"],
  },
  {
    id: "google_workspace",
    label: "Drive, Docs, and Sheets",
    description: "Create and update shared files, docs, and spreadsheets.",
    scopes: [
      "https://www.googleapis.com/auth/drive",
      "https://www.googleapis.com/auth/documents",
      "https://www.googleapis.com/auth/spreadsheets",
    ],
  },
  {
    id: "google_analytics",
    label: "Google Analytics",
    description: "Read GA4 reporting data.",
    scopes: ["https://www.googleapis.com/auth/analytics.readonly"],
  },
];

const DEFAULT_SELECTED_GOOGLE_TOOLS = GOOGLE_TOOL_SCOPE_DEFS.map((item) => item.id);

function dedupeScopes(scopes: string[]): string[] {
  const seen = new Set<string>();
  const rows: string[] = [];
  for (const raw of scopes) {
    const scope = String(raw || "").trim();
    if (!scope || seen.has(scope)) {
      continue;
    }
    seen.add(scope);
    rows.push(scope);
  }
  return rows;
}

function toolIdsFromGrantedScopes(scopes: string[]): string[] {
  const granted = new Set(scopes.map((item) => String(item || "").trim()).filter(Boolean));
  return GOOGLE_TOOL_SCOPE_DEFS.filter((tool) => tool.scopes.every((scope) => granted.has(scope))).map(
    (tool) => tool.id,
  );
}

function expandScopesFromToolIds(toolIds: string[]): string[] {
  const selectedSet = new Set(toolIds.map((item) => String(item || "").trim()).filter(Boolean));
  const scoped = GOOGLE_TOOL_SCOPE_DEFS.filter((tool) => selectedSet.has(tool.id)).flatMap(
    (tool) => tool.scopes,
  );
  return dedupeScopes([...GOOGLE_BASE_SCOPES, ...scoped]);
}

function hasAllScopes(requiredScopes: string[], grantedScopes: string[]): boolean {
  const granted = new Set(grantedScopes.map((item) => String(item || "").trim()).filter(Boolean));
  return requiredScopes.every((scope) => granted.has(scope));
}

function healthTone(item: GoogleToolHealthItem): { tone: "success" | "neutral" | "warning"; label: string } {
  if (item.ok) {
    return { tone: "success", label: "Connected" };
  }
  const lowerMessage = item.message.toLowerCase();
  if (lowerMessage.includes("error") || lowerMessage.includes("failed")) {
    return { tone: "warning", label: "Needs attention" };
  }
  return { tone: "neutral", label: "Not connected" };
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
    return shortId ? `shared sheet ${shortId}` : "shared sheet";
  }
  if (resourceType === "google_doc") {
    return shortId ? `shared doc ${shortId}` : "shared doc";
  }
  if (resourceType === "google_drive_file") {
    return shortId ? `shared file ${shortId}` : "shared file";
  }
  if (shortId) {
    return `google resource ${shortId}`;
  }
  return "shared google resource";
}

function stepChip(state: SetupStepState): { tone: "success" | "neutral" | "warning"; label: string } {
  if (state === "done") {
    return { tone: "success", label: "Done" };
  }
  if (state === "needs_user") {
    return { tone: "warning", label: "Action needed" };
  }
  if (state === "running") {
    return { tone: "neutral", label: "Running" };
  }
  return { tone: "neutral", label: "Pending" };
}

function buildSetupSteps(mode: "oauth" | "service_account"): SetupStep[] {
  if (mode === "service_account") {
    return [
      { id: "mode", label: "Switch to service account mode", state: "pending" },
      { id: "share", label: "Copy service email and share resource", state: "pending" },
      { id: "alias", label: "Quick-add first alias from copied link", state: "pending" },
    ];
  }
  return [
    { id: "mode", label: "Switch to OAuth mode", state: "pending" },
    { id: "connect", label: "Connect Google account", state: "pending" },
    { id: "alias", label: "Quick-add first alias from copied link", state: "pending" },
  ];
}

export function IntegrationsSettings({
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
  onGoogleAuthModeChange,
  onAnalyzeGoogleLink,
  onCheckGoogleLinkAccess,
  onSaveGoogleLinkAlias,
}: IntegrationsSettingsProps) {
  const oauthChip = toneFromBoolean(googleOAuthStatus.connected, {
    trueLabel: "Connected",
    falseLabel: "Not connected",
  });
  const [showToolDetails, setShowToolDetails] = useState(false);
  const [copyStatus, setCopyStatus] = useState("");
  const [assistantStatus, setAssistantStatus] = useState("");
  const [assistantBusy, setAssistantBusy] = useState(false);
  const [setupBusy, setSetupBusy] = useState(false);
  const [setupStatus, setSetupStatus] = useState("");
  const [setupStepsState, setSetupStepsState] = useState<SetupStep[]>([]);
  const [showAdvancedSettings, setShowAdvancedSettings] = useState(false);
  const [oauthManualUrl, setOauthManualUrl] = useState("");
  const [linkInput, setLinkInput] = useState("");
  const [aliasInput, setAliasInput] = useState("");
  const [linkAction, setLinkAction] = useState<"read" | "edit">("read");
  const [selectedOauthToolIds, setSelectedOauthToolIds] = useState<string[]>(DEFAULT_SELECTED_GOOGLE_TOOLS);
  const [analysisResult, setAnalysisResult] = useState<GoogleWorkspaceLinkAnalyzeResult | null>(null);
  const [accessResult, setAccessResult] = useState<GoogleWorkspaceLinkAccessResult | null>(null);
  const serviceChip = toneFromBoolean(googleServiceAccountStatus.usable, {
    trueLabel: "Ready",
    falseLabel: googleServiceAccountStatus.configured ? "Share-only" : "Not configured",
  });
  const inServiceAccountMode = googleServiceAccountStatus.auth_mode === "service_account";
  const trackedGoogleToolHealth =
    inServiceAccountMode || selectedOauthToolIds.length === 0
      ? googleToolHealth
      : googleToolHealth.filter((item) => selectedOauthToolIds.includes(item.id));
  const connectedTools = trackedGoogleToolHealth.filter((item) => item.ok).length;
  const grantedToolIds = useMemo(() => {
    const explicit = Array.isArray(googleOAuthStatus.enabled_tools)
      ? googleOAuthStatus.enabled_tools
      : [];
    if (explicit.length > 0) {
      return explicit;
    }
    return toolIdsFromGrantedScopes(googleOAuthStatus.scopes || []);
  }, [googleOAuthStatus.enabled_tools, googleOAuthStatus.scopes]);

  useEffect(() => {
    if (!googleOAuthStatus.connected) {
      return;
    }
    setSelectedOauthToolIds(grantedToolIds.length > 0 ? grantedToolIds : DEFAULT_SELECTED_GOOGLE_TOOLS);
  }, [googleOAuthStatus.connected, grantedToolIds]);

  const selectedOauthScopes = useMemo(
    () => expandScopesFromToolIds(selectedOauthToolIds),
    [selectedOauthToolIds],
  );
  const workspaceToolScopes =
    GOOGLE_TOOL_SCOPE_DEFS.find((item) => item.id === "google_workspace")?.scopes || [];
  const workspaceToolSelected = selectedOauthToolIds.includes("google_workspace");
  const workspaceScopesGranted = hasAllScopes(workspaceToolScopes, googleOAuthStatus.scopes || []);
  const oauthScopeReady = hasAllScopes(selectedOauthScopes, googleOAuthStatus.scopes || []);
  const canManageOAuthApp = Boolean(googleOAuthStatus.oauth_can_manage_config);
  const workspaceOwnerUserId = String(googleOAuthStatus.oauth_workspace_owner_user_id || "").trim();
  const oauthSetupRequestPending = Boolean(googleOAuthStatus.oauth_setup_request_pending);
  const oauthSetupRequestCount = Number(googleOAuthStatus.oauth_setup_request_count || 0);
  const oauthManagedByEnv = Boolean(googleOAuthStatus.oauth_managed_by_env);
  const quickSteps = [
    {
      id: "connect",
      label: inServiceAccountMode ? "Configure service account" : "Connect Google account",
      done: inServiceAccountMode ? googleServiceAccountStatus.usable : googleOAuthStatus.connected,
    },
    {
      id: "permissions",
      label: inServiceAccountMode ? "Share resources with service email" : "Grant required scopes",
      done: inServiceAccountMode
        ? Boolean(googleServiceAccountStatus.email)
        : selectedOauthToolIds.length > 0 && oauthScopeReady,
    },
    {
      id: "alias",
      label: "Save first link alias",
      done: !workspaceToolSelected || googleWorkspaceAliases.length > 0,
    },
  ];
  const quickDoneCount = quickSteps.filter((step) => step.done).length;
  const quickChip = toneFromBoolean(quickDoneCount === quickSteps.length, {
    trueLabel: "Ready",
    falseLabel: `${quickDoneCount}/${quickSteps.length} done`,
  });
  const setupComplete = quickDoneCount === quickSteps.length;
  const showAdvancedPanels = setupComplete || showAdvancedSettings;
  const setupDone = setupStepsState.length > 0 && setupStepsState.every((step) => step.state === "done");
  const setupNeedsUser = setupStepsState.some((step) => step.state === "needs_user");
  const setupStateChip = setupBusy
    ? { tone: "neutral" as const, label: "Running" }
    : setupDone
      ? { tone: "success" as const, label: "Completed" }
      : setupNeedsUser
        ? { tone: "warning" as const, label: "Action needed" }
        : { tone: "neutral" as const, label: "Idle" };
  const canUseAliasAssistant = inServiceAccountMode
    ? Boolean(googleServiceAccountStatus.email)
    : googleOAuthStatus.connected && workspaceToolSelected && workspaceScopesGranted;
  const aliasPrereqHint = inServiceAccountMode
    ? "Copy and share the service-account email first, then add a link alias."
    : !workspaceToolSelected
      ? "Enable Drive, Docs, and Sheets in tool access first, then reconnect Google."
      : "Connect Google and grant selected tool scopes first, then add a link alias.";
  const quickCompletionPercent = Math.round((quickDoneCount / quickSteps.length) * 100);
  const oauthMissingEnv = Array.isArray(googleOAuthStatus.oauth_missing_env)
    ? googleOAuthStatus.oauth_missing_env.filter((item) => String(item || "").trim().length > 0)
    : [];
  const oauthReady = googleOAuthStatus.oauth_ready ?? oauthMissingEnv.length === 0;
  const oauthBlocked = !inServiceAccountMode && !oauthReady;
  const oauthRequiredKeysSummary = oauthMissingEnv.length
    ? oauthMissingEnv.join(", ")
    : "GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET";
  const oauthRedirectUri = String(
    googleOAuthStatus.oauth_redirect_uri || "http://localhost:8000/api/agent/oauth/google/callback",
  ).trim();
  const oauthSetupHint = canManageOAuthApp
    ? `Save OAuth client credentials below (${oauthRequiredKeysSummary}), then continue with Google sign-in.`
    : oauthManagedByEnv
      ? "Google OAuth is managed by deployment settings. Contact your workspace owner if Google sign-in is unavailable."
      : workspaceOwnerUserId
        ? `Workspace owner '${workspaceOwnerUserId}' must complete one-time OAuth app setup.`
        : "A workspace owner must complete one-time OAuth app setup.";
  const workspaceOwnerHint = canManageOAuthApp
    ? "You are the workspace OAuth owner for this tenant."
    : workspaceOwnerUserId
      ? `Workspace OAuth owner: ${workspaceOwnerUserId}`
      : oauthManagedByEnv
        ? "OAuth app is managed by deployment credentials."
        : "No workspace owner is set yet.";
  const smartSetupBlocked = oauthBlocked && !googleServiceAccountStatus.usable;
  const selectedToolsNeedReconnect =
    googleOAuthStatus.connected &&
    (selectedOauthToolIds.length !== grantedToolIds.length ||
      selectedOauthToolIds.some((toolId) => !grantedToolIds.includes(toolId)) ||
      grantedToolIds.some((toolId) => !selectedOauthToolIds.includes(toolId)));

  const nextSetupAction: NextSetupResolution = (() => {
    if (inServiceAccountMode) {
      if (!googleServiceAccountStatus.email) {
        return {
          action: "switch_to_oauth",
          label: "Switch to OAuth mode",
          description:
            "Service-account email is not available yet. Switch to OAuth for the fastest first connection.",
          tone: "warning",
        };
      }
      if (googleWorkspaceAliases.length === 0) {
        return {
          action: "copy_service_email",
          label: "Copy service email",
          description:
            "Share your target Doc, Sheet, Drive file, or GA4 property with this service email before quick-adding an alias.",
          tone: "neutral",
        };
      }
      return {
        action: "done",
        label: "Setup complete",
        description: "Google integration is ready. You can start using prompt-based workspace actions.",
        tone: "success",
      };
    }

    if (oauthBlocked) {
      if (canManageOAuthApp) {
        return {
          action: "configure_oauth_env",
          label: "Save OAuth app credentials",
          description: oauthSetupHint,
          tone: "warning",
        };
      }
      return {
        action: "request_oauth_setup",
        label: oauthSetupRequestPending ? "Setup request sent" : "Request workspace setup",
        description: oauthSetupRequestPending
          ? "Workspace owner has been notified. Waiting for one-time OAuth app setup."
          : oauthSetupHint,
        tone: oauthSetupRequestPending ? "neutral" : "warning",
      };
    }

    if (!googleOAuthStatus.connected) {
      if (oauthManualUrl) {
        return {
          action: "open_google_login",
          label: "Open Google login",
          description: "Continue the sign-in flow in your browser.",
          tone: "warning",
        };
      }
      return {
        action: "connect_google",
        label: "Connect Google account",
        description: "Sign in once to unlock Gmail, Calendar, Drive, Docs, and Sheets tools.",
        tone: "warning",
      };
    }
    if (!oauthScopeReady) {
      return {
        action: "connect_google",
        label: "Grant selected tool scopes",
        description: selectedToolsNeedReconnect
          ? "Reconnect Google to grant updated tool permissions."
          : "Finish consent to grant the scopes needed by selected tools.",
        tone: "warning",
      };
    }
    if (googleWorkspaceAliases.length === 0) {
      return {
        action: "quick_add_clipboard",
        label: "Quick add first alias",
        description:
          "Copy a Google link (Doc, Sheet, Drive, or GA4) and we will analyze, verify access, and save an alias.",
        tone: "neutral",
      };
    }
    return {
      action: "done",
      label: "Setup complete",
      description: "Google integration is ready. You can start using prompt-based workspace actions.",
      tone: "success",
    };
  })();

  const setSetupStep = (stepId: string, state: SetupStepState) => {
    setSetupStepsState((previous) =>
      previous.map((step) => (step.id === stepId ? { ...step, state } : step)),
    );
  };

  const readClipboardText = async (): Promise<string> => {
    if (typeof navigator === "undefined" || !navigator.clipboard?.readText) {
      return "";
    }
    try {
      return String((await navigator.clipboard.readText()) || "").trim();
    } catch {
      return "";
    }
  };

  const handleCopyServiceEmail = async () => {
    const email = String(googleServiceAccountStatus.email || "").trim();
    if (!email) {
      setCopyStatus("Service-account email is not available yet.");
      return;
    }
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(email);
        setCopyStatus("Service-account email copied.");
        return;
      }
      setCopyStatus("Clipboard API is unavailable in this browser.");
    } catch {
      setCopyStatus("Failed to copy service-account email.");
    }
  };

  const handleConnectGoogleAction = async (): Promise<boolean> => {
    if (oauthBlocked) {
      const message = `Google OAuth is blocked. ${oauthSetupHint}`;
      setOauthManualUrl("");
      setSetupStatus(message);
      return false;
    }
    try {
      const connectOptions = canManageOAuthApp
        ? { scopes: selectedOauthScopes, toolIds: selectedOauthToolIds }
        : undefined;
      const result = await onConnectGoogle(connectOptions);
      const authorizeUrl = String(result.authorize_url || "").trim();
      if (authorizeUrl) {
        setOauthManualUrl(authorizeUrl);
      }
      if (result.ok) {
        setSetupStatus(
          `${result.message}${authorizeUrl ? " If no redirect happened, click 'Open Google login'." : ""}`,
        );
        return true;
      }
      setSetupStatus(result.message || "Could not start Google OAuth.");
      return false;
    } catch (error) {
      setSetupStatus(`Could not start Google OAuth: ${String(error)}`);
      return false;
    }
  };

  const handleRequestOAuthSetupAction = async (): Promise<boolean> => {
    if (oauthSetupRequestPending) {
      const message = "Setup request already sent. Waiting for workspace owner to finish OAuth app setup.";
      setSetupStatus(message);
      setAssistantStatus(message);
      return true;
    }
    try {
      const result = await onRequestGoogleOAuthSetup();
      setSetupStatus(result.message);
      setAssistantStatus(result.message);
      return result.ok;
    } catch (error) {
      const message = `Could not submit setup request: ${String(error)}`;
      setSetupStatus(message);
      setAssistantStatus(message);
      return false;
    }
  };

  const handleAnalyzeLink = async () => {
    const link = linkInput.trim();
    if (!link) {
      setAssistantStatus("Paste a Google link or saved alias first.");
      return;
    }
    setAssistantBusy(true);
    try {
      const result = await onAnalyzeGoogleLink(link);
      setAnalysisResult(result);
      if (result.detected) {
        setAssistantStatus("Link analyzed successfully.");
      } else {
        setAssistantStatus(result.message || "Could not detect a supported Google resource.");
      }
    } catch (error) {
      setAssistantStatus(`Analyze failed: ${String(error)}`);
    } finally {
      setAssistantBusy(false);
    }
  };

  const handleCheckLinkAccess = async () => {
    if (!canUseAliasAssistant) {
      setAssistantStatus(aliasPrereqHint);
      return;
    }
    const link = linkInput.trim();
    if (!link) {
      setAssistantStatus("Paste a Google link or alias before checking access.");
      return;
    }
    setAssistantBusy(true);
    try {
      const result = await onCheckGoogleLinkAccess({ link, action: linkAction });
      setAccessResult(result);
      setAssistantStatus(result.message || (result.ready ? "Access ready." : "Access not ready."));
    } catch (error) {
      setAssistantStatus(`Access check failed: ${String(error)}`);
    } finally {
      setAssistantBusy(false);
    }
  };

  const handleSaveAlias = async () => {
    const alias = aliasInput.trim();
    const link = linkInput.trim();
    if (!alias || !link) {
      setAssistantStatus("Both alias and link are required to save.");
      return;
    }
    setAssistantBusy(true);
    try {
      await onSaveGoogleLinkAlias(alias, link);
      setAssistantStatus(`Alias '${alias}' saved.`);
    } catch (error) {
      setAssistantStatus(`Save alias failed: ${String(error)}`);
    } finally {
      setAssistantBusy(false);
    }
  };

  const quickAddLink = async (rawLink: string): Promise<{ ok: boolean; message: string }> => {
    if (!canUseAliasAssistant) {
      return { ok: false, message: aliasPrereqHint };
    }
    const link = String(rawLink || "").trim();
    if (!link) {
      return { ok: false, message: "Copy a Google link first." };
    }

    setLinkInput(link);
    const analysis = await onAnalyzeGoogleLink(link);
    setAnalysisResult(analysis);
    if (!analysis.detected) {
      return {
        ok: false,
        message: analysis.message || "Unsupported link. Paste a Google Docs/Sheets/Drive/GA4 link.",
      };
    }

    const access = await onCheckGoogleLinkAccess({ link, action: linkAction });
    setAccessResult(access);

    const manualAlias = aliasInput.trim();
    const suggestedAlias = buildSuggestedAlias(analysis, access);
    const aliasToSave = normalizeAliasText(manualAlias || suggestedAlias).slice(0, 120);
    if (!aliasToSave) {
      return { ok: false, message: "Could not generate a valid alias for this resource." };
    }

    const existed = googleWorkspaceAliases.some(
      (row) => row.alias.trim().toLowerCase() === aliasToSave.toLowerCase(),
    );
    await onSaveGoogleLinkAlias(aliasToSave, link);
    setAliasInput(aliasToSave);
    return {
      ok: true,
      message: `Alias '${aliasToSave}' ${existed ? "updated" : "saved"}${
        access.ready ? "." : ` (access needs ${access.required_role}).`
      }`,
    };
  };

  const handleQuickAddFromClipboard = async () => {
    if (!canUseAliasAssistant) {
      setAssistantStatus(aliasPrereqHint);
      return;
    }
    setAssistantBusy(true);
    try {
      const clipboardText = await readClipboardText();
      if (!clipboardText) {
        setAssistantStatus("Clipboard is empty or unavailable. Copy a Google link first.");
        return;
      }
      const outcome = await quickAddLink(clipboardText);
      setAssistantStatus(outcome.ok ? `Quick add complete. ${outcome.message}` : `Quick add failed: ${outcome.message}`);
    } catch (error) {
      setAssistantStatus(`Quick add failed: ${String(error)}`);
    } finally {
      setAssistantBusy(false);
    }
  };

  const handleStartSetup = async () => {
    const preferredMode: "oauth" | "service_account" = googleServiceAccountStatus.usable
      ? "service_account"
      : "oauth";
    if (preferredMode === "oauth" && selectedOauthToolIds.length === 0) {
      setSetupStatus("Select at least one Google tool before starting setup.");
      return;
    }
    if (preferredMode === "oauth" && !oauthReady) {
      setSetupStepsState([
        { id: "mode", label: "Switch to OAuth mode", state: "done" },
        { id: "connect", label: "Connect Google account", state: "needs_user" },
        { id: "alias", label: "Quick-add first alias from copied link", state: "pending" },
      ]);
      setSetupStatus(`Setup blocked until OAuth app credentials are saved. ${oauthSetupHint}`);
      return;
    }
    setSetupStepsState(buildSetupSteps(preferredMode));
    setSetupStatus(
      preferredMode === "service_account"
        ? "Using service account mode because tenant service credentials are ready."
        : "Using OAuth mode because service-account credentials are not fully ready.",
    );
    setSetupBusy(true);
    try {
      setSetupStep("mode", "running");
      if (googleServiceAccountStatus.auth_mode !== preferredMode) {
        await onGoogleAuthModeChange(preferredMode);
      }
      setSetupStep("mode", "done");

      if (preferredMode === "oauth") {
        setSetupStep("connect", "running");
        if (!googleOAuthStatus.connected || !oauthScopeReady) {
          setSetupStep("connect", "needs_user");
          setSetupStatus(
            googleOAuthStatus.connected
              ? "Step 2 needs you: reconnect Google to grant selected tool permissions, then click Start setup again."
              : "Step 2 needs you: complete Google login, then click Start setup again.",
          );
          await handleConnectGoogleAction();
          return;
        }
        setSetupStep("connect", "done");
      } else {
        setSetupStep("share", "running");
        const email = String(googleServiceAccountStatus.email || "").trim();
        if (!email) {
          setSetupStep("share", "needs_user");
          setSetupStatus("Service-account email is missing. Configure service-account keys first.");
          return;
        }
        try {
          if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(email);
            setCopyStatus("Service-account email copied.");
          }
        } catch {
          setCopyStatus("Could not auto-copy service-account email.");
        }
        setSetupStep("share", "done");
      }

      setSetupStep("alias", "running");
      const linkCandidate = linkInput.trim() || (await readClipboardText());
      if (!linkCandidate) {
        setSetupStep("alias", "needs_user");
        setSetupStatus("Copy a Google Docs/Sheets/Drive/GA4 link, then click Start setup again.");
        return;
      }
      const outcome = await quickAddLink(linkCandidate);
      if (!outcome.ok) {
        setSetupStep("alias", "needs_user");
        setSetupStatus(outcome.message);
        return;
      }
      setSetupStep("alias", "done");
      setOauthManualUrl("");
      setAssistantStatus(`Quick add complete. ${outcome.message}`);
      setSetupStatus("Smart setup completed. Google integration is ready for prompt-based usage.");
    } catch (error) {
      setSetupStatus(`Smart setup failed: ${String(error)}`);
    } finally {
      setSetupBusy(false);
    }
  };

  const handleRecommendedAction = async () => {
    if (nextSetupAction.action === "done") {
      return;
    }
    if (nextSetupAction.action === "connect_google") {
      await handleConnectGoogleAction();
      return;
    }
    if (nextSetupAction.action === "configure_oauth_env") {
      setSetupStatus(
        canManageOAuthApp
          ? `Save OAuth app credentials first. Redirect URI: ${oauthRedirectUri}`
          : oauthSetupHint,
      );
      return;
    }
    if (nextSetupAction.action === "request_oauth_setup") {
      await handleRequestOAuthSetupAction();
      return;
    }
    if (nextSetupAction.action === "open_google_login") {
      if (!oauthManualUrl) {
        setSetupStatus("Google login link is unavailable. Click Connect now instead.");
        return;
      }
      if (typeof window !== "undefined") {
        const popup = window.open(oauthManualUrl, "_blank", "noopener,noreferrer");
        if (popup && !popup.closed) {
          popup.focus();
          setSetupStatus("Google login opened.");
          return;
        }
        window.location.assign(oauthManualUrl);
        setSetupStatus("Redirecting to Google login.");
      }
      return;
    }
    if (nextSetupAction.action === "switch_to_oauth") {
      onGoogleAuthModeChange("oauth");
      setSetupStatus("Switched to OAuth mode. Next step: connect your Google account.");
      return;
    }
    if (nextSetupAction.action === "copy_service_email") {
      await handleCopyServiceEmail();
      setSetupStatus("Service email copied. Share your target resource, then quick-add an alias.");
      return;
    }
    if (nextSetupAction.action === "quick_add_clipboard") {
      await handleQuickAddFromClipboard();
      return;
    }
    await handleStartSetup();
  };

  return (
    <>
      <SettingsSection
        title="Google Quick Start"
        subtitle="Fastest path: connect, verify access, and save one alias. Most users finish this in under 1 minute."
      >
        <SettingsRow
          title="Recommended next step"
          description={nextSetupAction.description}
          right={<StatusChip label={nextSetupAction.action === "done" ? "Ready" : "Next"} tone={nextSetupAction.tone} />}
        >
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={assistantBusy || setupBusy || nextSetupAction.action === "done"}
              onClick={() => void handleRecommendedAction()}
              className="rounded-lg bg-[#1d1d1f] px-3 py-2 text-[12px] font-semibold text-white hover:bg-[#2f2f34] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {nextSetupAction.label}
            </button>
            {nextSetupAction.action !== "done" ? (
              <button
                type="button"
                disabled={assistantBusy || setupBusy || smartSetupBlocked}
                onClick={() => void handleStartSetup()}
                className="rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:cursor-not-allowed disabled:opacity-60"
              >
                Run smart setup
              </button>
            ) : null}
          </div>
        </SettingsRow>
        <SettingsRow
          title="Workspace OAuth owner"
          description={workspaceOwnerHint}
          right={
            <StatusChip
              label={
                canManageOAuthApp
                  ? "Owner"
                  : oauthManagedByEnv
                    ? "Managed"
                    : workspaceOwnerUserId
                      ? "Member"
                      : "Unassigned"
              }
              tone={canManageOAuthApp ? "success" : workspaceOwnerUserId ? "neutral" : "warning"}
            />
          }
        >
          {!canManageOAuthApp && oauthBlocked && !oauthManagedByEnv ? (
            <button
              type="button"
              disabled={assistantBusy || setupBusy || oauthSetupRequestPending}
              onClick={() => void handleRequestOAuthSetupAction()}
              className="rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {oauthSetupRequestPending ? "Request sent" : "Request setup from owner"}
            </button>
          ) : null}
          {!canManageOAuthApp && oauthSetupRequestCount > 0 ? (
            <p className="mt-2 text-[11px] text-[#6e6e73]">
              Pending workspace setup requests: {oauthSetupRequestCount}
            </p>
          ) : null}
        </SettingsRow>
        {canManageOAuthApp ? (
          <SettingsRow
            title="Tool access permissions"
            description={
              inServiceAccountMode
                ? "OAuth tool scope selection is disabled in service account mode."
                : "Choose what this user allows Maia to access before Google sign-in."
            }
            right={
              <StatusChip
                label={`${selectedOauthToolIds.length}/${GOOGLE_TOOL_SCOPE_DEFS.length} selected`}
                tone={selectedOauthToolIds.length > 0 ? "success" : "warning"}
              />
            }
          >
            <div className="grid gap-2 sm:grid-cols-2">
              {GOOGLE_TOOL_SCOPE_DEFS.map((tool) => {
                const checked = selectedOauthToolIds.includes(tool.id);
                return (
                  <label
                    key={tool.id}
                    className="flex cursor-pointer items-start gap-2 rounded-lg border border-[#ececf0] bg-[#fafafc] px-3 py-2"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={assistantBusy || setupBusy || inServiceAccountMode}
                      onChange={(event) => {
                        const nextChecked = event.target.checked;
                        setSelectedOauthToolIds((previous) => {
                          if (nextChecked) {
                            return Array.from(new Set([...previous, tool.id]));
                          }
                          return previous.filter((item) => item !== tool.id);
                        });
                      }}
                      className="mt-0.5 h-4 w-4 rounded border-[#d2d2d7]"
                    />
                    <span>
                      <span className="block text-[12px] font-semibold text-[#1d1d1f]">{tool.label}</span>
                      <span className="block text-[11px] text-[#6e6e73]">{tool.description}</span>
                    </span>
                  </label>
                );
              })}
            </div>
            {selectedToolsNeedReconnect ? (
              <p className="mt-2 text-[11px] text-[#6e6e73]">
                Tool selection changed. Reconnect Google to grant updated permissions.
              </p>
            ) : null}
            {!inServiceAccountMode ? (
              <p className="mt-1 text-[11px] text-[#6e6e73]">
                OAuth scopes requested: {selectedOauthScopes.length}
              </p>
            ) : null}
          </SettingsRow>
        ) : null}
        {canManageOAuthApp ? (
          <SettingsRow
            title="OAuth app setup"
            description={
              oauthReady
                ? "OAuth app credentials are configured. Users can now connect Google with one click."
                : "One-time workspace owner step: save Google OAuth client credentials here."
            }
            right={
              <StatusChip
                label={oauthReady ? "Configured" : "Action needed"}
                tone={oauthReady ? "success" : "warning"}
              />
            }
          >
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
                placeholder={googleOAuthStatus.oauth_client_secret_configured ? "Google OAuth client secret (configured)" : "Google OAuth client secret"}
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
                disabled={assistantBusy || setupBusy || oauthConfigSaving}
                onClick={() => onSaveGoogleOAuthConfig()}
                className="rounded-lg bg-[#1d1d1f] px-3 py-2 text-[12px] font-semibold text-white hover:bg-[#2f2f34] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {oauthConfigSaving ? "Saving..." : "Save OAuth app"}
              </button>
            </div>
            <p className="mt-2 text-[11px] text-[#6e6e73]">
              Redirect URI in Google Cloud must match exactly: {oauthRedirectUriInput || oauthRedirectUri}
            </p>
          </SettingsRow>
        ) : null}
        <SettingsRow
          title="Setup progress"
          description={`Mode: ${inServiceAccountMode ? "Service account" : "OAuth"} - ${connectedTools}/${trackedGoogleToolHealth.length} tools connected`}
          right={<StatusChip label={quickChip.label} tone={quickChip.tone} />}
        >
          <div className="mb-3">
            <div className="h-2 w-full overflow-hidden rounded-full bg-[#f0f0f4]">
              <div
                className="h-full rounded-full bg-[#1d1d1f] transition-[width] duration-300"
                style={{ width: `${quickCompletionPercent}%` }}
              />
            </div>
            <p className="mt-2 text-[11px] text-[#6e6e73]">{quickCompletionPercent}% complete</p>
          </div>
          <div className="grid gap-2 sm:grid-cols-3">
            {quickSteps.map((step) => (
              <div
                key={step.id}
                className="rounded-lg border border-[#ececf0] bg-[#fafafc] px-3 py-2 text-[12px] text-[#3a3a3c]"
              >
                <p className="font-semibold text-[#1d1d1f]">{step.label}</p>
                <p>{step.done ? "Completed" : "Pending"}</p>
              </div>
            ))}
          </div>
        </SettingsRow>
        <SettingsRow
          title="Quick actions"
          description="Manual shortcuts for power users."
          right={<StatusChip label={assistantBusy || setupBusy ? "Running" : "Idle"} tone="neutral" />}
        >
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={assistantBusy || setupBusy || smartSetupBlocked}
              onClick={() => void handleStartSetup()}
              className="rounded-lg bg-[#1d1d1f] px-3 py-2 text-[12px] font-semibold text-white hover:bg-[#2f2f34] disabled:cursor-not-allowed disabled:opacity-60"
            >
              Run smart setup
            </button>
            {!inServiceAccountMode ? (
              <>
                <button
                  type="button"
                  disabled={assistantBusy || setupBusy || oauthBlocked}
                  onClick={() => void handleConnectGoogleAction()}
                  className="rounded-lg bg-[#2f2f34] px-3 py-2 text-[12px] font-semibold text-white hover:bg-[#434349] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Connect now
                </button>
                {oauthBlocked && !canManageOAuthApp && !oauthManagedByEnv ? (
                  <button
                    type="button"
                    disabled={assistantBusy || setupBusy || oauthSetupRequestPending}
                    onClick={() => void handleRequestOAuthSetupAction()}
                    className="rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {oauthSetupRequestPending ? "Request sent" : "Request setup"}
                  </button>
                ) : null}
              </>
            ) : (
              <button
                type="button"
                disabled={assistantBusy || setupBusy}
                onClick={() => void handleCopyServiceEmail()}
                className="rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:cursor-not-allowed disabled:opacity-60"
              >
                Copy service email
              </button>
            )}
            <button
              type="button"
              disabled={assistantBusy || setupBusy || !canUseAliasAssistant}
              onClick={() => void handleQuickAddFromClipboard()}
              className="rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:cursor-not-allowed disabled:opacity-60"
            >
              Quick add from clipboard
            </button>
            <select
              value={googleServiceAccountStatus.auth_mode}
              disabled={assistantBusy || setupBusy}
              onChange={(event) =>
                onGoogleAuthModeChange(event.target.value as "oauth" | "service_account")
              }
              className="rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] disabled:cursor-not-allowed disabled:opacity-60"
            >
              <option value="oauth">OAuth mode</option>
              <option value="service_account">Service account mode</option>
            </select>
            {oauthManualUrl && !inServiceAccountMode ? (
              <a
                href={oauthManualUrl}
                target="_blank"
                rel="noreferrer"
                className="rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7]"
              >
                Open Google login
              </a>
            ) : null}
          </div>
          {!canUseAliasAssistant ? (
            <p className="mt-2 text-[12px] text-[#6e6e73]">{aliasPrereqHint}</p>
          ) : null}
          {oauthBlocked ? (
            <p className="mt-1 text-[12px] text-[#6e6e73]">{oauthSetupHint}</p>
          ) : null}
        </SettingsRow>
        <SettingsRow
          title="Smart setup assistant"
          description={
            setupStatus ||
            oauthStatus ||
            "Click Start setup to auto-select mode and walk through setup steps."
          }
          right={<StatusChip label={setupStateChip.label} tone={setupStateChip.tone} />}
          noDivider
        >
          {setupStepsState.length === 0 ? (
            <p className="text-[12px] text-[#6e6e73]">
              No run yet. This assistant can switch auth mode, guide Google login/share, and quick-add your first alias.
            </p>
          ) : (
            <div className="grid gap-2 sm:grid-cols-3">
              {setupStepsState.map((step) => {
                const chip = stepChip(step.state);
                return (
                  <div
                    key={step.id}
                    className="rounded-lg border border-[#ececf0] bg-[#fafafc] px-3 py-2 text-[12px] text-[#3a3a3c]"
                  >
                    <p className="font-semibold text-[#1d1d1f]">{step.label}</p>
                    <p>{chip.label}</p>
                  </div>
                );
              })}
            </div>
          )}
        </SettingsRow>
      </SettingsSection>

      <SettingsSection
        title="Advanced settings"
        subtitle="Detailed Google controls are hidden during onboarding to keep setup fast."
      >
        <SettingsRow
          title="Panel visibility"
          description={
            setupComplete
              ? "Setup complete. Advanced controls are unlocked."
              : "Complete quick setup first, or show advanced controls manually."
          }
          right={
            <button
              type="button"
              onClick={() => setShowAdvancedSettings((value) => !value)}
              className="rounded-lg border border-[#d2d2d7] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7]"
            >
              {showAdvancedPanels ? "Hide advanced" : "Show advanced"}
            </button>
          }
          noDivider
        />
      </SettingsSection>

      {showAdvancedPanels ? (
        <>
      <SettingsSection
        title="Google"
        subtitle="Connect Google services for Gmail, Calendar, Drive, and Analytics."
        actions={
          <>
            <StatusChip label={oauthChip.label} tone={oauthChip.tone} />
            <button
              type="button"
              disabled={oauthBlocked}
              onClick={() => void handleConnectGoogleAction()}
              className="rounded-xl bg-[#1d1d1f] px-4 py-2 text-[13px] font-semibold text-white hover:bg-[#2f2f34] disabled:cursor-not-allowed disabled:opacity-60"
            >
              Connect Google
            </button>
            <button
              type="button"
              onClick={onDisconnectGoogle}
              className="rounded-xl border border-[#d2d2d7] bg-white px-4 py-2 text-[13px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7]"
            >
              Disconnect
            </button>
          </>
        }
      >
        <SettingsRow
          title="Account"
          description={googleOAuthStatus.email || "No Google account connected yet."}
          right={<StatusChip label={oauthChip.label} tone={oauthChip.tone} />}
        />
        <SettingsRow
          title="Granted scopes"
          description={
            googleOAuthStatus.scopes.length > 0
              ? `${googleOAuthStatus.scopes.length} scope(s) granted`
              : "No scopes granted yet."
          }
          right={<StatusChip label={googleOAuthStatus.scopes.length > 0 ? "Ready" : "Not granted"} tone="neutral" />}
        />
        <SettingsRow
          title="Tool connectivity"
          description={`${connectedTools} of ${trackedGoogleToolHealth.length} selected Google tool(s) are connected.`}
          right={
            <button
              type="button"
              onClick={() => setShowToolDetails((value) => !value)}
              className="rounded-lg border border-[#d2d2d7] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7]"
            >
              {showToolDetails ? "Hide details" : "Show details"}
            </button>
          }
          noDivider={!showToolDetails}
        />
        {showToolDetails
          ? trackedGoogleToolHealth.map((item, index) => {
              const chip = healthTone(item);
              const fallbackMessage =
                googleOAuthStatus.connected || inServiceAccountMode
                  ? "Temporarily unavailable. Click Refresh to re-check this tool."
                  : "Connect Google first to enable this tool.";
              return (
                <SettingsRow
                  key={item.id}
                  title={item.label}
                  description={item.message || fallbackMessage}
                  right={<StatusChip label={chip.label} tone={chip.tone} />}
                  noDivider={index === trackedGoogleToolHealth.length - 1}
                />
              );
            })
          : null}
      </SettingsSection>

      <SettingsSection
        title="Service account access"
        subtitle="Share Docs, Sheets, and GA4 resources with this email so the agent can access them based on the role you grant."
      >
        <SettingsRow
          title="Service account email"
          description={
            googleServiceAccountStatus.email ||
            "No service-account email detected. Configure GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_JSON_PATH."
          }
          right={
            <>
              <StatusChip label={serviceChip.label} tone={serviceChip.tone} />
              <button
                type="button"
                onClick={() => void handleCopyServiceEmail()}
                className="rounded-xl border border-[#d2d2d7] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7]"
              >
                Copy email
              </button>
            </>
          }
        />
        <SettingsRow
          title="Auth mode"
          description="Choose how Google tools authenticate. Use service_account after users share resources with the email above."
          right={
            <select
              value={googleServiceAccountStatus.auth_mode}
              onChange={(event) =>
                onGoogleAuthModeChange(event.target.value as "oauth" | "service_account")
              }
              className="rounded-lg border border-[#d2d2d7] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#1d1d1f]"
            >
              <option value="oauth">OAuth</option>
              <option value="service_account">Service account</option>
            </select>
          }
        />
        <SettingsRow
          title="Status"
          description={googleServiceAccountStatus.message}
          right={
            <StatusChip
              label={googleServiceAccountStatus.usable ? "API ready" : "Needs key"}
              tone={googleServiceAccountStatus.usable ? "success" : "neutral"}
            />
          }
          noDivider={googleServiceAccountStatus.instructions.length === 0}
        />
        {googleServiceAccountStatus.instructions.map((instruction, index) => (
          <SettingsRow
            key={`sa-instruction-${index}`}
            title={`Step ${index + 1}`}
            description={instruction}
            right={<StatusChip label="Guide" tone="neutral" />}
            noDivider={index === googleServiceAccountStatus.instructions.length - 1}
          />
        ))}
      </SettingsSection>

      <SettingsSection
        title="Link Sharing Assistant"
        subtitle="Paste a Google link, verify required role, and save an alias for future prompts."
      >
        <SettingsRow
          title="Resource link"
          description="Supports Google Docs, Sheets, Drive files, GA4 links, and saved aliases."
          right={<StatusChip label={assistantBusy ? "Running" : "Ready"} tone="neutral" />}
        >
          <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto]">
            <input
              value={linkInput}
              onChange={(event) => setLinkInput(event.target.value)}
              placeholder="Paste Google link or alias"
              className="w-full rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] text-[#1d1d1f]"
            />
            <button
              type="button"
              disabled={assistantBusy}
              onClick={() => void handleQuickAddFromClipboard()}
              className="rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:cursor-not-allowed disabled:opacity-60"
            >
              Paste & quick add
            </button>
            <button
              type="button"
              disabled={assistantBusy}
              onClick={() => void handleAnalyzeLink()}
              className="rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:cursor-not-allowed disabled:opacity-60"
            >
              Analyze
            </button>
          </div>
        </SettingsRow>
        <SettingsRow
          title="Required action"
          description="Select read or edit, then run a live access check."
          right={
            <div className="flex items-center gap-2">
              <select
                value={linkAction}
                onChange={(event) => setLinkAction(event.target.value as "read" | "edit")}
                className="rounded-lg border border-[#d2d2d7] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#1d1d1f]"
              >
                <option value="read">Read</option>
                <option value="edit">Edit</option>
              </select>
              <button
                type="button"
                disabled={assistantBusy}
                onClick={() => void handleCheckLinkAccess()}
                className="rounded-lg border border-[#d2d2d7] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:cursor-not-allowed disabled:opacity-60"
              >
                Check access
              </button>
            </div>
          }
        />
        <SettingsRow
          title="Alias"
          description="Save this resource with a human-friendly name for future prompts."
          right={
            <button
              type="button"
              disabled={assistantBusy}
              onClick={() => void handleSaveAlias()}
              className="rounded-lg border border-[#d2d2d7] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:cursor-not-allowed disabled:opacity-60"
            >
              Save alias
            </button>
          }
        >
          <input
            value={aliasInput}
            onChange={(event) => setAliasInput(event.target.value)}
            placeholder="e.g. quarterly traffic sheet"
            className="w-full rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] text-[#1d1d1f]"
          />
        </SettingsRow>
        <SettingsRow
          title="Detected target"
          description={
            analysisResult?.detected
              ? `${analysisResult.resource_type || "resource"} - ${analysisResult.resource_id || ""}`
              : analysisResult?.message || "No link analyzed yet."
          }
          right={
            <StatusChip
              label={analysisResult?.detected ? "Detected" : "Pending"}
              tone={analysisResult?.detected ? "success" : "neutral"}
            />
          }
        />
        <SettingsRow
          title="Access result"
          description={accessResult?.message || "No access check has been run."}
          right={
            <StatusChip
              label={accessResult ? (accessResult.ready ? "Ready" : "Missing role") : "Pending"}
              tone={accessResult ? (accessResult.ready ? "success" : "warning") : "neutral"}
            />
          }
          noDivider={googleWorkspaceAliases.length === 0}
        />
        {googleWorkspaceAliases.map((row, index) => (
          <SettingsRow
            key={`${row.alias}-${row.resource_id}-${index}`}
            title={row.alias}
            description={`${row.resource_type} - ${row.resource_id}`}
            right={<StatusChip label="Alias" tone="neutral" />}
            noDivider={index === googleWorkspaceAliases.length - 1}
          />
        ))}
      </SettingsSection>
        </>
      ) : null}

      {setupComplete ? (
        <SettingsSection
          title="Recent events"
          subtitle="Live OAuth and tool activity from the backend event stream."
        >
          {liveEvents.length === 0 ? (
            <SettingsRow
              title="No events yet"
              description="Run a connection check or model action to populate this timeline."
              right={<StatusChip label="Idle" tone="neutral" />}
              noDivider
            />
          ) : (
            liveEvents.slice(0, 16).map((event, index) => (
              <SettingsRow
                key={`${event.type}-${event.timestamp || index}`}
                title={event.type}
                description={event.message}
                right={<StatusChip label="Live" tone="neutral" />}
                noDivider={index === Math.min(liveEvents.length, 16) - 1}
              />
            ))
          )}
        </SettingsSection>
      ) : (
        <SettingsSection
          title="Recent events"
          subtitle="Hidden during onboarding to keep setup focused."
        >
          <SettingsRow
            title="Unlock after setup"
            description="Complete the 3-step quick setup to view live event history."
            right={<StatusChip label="Locked" tone="neutral" />}
            noDivider
          />
        </SettingsSection>
      )}

      {oauthStatus ? (
        <div className="rounded-xl border border-[#ececf0] bg-white px-4 py-3">
          <p className="text-[12px] text-[#6e6e73]">{oauthStatus}</p>
        </div>
      ) : null}
      {copyStatus ? (
        <div className="rounded-xl border border-[#ececf0] bg-white px-4 py-3">
          <p className="text-[12px] text-[#6e6e73]">{copyStatus}</p>
        </div>
      ) : null}
      {assistantStatus ? (
        <div className="rounded-xl border border-[#ececf0] bg-white px-4 py-3">
          <p className="text-[12px] text-[#6e6e73]">{assistantStatus}</p>
        </div>
      ) : null}
    </>
  );
}
