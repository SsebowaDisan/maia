import type { SkinProps } from "./skinTypes";
import { ApprovalBanner, SkinHeader, SkinShell, ToolParamsPreview, ValidationBadges } from "./shared";

/** Calendly / Google Calendar — calendar event card. */
function SchedulingSkin({ state, palette, descriptor, activeTitle }: SkinProps) {
  const data = state.toolParams ?? {};
  const title = activeTitle || state.operationLabel || descriptor.actionVerb;

  return (
    <SkinShell palette={palette}>
      <SkinHeader palette={palette} descriptor={descriptor} title={title} status={state.statusLabel} />

      {/* Calendar event card */}
      <div className={`rounded-xl border-l-4 ${palette.cardBorder} bg-white/70 p-4`} style={{ borderLeftColor: "currentColor" }}>
        <div className={`border-l-4 border-current pl-3 ${palette.accentText}`}>
          <p className={`text-[16px] font-bold ${palette.textPrimary}`}>
            {String(data["title"] || data["event_name"] || state.objectType || "Meeting")}
          </p>
          <div className={`mt-2 flex flex-wrap items-center gap-3 text-[13px] ${palette.textSecondary}`}>
            {data["start"] || data["date"] ? (
              <span>📅 {String(data["start"] || data["date"])}</span>
            ) : null}
            {data["end"] ? <span>→ {String(data["end"])}</span> : null}
            {data["attendees"] || data["signer_email"] ? (
              <span>👤 {String(data["attendees"] || data["signer_email"])}</span>
            ) : null}
          </div>
          {data["description"] || data["reason"] ? (
            <p className={`mt-2 text-[13px] ${palette.textPrimary}`}>
              {String(data["description"] || data["reason"])}
            </p>
          ) : null}
        </div>
      </div>

      <ToolParamsPreview
        data={data}
        palette={palette}
        fields={[
          { key: "location", label: "Location" },
          { key: "meeting_link", label: "Meeting link" },
          { key: "notes", label: "Notes" },
        ]}
      />

      <ValidationBadges validations={state.validations} />
      <ApprovalBanner state={state} />
    </SkinShell>
  );
}

export { SchedulingSkin };
