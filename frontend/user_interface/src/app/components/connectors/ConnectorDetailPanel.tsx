import { useMemo, useState, type ReactNode } from "react";
import { Loader2, RefreshCw, X } from "lucide-react";

import {
  deleteConnectorCredentials,
  listConnectorHealth,
  startGoogleOAuth,
  upsertConnectorCredentials,
} from "../../../api/client";
import type { ConnectorSummary } from "../../types/connectorSummary";
import { MANUAL_CONNECTOR_DEFINITIONS } from "../settings/connectorDefinitions";
import { openOAuthPopup } from "../../utils/oauthPopup";
import { WebhookManager } from "./WebhookManager";

type ConnectorDetailPanelProps = {
  connector: ConnectorSummary | null;
  open: boolean;
  onClose: () => void;
  onRefresh: () => Promise<void> | void;
  advancedSettings?: ReactNode;
};

function subServiceDotClass(status: "Connected" | "Needs permission" | "Disabled"): string {
  if (status === "Connected") {
    return "bg-[#16a34a]";
  }
  if (status === "Needs permission") {
    return "bg-[#d97706]";
  }
  return "bg-[#98a2b3]";
}

export function ConnectorDetailPanel({
  connector,
  open,
  onClose,
  onRefresh,
  advancedSettings,
}: ConnectorDetailPanelProps) {
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");
  const [lastTestedAt, setLastTestedAt] = useState<string | null>(null);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});

  const connectorDefinition = useMemo(
    () =>
      MANUAL_CONNECTOR_DEFINITIONS.find(
        (definition) => definition.id === connector?.id,
      ) || null,
    [connector?.id],
  );

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
      if (connector.id === "google_workspace") {
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
      setStatus("OAuth flow is not configured for this connector yet.");
    } catch (error) {
      setStatus(`Failed to start OAuth: ${String(error)}`);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveApiKeys = async () => {
    if (!connector || !connectorDefinition) {
      return;
    }
    const payload: Record<string, string> = {};
    for (const field of connectorDefinition.fields) {
      const value = String(fieldValues[field.key] || "").trim();
      if (value) {
        payload[field.key] = value;
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
      const rows = await listConnectorHealth();
      const row = rows.find((entry) => String(entry?.connector_id || "") === connector.id);
      const ok = Boolean(row?.ok);
      const message = String(row?.message || "");
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

  if (!open || !connector) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-[120] bg-black/30 backdrop-blur-[2px]">
      <div className="absolute inset-y-0 right-0 w-full max-w-[480px] border-l border-black/[0.08] bg-white shadow-[-30px_0_64px_rgba(15,23,42,0.24)]">
        <div className="flex items-start justify-between border-b border-black/[0.08] px-5 py-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#667085]">Connector detail</p>
            <h2 className="mt-1 text-[24px] font-semibold tracking-[-0.02em] text-[#101828]">{connector.name}</h2>
            <p className="mt-1 text-[13px] text-[#667085]">{connector.description}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-black/[0.1] text-[#475467] hover:text-[#111827]"
            aria-label="Close connector details"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-4 overflow-y-auto px-5 py-4">
          <div className="rounded-2xl border border-black/[0.08] bg-[#f8fafc] px-4 py-3 text-[13px] text-[#475467]">
            Auth type: <span className="font-semibold text-[#111827]">{connector.authType}</span>
          </div>

          {connector.subServices && connector.subServices.length > 0 ? (
            <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#667085]">
                Google services
              </p>
              <div className="mt-2 space-y-2">
                {connector.subServices.map((service) => (
                  <div
                    key={service.id}
                    className="flex items-start justify-between gap-3 rounded-xl border border-black/[0.06] bg-[#f8fafc] px-3 py-2"
                  >
                    <div>
                      <p className="text-[13px] font-semibold text-[#101828]">{service.label}</p>
                      <p className="text-[12px] text-[#667085]">{service.description}</p>
                    </div>
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-black/[0.08] bg-white px-2 py-1 text-[11px] font-semibold text-[#475467]">
                      <span className={`h-1.5 w-1.5 rounded-full ${subServiceDotClass(service.status)}`} />
                      {service.status}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          {connector.authType === "oauth2" ? (
            <button
              type="button"
              onClick={() => void handleOAuthConnect()}
              disabled={saving}
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#111827] px-4 py-2.5 text-[13px] font-semibold text-white hover:bg-[#1f2937] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {saving ? <Loader2 size={14} className="animate-spin" /> : null}
              Connect with OAuth
            </button>
          ) : null}

          {connector.authType !== "oauth2" && connectorDefinition ? (
            <div className="space-y-3 rounded-2xl border border-black/[0.08] bg-white p-4">
              <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">Credential form</p>
              {connectorDefinition.fields.map((field) => (
                <label key={field.key} className="block">
                  <span className="mb-1 block text-[12px] font-semibold text-[#344054]">{field.label}</span>
                  <input
                    type={field.sensitive ? "password" : "text"}
                    value={fieldValues[field.key] || ""}
                    onChange={(event) => updateField(field.key, event.target.value)}
                    placeholder={field.placeholder}
                    className="w-full rounded-xl border border-black/[0.12] bg-white px-3 py-2 text-[13px] text-[#111827] focus:border-black/[0.28] focus:outline-none"
                  />
                </label>
              ))}
              <button
                type="button"
                onClick={() => void handleSaveApiKeys()}
                disabled={saving}
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#111827] px-4 py-2.5 text-[13px] font-semibold text-white hover:bg-[#1f2937] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {saving ? <Loader2 size={14} className="animate-spin" /> : null}
                Save credential
              </button>
            </div>
          ) : null}

          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => void handleTestConnection()}
              disabled={saving}
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-black/[0.12] bg-white px-3 py-2 text-[13px] font-semibold text-[#111827] hover:border-black/[0.24] disabled:cursor-not-allowed disabled:opacity-60"
            >
              <RefreshCw size={13} />
              Test connection
            </button>
            <button
              type="button"
              onClick={() => void handleRevoke()}
              disabled={saving}
              className="inline-flex items-center justify-center rounded-xl border border-[#fda4af] bg-[#fff1f2] px-3 py-2 text-[13px] font-semibold text-[#9f1239] hover:bg-[#ffe4e6] disabled:cursor-not-allowed disabled:opacity-60"
            >
              Revoke
            </button>
          </div>

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

          {advancedSettings ? (
            <section className="rounded-2xl border border-black/[0.08] bg-white p-3">
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#667085]">
                Advanced settings
              </p>
              {advancedSettings}
            </section>
          ) : null}

          <WebhookManager connectorId={connector.id} />
        </div>
      </div>
    </div>
  );
}
