import { SettingsRow } from "../ui/SettingsRow";
import { SettingsSection } from "../ui/SettingsSection";
import { StatusChip, toneFromBoolean } from "../ui/StatusChip";

type GeneralSettingsProps = {
  loading: boolean;
  oauthConnected: boolean;
  ollamaReachable: boolean;
  mapsConfigured: boolean;
  braveConfigured: boolean;
  statusMessage: string;
};

export function GeneralSettings({
  loading,
  oauthConnected,
  ollamaReachable,
  mapsConfigured,
  braveConfigured,
  statusMessage,
}: GeneralSettingsProps) {
  const oauth = toneFromBoolean(oauthConnected, { trueLabel: "Connected", falseLabel: "Not connected" });
  const ollama = toneFromBoolean(ollamaReachable, { trueLabel: "Online", falseLabel: "Offline" });
  const maps = toneFromBoolean(mapsConfigured, { trueLabel: "Configured", falseLabel: "Not configured" });
  const brave = toneFromBoolean(braveConfigured, { trueLabel: "Configured", falseLabel: "Not configured" });

  return (
    <>
      <SettingsSection
        title="Workspace"
        subtitle="Overview of your local runtime and service connections."
      >
        <SettingsRow
          title="Sync status"
          description="Current settings snapshot from backend services."
          right={<StatusChip label={loading ? "Refreshing" : "Synced"} tone={loading ? "warning" : "neutral"} />}
        />
        <SettingsRow
          title="Google OAuth"
          description="Authentication for Gmail, Calendar, Docs, Sheets, and Analytics."
          right={<StatusChip label={oauth.label} tone={oauth.tone} />}
        />
        <SettingsRow
          title="Local model runtime"
          description="Ollama service status for local inference."
          right={<StatusChip label={ollama.label} tone={ollama.tone} />}
        />
        <SettingsRow
          title="Google Maps API"
          description="Places, Geocode, and Distance Matrix support."
          right={<StatusChip label={maps.label} tone={maps.tone} />}
        />
        <SettingsRow
          title="Brave Search API"
          description="Primary web research provider."
          right={<StatusChip label={brave.label} tone={brave.tone} />}
          noDivider
        />
      </SettingsSection>

      <SettingsSection title="Notices" subtitle="Operational messages from recent settings actions.">
        <SettingsRow
          title="Latest message"
          description={statusMessage || "No new notices."}
          right={<StatusChip label="Info" tone="neutral" />}
          noDivider
        />
      </SettingsSection>
    </>
  );
}
