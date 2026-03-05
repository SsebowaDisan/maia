import { useState } from "react";

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
  googleToolHealth: GoogleToolHealthItem[];
  liveEvents: AgentLiveEvent[];
  onConnectGoogle: () => Promise<{ ok: boolean; authorize_url?: string; message: string }>;
  onDisconnectGoogle: () => void;
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
  googleToolHealth,
  liveEvents,
  onConnectGoogle,
  onDisconnectGoogle,
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
  const [analysisResult, setAnalysisResult] = useState<GoogleWorkspaceLinkAnalyzeResult | null>(null);
  const [accessResult, setAccessResult] = useState<GoogleWorkspaceLinkAccessResult | null>(null);
  const serviceChip = toneFromBoolean(googleServiceAccountStatus.usable, {
    trueLabel: "Ready",
    falseLabel: googleServiceAccountStatus.configured ? "Share-only" : "Not configured",
  });
  const connectedTools = googleToolHealth.filter((item) => item.ok).length;
  const inServiceAccountMode = googleServiceAccountStatus.auth_mode === "service_account";
  const quickSteps = [
    {
      id: "connect",
      label: inServiceAccountMode ? "Configure service account" : "Connect Google account",
      done: inServiceAccountMode ? googleServiceAccountStatus.usable : googleOAuthStatus.connected,
    },
    {
      id: "permissions",
      label: inServiceAccountMode ? "Share resources with service email" : "Grant required scopes",
      done: inServiceAccountMode ? Boolean(googleServiceAccountStatus.email) : googleOAuthStatus.scopes.length > 0,
    },
    {
      id: "alias",
      label: "Save first link alias",
      done: googleWorkspaceAliases.length > 0,
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
    try {
      const result = await onConnectGoogle();
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
        if (!googleOAuthStatus.connected) {
          setSetupStep("connect", "needs_user");
          setSetupStatus("Step 2 needs you: complete Google login, then click Start setup again.");
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

  return (
    <>
      <SettingsSection
        title="Google Quick Start"
        subtitle="Fastest path: connect, verify access, and save one alias. Most users finish this in under 1 minute."
      >
        <SettingsRow
          title="Setup progress"
          description={`Mode: ${inServiceAccountMode ? "Service account" : "OAuth"} • ${connectedTools}/${googleToolHealth.length} tools connected`}
          right={<StatusChip label={quickChip.label} tone={quickChip.tone} />}
        >
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
          description="Use one of these actions to finish setup quickly."
          right={<StatusChip label={assistantBusy || setupBusy ? "Running" : "Idle"} tone="neutral" />}
        >
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={assistantBusy || setupBusy}
              onClick={() => void handleStartSetup()}
              className="rounded-lg bg-[#1d1d1f] px-3 py-2 text-[12px] font-semibold text-white hover:bg-[#2f2f34] disabled:cursor-not-allowed disabled:opacity-60"
            >
              Start setup
            </button>
            {!inServiceAccountMode ? (
              <button
                type="button"
                disabled={assistantBusy || setupBusy}
                onClick={() => void handleConnectGoogleAction()}
                className="rounded-lg bg-[#2f2f34] px-3 py-2 text-[12px] font-semibold text-white hover:bg-[#434349] disabled:cursor-not-allowed disabled:opacity-60"
              >
                Connect Google
              </button>
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
              disabled={assistantBusy || setupBusy}
              onClick={() => void handleQuickAddFromClipboard()}
              className="rounded-lg border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7] disabled:cursor-not-allowed disabled:opacity-60"
            >
              Paste & quick add
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
              onClick={() => void handleConnectGoogleAction()}
              className="rounded-xl bg-[#1d1d1f] px-4 py-2 text-[13px] font-semibold text-white hover:bg-[#2f2f34]"
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
          description={`${connectedTools} of ${googleToolHealth.length} Google tool(s) are connected.`}
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
          ? googleToolHealth.map((item, index) => {
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
                  noDivider={index === googleToolHealth.length - 1}
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
              ? `${analysisResult.resource_type || "resource"} • ${analysisResult.resource_id || ""}`
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
            description={`${row.resource_type} • ${row.resource_id}`}
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
