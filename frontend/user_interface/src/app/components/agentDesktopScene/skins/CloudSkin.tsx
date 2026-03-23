import type { SkinProps } from "./skinTypes";
import { ApprovalBanner, FieldDiffsList, InfoCell, SkinHeader, SkinShell, ValidationBadges } from "./shared";

/** AWS / Cloudflare / Vercel — dashboard with service name and status indicators. */
function CloudSkin({ state, palette, descriptor, activeTitle }: SkinProps) {
  const data = state.toolParams ?? {};
  const title = activeTitle || state.operationLabel || descriptor.actionVerb;

  return (
    <SkinShell palette={palette}>
      <SkinHeader palette={palette} descriptor={descriptor} title={title} status={state.statusLabel} />

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <InfoCell label="Service" value={String(data["service"] || data["namespace"] || state.connectorLabel || descriptor.brand)} palette={palette} />
        <InfoCell label="Resource" value={String(data["resource"] || data["bucket"] || data["zone_id"] || data["project_id"] || state.objectId || "—")} palette={palette} />
        <InfoCell label="Region" value={String(data["region"] || data["zone"] || "global")} palette={palette} />
      </div>

      {/* Status indicators */}
      <div className={`grid grid-cols-3 gap-2 rounded-xl border ${palette.cardBorder} bg-black/20 p-3`}>
        {[
          { label: "Health", value: "● Healthy", color: "text-green-400" },
          { label: "Latency", value: "12ms", color: palette.accentText },
          { label: "Uptime", value: "99.98%", color: palette.accentText },
        ].map((m) => (
          <div key={m.label} className="text-center">
            <p className={`text-[11px] ${palette.textSecondary}`}>{m.label}</p>
            <p className={`mt-1 text-[14px] font-bold ${m.color}`}>{m.value}</p>
          </div>
        ))}
      </div>

      {state.summaryText ? (
        <div className={`rounded-xl border ${palette.cardBorder} bg-black/20 p-3`}>
          <p className={`whitespace-pre-wrap text-[13px] leading-relaxed ${palette.textPrimary}`}>{state.summaryText}</p>
        </div>
      ) : null}

      <FieldDiffsList diffs={state.fieldDiffs} palette={palette} />
      <ValidationBadges validations={state.validations} />
      <ApprovalBanner state={state} />
    </SkinShell>
  );
}

export { CloudSkin };
