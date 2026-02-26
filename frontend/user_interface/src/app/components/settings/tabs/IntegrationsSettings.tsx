import type { AgentLiveEvent, GoogleOAuthStatus } from "../../../../api/client";
import type { GoogleToolHealthItem } from "../types";
import { SettingsRow } from "../ui/SettingsRow";
import { SettingsSection } from "../ui/SettingsSection";
import { StatusChip, toneFromBoolean } from "../ui/StatusChip";

type IntegrationsSettingsProps = {
  googleOAuthStatus: GoogleOAuthStatus;
  oauthStatus: string;
  googleToolHealth: GoogleToolHealthItem[];
  liveEvents: AgentLiveEvent[];
  onConnectGoogle: () => void;
  onDisconnectGoogle: () => void;
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

export function IntegrationsSettings({
  googleOAuthStatus,
  oauthStatus,
  googleToolHealth,
  liveEvents,
  onConnectGoogle,
  onDisconnectGoogle,
}: IntegrationsSettingsProps) {
  const oauthChip = toneFromBoolean(googleOAuthStatus.connected, {
    trueLabel: "Connected",
    falseLabel: "Not connected",
  });

  return (
    <>
      <SettingsSection
        title="Google"
        subtitle="Connect Google services for Gmail, Calendar, Drive, and Analytics."
        actions={
          <>
            <StatusChip label={oauthChip.label} tone={oauthChip.tone} />
            <button
              type="button"
              onClick={onConnectGoogle}
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
        {googleToolHealth.map((item, index) => {
          const chip = healthTone(item);
          return (
            <SettingsRow
              key={item.id}
              title={item.label}
              description={item.message || "Service status available after refresh."}
              right={<StatusChip label={chip.label} tone={chip.tone} />}
              noDivider={index === googleToolHealth.length - 1}
            />
          );
        })}
      </SettingsSection>

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

      {oauthStatus ? (
        <div className="rounded-xl border border-[#ececf0] bg-white px-4 py-3">
          <p className="text-[12px] text-[#6e6e73]">{oauthStatus}</p>
        </div>
      ) : null}
    </>
  );
}
