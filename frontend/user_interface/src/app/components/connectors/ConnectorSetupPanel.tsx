import { Loader2 } from "lucide-react";

import type { ConnectorSummary } from "../../types/connectorSummary";
import type { ConnectorDefinition } from "../settings/connectorDefinitions";

type ConnectorSetupPanelProps = {
  connector: ConnectorSummary;
  connectorDefinition: ConnectorDefinition | null;
  saving: boolean;
  fieldValues: Record<string, string>;
  onFieldChange: (key: string, value: string) => void;
  onOAuthConnect: () => void;
  onSaveCredentials: () => void;
};

const GENERIC_CREDENTIAL_FIELD_KEY = "__generic_credential";

function setupLabel(connector: ConnectorSummary): string {
  if (connector.setupMode === "service_identity") {
    return "Service identity setup";
  }
  if (connector.setupMode === "oauth_popup" || connector.authType === "oauth2") {
    return "OAuth setup";
  }
  return "Credential setup";
}

export function ConnectorSetupPanel({
  connector,
  connectorDefinition,
  saving,
  fieldValues,
  onFieldChange,
  onOAuthConnect,
  onSaveCredentials,
}: ConnectorSetupPanelProps) {
  return (
    <section className="space-y-3 rounded-2xl border border-black/[0.08] bg-white p-4">
      <div>
        <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">
          {setupLabel(connector)}
        </p>
        <p className="mt-1 text-[13px] text-[#667085]">
          {connector.setupMode === "service_identity"
            ? "Use a managed enterprise identity for this connector and keep long-lived credentials out of agents."
            : connector.authType === "oauth2"
              ? "Launch the provider login in a popup and refresh the connector state after approval."
              : connector.authType === "none"
                ? "This connector does not require stored credentials."
                : "Store the connector credentials for this workspace so agents can use the integration."}
        </p>
      </div>

      {connector.authType === "oauth2" ? (
        <button
          type="button"
          onClick={onOAuthConnect}
          disabled={saving}
          className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#7c3aed] px-4 py-2.5 text-[13px] font-semibold text-white hover:bg-[#6d28d9] disabled:cursor-not-allowed disabled:opacity-60"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : null}
          Connect with OAuth
        </button>
      ) : null}

      {connector.authType === "none" ? (
        <div className="rounded-2xl border border-[#c4b5fd] bg-[#f5f3ff] px-4 py-3 text-[13px] text-[#7c3aed]">
          No credentials required. This connector uses a public API or shared configuration.
        </div>
      ) : null}

      {connector.authType !== "oauth2" &&
      connector.authType !== "none" &&
      connectorDefinition ? (
        <>
          {connectorDefinition.fields.map((field) => (
            <label key={field.key} className="block">
              <span className="mb-1 block text-[12px] font-semibold text-[#344054]">
                {field.label}
              </span>
              <input
                type={field.sensitive ? "password" : "text"}
                value={fieldValues[field.key] || ""}
                onChange={(event) => onFieldChange(field.key, event.target.value)}
                placeholder={field.placeholder}
                className="w-full rounded-xl border border-black/[0.12] bg-white px-3 py-2 text-[13px] text-[#111827] focus:border-black/[0.28] focus:outline-none"
              />
            </label>
          ))}
          <button
            type="button"
            onClick={onSaveCredentials}
            disabled={saving}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#7c3aed] px-4 py-2.5 text-[13px] font-semibold text-white hover:bg-[#6d28d9] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : null}
            {connector.setupMode === "service_identity"
              ? "Save service identity"
              : "Save credential"}
          </button>
        </>
      ) : null}

      {connector.authType !== "oauth2" &&
      connector.authType !== "none" &&
      !connectorDefinition ? (
        <>
          <label className="block">
            <span className="mb-1 block text-[12px] font-semibold text-[#344054]">
              {connector.authType === "bearer" ? "Access token" : "API key"}
            </span>
            <input
              type="password"
              value={fieldValues[GENERIC_CREDENTIAL_FIELD_KEY] || ""}
              onChange={(event) =>
                onFieldChange(GENERIC_CREDENTIAL_FIELD_KEY, event.target.value)
              }
              placeholder={
                connector.authType === "bearer"
                  ? "Paste bearer token"
                  : "Paste API key"
              }
              className="w-full rounded-xl border border-black/[0.12] bg-white px-3 py-2 text-[13px] text-[#111827] focus:border-black/[0.28] focus:outline-none"
            />
          </label>
          <button
            type="button"
            onClick={onSaveCredentials}
            disabled={saving}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#7c3aed] px-4 py-2.5 text-[13px] font-semibold text-white hover:bg-[#6d28d9] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : null}
            Save credential
          </button>
        </>
      ) : null}
    </section>
  );
}
