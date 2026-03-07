import { useEffect, useMemo, useState } from "react";

import { listConnectorPlugins, type ConnectorPluginManifest } from "../../../../api/client";
import { ManualConnectorCard } from "../ManualConnectorCard";
import type { ConnectorDefinition } from "../connectorDefinitions";
import { summarizeConnectorCapabilities } from "../pluginCapabilities";
import { SettingsRow } from "../ui/SettingsRow";
import { SettingsSection } from "../ui/SettingsSection";
import { StatusChip, toneFromBoolean } from "../ui/StatusChip";

type ApiSettingsProps = {
  mapsStatus: { configured: boolean; source?: "env" | "stored" | null };
  braveStatus: { configured: boolean; source?: "env" | "stored" | null };
  mapsKeyInput: string;
  braveKeyInput: string;
  setMapsKeyInput: (value: string) => void;
  setBraveKeyInput: (value: string) => void;
  onSaveMapsKey: () => void;
  onClearMapsKey: () => void;
  onSaveBraveKey: () => void;
  onClearBraveKey: () => void;
  connectors: ConnectorDefinition[];
  healthMap: Record<string, { ok: boolean; message: string }>;
  credentialMap: Record<string, { connector_id: string; values: Record<string, string>; date_updated: string }>;
  draftValues: Record<string, Record<string, string>>;
  savingConnectorId: string | null;
  statusMessage: string;
  onDraftChange: (connectorId: string, fieldKey: string, value: string) => void;
  onSaveConnector: (connector: ConnectorDefinition) => void;
  onClearConnector: (connector: ConnectorDefinition) => void;
};

export function ApiSettings({
  mapsStatus,
  braveStatus,
  mapsKeyInput,
  braveKeyInput,
  setMapsKeyInput,
  setBraveKeyInput,
  onSaveMapsKey,
  onClearMapsKey,
  onSaveBraveKey,
  onClearBraveKey,
  connectors,
  healthMap,
  credentialMap,
  draftValues,
  savingConnectorId,
  statusMessage,
  onDraftChange,
  onSaveConnector,
  onClearConnector,
}: ApiSettingsProps) {
  const mapsChip = toneFromBoolean(mapsStatus.configured, { trueLabel: "Configured", falseLabel: "Not configured" });
  const braveChip = toneFromBoolean(braveStatus.configured, { trueLabel: "Configured", falseLabel: "Not configured" });
  const [pluginManifests, setPluginManifests] = useState<ConnectorPluginManifest[]>([]);
  const [pluginStatus, setPluginStatus] = useState("");

  useEffect(() => {
    let mounted = true;
    void listConnectorPlugins()
      .then((rows) => {
        if (!mounted) {
          return;
        }
        setPluginManifests(Array.isArray(rows) ? rows : []);
        setPluginStatus("");
      })
      .catch(() => {
        if (!mounted) {
          return;
        }
        setPluginManifests([]);
        setPluginStatus("Plugin capabilities are temporarily unavailable.");
      });
    return () => {
      mounted = false;
    };
  }, []);

  const capabilityMap = useMemo(() => summarizeConnectorCapabilities(pluginManifests), [pluginManifests]);

  return (
    <>
      <SettingsSection title="External APIs" subtitle="Manage provider keys used by live company workflows.">
        <SettingsRow
          title="Google Maps API key"
          description="Used for Places, Geocode, and Distance Matrix."
          right={<StatusChip label={mapsChip.label} tone={mapsChip.tone} />}
        >
          {mapsStatus.source === "env" ? (
            <p className="text-[12px] text-[#6e6e73]">Configured via server environment variable.</p>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="password"
                value={mapsKeyInput}
                onChange={(event) => setMapsKeyInput(event.target.value)}
                aria-label="Google Maps API key"
                className="min-w-[280px] flex-1 rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[13px] text-[#1d1d1f] placeholder:text-[#a1a1a6] focus:outline-none focus:border-[#8e8e93]"
                placeholder="Paste Google Maps API key"
                autoComplete="off"
              />
              <button
                type="button"
                onClick={onSaveMapsKey}
                className="rounded-xl bg-[#1d1d1f] px-3 py-2 text-[12px] font-semibold text-white hover:bg-[#2f2f34]"
              >
                Save
              </button>
              <button
                type="button"
                onClick={onClearMapsKey}
                className="rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7]"
              >
                Clear
              </button>
            </div>
          )}
        </SettingsRow>

        <SettingsRow
          title="Brave Search API key"
          description="Primary provider for web search and live research."
          right={<StatusChip label={braveChip.label} tone={braveChip.tone} />}
          noDivider
        >
          {braveStatus.source === "env" ? (
            <p className="text-[12px] text-[#6e6e73]">Configured via server environment variable.</p>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="password"
                value={braveKeyInput}
                onChange={(event) => setBraveKeyInput(event.target.value)}
                aria-label="Brave Search API key"
                className="min-w-[280px] flex-1 rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[13px] text-[#1d1d1f] placeholder:text-[#a1a1a6] focus:outline-none focus:border-[#8e8e93]"
                placeholder="Paste Brave Search API key"
                autoComplete="off"
              />
              <button
                type="button"
                onClick={onSaveBraveKey}
                className="rounded-xl bg-[#1d1d1f] px-3 py-2 text-[12px] font-semibold text-white hover:bg-[#2f2f34]"
              >
                Save
              </button>
              <button
                type="button"
                onClick={onClearBraveKey}
                className="rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[12px] font-semibold text-[#1d1d1f] hover:bg-[#f5f5f7]"
              >
                Clear
              </button>
            </div>
          )}
        </SettingsRow>
      </SettingsSection>

      <SettingsSection
        title="Provider credentials"
        subtitle="Optional connectors used by advanced workflows."
      >
        <SettingsRow
          title="Manual connectors"
          description={`Configure ${connectors.length} connectors from the list below.`}
          right={
            <StatusChip
              label={`${Object.keys(capabilityMap).length || connectors.length} total`}
              tone="neutral"
            />
          }
          noDivider
        />
        {pluginStatus ? (
          <p className="mt-2 text-[12px] text-[#6e6e73]">{pluginStatus}</p>
        ) : (
          <p className="mt-2 text-[12px] text-[#6e6e73]">
            Runtime plugin capabilities are synced from `/api/agent/connectors/plugins`.
          </p>
        )}
      </SettingsSection>

      {statusMessage ? (
        <div className="rounded-xl border border-[#ececf0] bg-white px-4 py-3">
          <p className="text-[12px] text-[#6e6e73]">{statusMessage}</p>
        </div>
      ) : null}

      <div className="space-y-4">
        {connectors.map((connector) => {
          const health = healthMap[connector.id];
          const stored = credentialMap[connector.id];
          const currentDraft = draftValues[connector.id] || {};
          const busy = savingConnectorId === connector.id;
          return (
            <ManualConnectorCard
              key={connector.id}
              connector={connector}
              health={health}
              stored={stored}
              capability={capabilityMap[connector.id]}
              currentDraft={currentDraft}
              busy={busy}
              onDraftChange={(fieldKey, value) => onDraftChange(connector.id, fieldKey, value)}
              onSave={() => onSaveConnector(connector)}
              onClear={() => onClearConnector(connector)}
            />
          );
        })}
      </div>
    </>
  );
}
