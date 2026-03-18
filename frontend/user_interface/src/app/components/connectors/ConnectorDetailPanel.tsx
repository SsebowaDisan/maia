import { useMemo, useState, type ReactNode } from "react";

import {
  deleteConnectorCredentials,
  startConnectorOAuth,
  startGoogleOAuth,
  testConnectorConnection,
  upsertConnectorCredentials,
} from "../../../api/client";
import type { ConnectorSummary } from "../../types/connectorSummary";
import { openOAuthPopup } from "../../utils/oauthPopup";
import {
  MANUAL_CONNECTOR_DEFINITIONS,
  type ConnectorDefinition,
} from "../settings/connectorDefinitions";
import { ConnectorAgentAccessList } from "./ConnectorAgentAccessList";
import { ConnectorDetailActions } from "./ConnectorDetailActions";
import { ConnectorDetailHeader } from "./ConnectorDetailHeader";
import { ConnectorDetailShell } from "./ConnectorDetailShell";
import { ConnectorSetupPanel } from "./ConnectorSetupPanel";
import { GoogleSuitePanel } from "./GoogleSuitePanel";
import { MicrosoftSuitePanel } from "./MicrosoftSuitePanel";
import { WebhookManager } from "./WebhookManager";

type ConnectorDetailPanelProps = {
  connector: ConnectorSummary | null;
  open: boolean;
  onClose: () => void;
  onRefresh: () => Promise<void> | void;
  advancedSettings?: ReactNode;
  permissionAgents?: Array<{
    id: string;
    name: string;
  }>;
  permissionValue?: Record<string, string[]>;
  permissionSaving?: boolean;
  permissionError?: string;
  onPermissionChange?: (next: Record<string, string[]>) => Promise<void> | void;
};

const GENERIC_CREDENTIAL_FIELD_KEY = "__generic_credential";

function formatLabel(value?: string) {
  if (!value) {
    return null;
  }
  return value
    .split(/[_-]+/g)
    .filter(Boolean)
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");
}

export function ConnectorDetailPanel({
  connector,
  open,
  onClose,
  onRefresh,
  advancedSettings,
  permissionAgents = [],
  permissionValue = {},
  permissionSaving = false,
  permissionError = "",
  onPermissionChange,
}: ConnectorDetailPanelProps) {
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");
  const [lastTestedAt, setLastTestedAt] = useState<string | null>(null);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});

  const connectorDefinition = useMemo<ConnectorDefinition | null>(
    () =>
      MANUAL_CONNECTOR_DEFINITIONS.find(
        (definition) => definition.id === connector?.id,
      ) || null,
    [connector?.id],
  );

  const allowedAgentIds = connector ? permissionValue[connector.id] || [] : [];

  const updateField = (key: string, value: string) => {
    setFieldValues((previous) => ({ ...previous, [key]: value }));
  };

  const handleOAuthConnect = async () => {
    if (!connector) {
      return;
    }
    setSaving(true);
    setStatus("");
    try {
      const setupMode = (connector as Record<string, unknown>).setup_mode || (connector as Record<string, unknown>).auth_kind || "";
      if (setupMode === "oauth_popup" || connector.id === "google_workspace") {
        const oauthStart = await startGoogleOAuth();
        const result = await openOAuthPopup(oauthStart.authorize_url);
        if (!result.success) {
          setStatus(result.error);
          return;
        }
        setStatus("OAuth completed. Refreshing connector status...");
        await onRefresh();
        return;
      }
      const redirectUri =
        typeof window !== "undefined"
          ? `${window.location.origin}/api/connectors/oauth/callback`
          : "/api/connectors/oauth/callback";
      const oauthStart = await startConnectorOAuth({
        connectorId: connector.id,
        redirectUri,
      });
      const result = await openOAuthPopup(oauthStart.auth_url);
      if (!result.success) {
        setStatus(result.error);
        return;
      }
      setStatus("OAuth completed. Refreshing connector status...");
      await onRefresh();
    } catch (error) {
      setStatus(`Failed to start OAuth: ${String(error)}`);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveCredentials = async () => {
    if (!connector) {
      return;
    }
    const payload: Record<string, string> = {};
    if (connectorDefinition) {
      for (const field of connectorDefinition.fields) {
        const value = String(fieldValues[field.key] || "").trim();
        if (value) {
          payload[field.key] = value;
        }
      }
    } else {
      const value = String(fieldValues[GENERIC_CREDENTIAL_FIELD_KEY] || "").trim();
      if (value) {
        const key = connector.authType === "bearer" ? "ACCESS_TOKEN" : "API_KEY";
        payload[key] = value;
      }
    }
    if (!Object.keys(payload).length) {
      setStatus("Enter at least one value before saving.");
      return;
    }
    setSaving(true);
    setStatus("");
    try {
      await upsertConnectorCredentials(connector.id, payload);
      setStatus("Credential saved successfully.");
      await onRefresh();
    } catch (error) {
      setStatus(`Failed to save credential: ${String(error)}`);
    } finally {
      setSaving(false);
    }
  };

  const handleTestConnection = async () => {
    if (!connector) {
      return;
    }
    setSaving(true);
    setStatus("");
    try {
      const row = await testConnectorConnection(connector.id);
      const ok = String(row?.status || "").toLowerCase() === "ok";
      const message = String(row?.detail || "");
      setStatus(ok ? "Test passed." : `Test failed: ${message || "Unknown connector error."}`);
      setLastTestedAt(new Date().toISOString());
    } catch (error) {
      setStatus(`Connection test failed: ${String(error)}`);
    } finally {
      setSaving(false);
    }
  };

  const handleRevoke = async () => {
    if (!connector) {
      return;
    }
    if (connector.authType === "none") {
      setStatus("No credentials to revoke for this public connector.");
      return;
    }
    setSaving(true);
    setStatus("");
    try {
      await deleteConnectorCredentials(connector.id);
      setStatus("Credential revoked.");
      await onRefresh();
    } catch (error) {
      setStatus(`Failed to revoke credential: ${String(error)}`);
    } finally {
      setSaving(false);
    }
  };

  const handlePermissionChange = async (nextAllowedAgentIds: string[]) => {
    if (!connector || !onPermissionChange) {
      return;
    }
    await onPermissionChange({
      ...permissionValue,
      [connector.id]: nextAllowedAgentIds,
    });
  };

  if (!open || !connector) {
    return null;
  }

  const setupPanel = (
    <ConnectorSetupPanel
      connector={connector}
      connectorDefinition={connectorDefinition}
      saving={saving}
      fieldValues={fieldValues}
      onFieldChange={updateField}
      onOAuthConnect={() => {
        void handleOAuthConnect();
      }}
      onSaveCredentials={() => {
        void handleSaveCredentials();
      }}
    />
  );

  // Use suite_id from backend metadata to decide which panel to render
  const suiteId = String((connector as Record<string, unknown>).suite_id || "").trim().toLowerCase();
  const panelContent =
    suiteId === "google" ? (
      <GoogleSuitePanel connector={connector} advancedSettings={advancedSettings} />
    ) : suiteId === "microsoft" ? (
      <MicrosoftSuitePanel connector={connector} setupPanel={setupPanel} />
    ) : (
      setupPanel
    );

  return (
    <ConnectorDetailShell
      header={<ConnectorDetailHeader connector={connector} onClose={onClose} />}
    >
      <section className="grid grid-cols-3 gap-3">
        <div className="rounded-2xl border border-black/[0.08] bg-[#f8fafc] px-3.5 py-3">
          <p className="text-[11px] uppercase tracking-[0.08em] text-[#98a2b3]">Auth type</p>
          <p className="mt-1 text-[14px] font-semibold text-[#111827]">
            {formatLabel(connector.authType) || connector.authType}
          </p>
        </div>
        <div className="rounded-2xl border border-black/[0.08] bg-[#f8fafc] px-3.5 py-3">
          <p className="text-[11px] uppercase tracking-[0.08em] text-[#98a2b3]">Setup mode</p>
          <p className="mt-1 text-[14px] font-semibold text-[#111827]">
            {formatLabel(connector.setupMode) || "Default"}
          </p>
        </div>
        <div className="rounded-2xl border border-black/[0.08] bg-[#f8fafc] px-3.5 py-3">
          <p className="text-[11px] uppercase tracking-[0.08em] text-[#98a2b3]">Tools</p>
          <p className="mt-1 text-[14px] font-semibold text-[#111827]">
            {connector.tools.length}
          </p>
        </div>
      </section>

      {connector.statusMessage ? (
        <div className="rounded-xl border border-black/[0.08] bg-[#f8fafc] px-3 py-2 text-[13px] text-[#344054]">
          {connector.statusMessage}
        </div>
      ) : null}

      {panelContent}

      {connector.tools.length ? (
        <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
          <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">
            Enabled tools
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {connector.tools.map((toolId) => (
              <span
                key={toolId}
                className="rounded-full border border-black/[0.08] bg-[#f8fafc] px-2.5 py-1 text-[11px] font-medium text-[#475467]"
              >
                {toolId}
              </span>
            ))}
          </div>
        </section>
      ) : null}

      {permissionAgents.length ? (
        <>
          <ConnectorAgentAccessList
            connectorId={connector.id}
            agents={permissionAgents}
            allowedAgentIds={allowedAgentIds}
            disabled={permissionSaving}
            onChange={(nextAllowedAgentIds) => {
              void handlePermissionChange(nextAllowedAgentIds);
            }}
          />
          {permissionError ? (
            <div className="rounded-xl border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-[12px] text-[#9f1239]">
              {permissionError}
            </div>
          ) : null}
        </>
      ) : null}

      <ConnectorDetailActions
        canRevoke={connector.authType !== "none"}
        disabled={saving}
        onTest={() => {
          void handleTestConnection();
        }}
        onRevoke={() => {
          void handleRevoke();
        }}
      />

      {lastTestedAt ? (
        <p className="text-[12px] text-[#667085]">
          Last tested: {new Date(lastTestedAt).toLocaleString()}
        </p>
      ) : null}

      {status ? (
        <div className="rounded-xl border border-black/[0.08] bg-[#f8fafc] px-3 py-2 text-[13px] text-[#344054]">
          {status}
        </div>
      ) : null}

      <WebhookManager connectorId={connector.id} />
    </ConnectorDetailShell>
  );
}
