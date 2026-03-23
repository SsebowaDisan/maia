import type { SkinProps } from "./skinTypes";
import { ApprovalBanner, FieldDiffsList, InfoCell, SkinHeader, SkinShell, ValidationBadges } from "./shared";

/** Figma — canvas preview with artboard and component info. */
function DesignSkin({ state, palette, descriptor, activeTitle }: SkinProps) {
  const data = state.toolParams ?? {};
  const title = activeTitle || state.operationLabel || descriptor.actionVerb;

  return (
    <SkinShell palette={palette}>
      <SkinHeader palette={palette} descriptor={descriptor} title={title} status={state.statusLabel} />

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <InfoCell label="File" value={String(data["file_key"] || data["file_name"] || state.objectId || "Design file")} palette={palette} />
        <InfoCell label="Frame" value={String(data["node_id"] || data["frame"] || state.objectType || "—")} palette={palette} />
        <InfoCell label="Action" value={state.operationLabel || descriptor.actionVerb} palette={palette} />
      </div>

      {/* Canvas placeholder */}
      <div className={`flex flex-1 items-center justify-center rounded-xl border-2 border-dashed ${palette.cardBorder} bg-white/40 p-8`}>
        <div className="text-center">
          <div className={`mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-2xl ${palette.accentBg}`}>
            <span className={`text-[28px] font-bold ${palette.accentText}`}>F</span>
          </div>
          <p className={`text-[14px] font-semibold ${palette.textPrimary}`}>{descriptor.brand} Canvas</p>
          <p className={`mt-1 text-[12px] ${palette.textSecondary}`}>{state.summaryText || "Reviewing design file…"}</p>
        </div>
      </div>

      <FieldDiffsList diffs={state.fieldDiffs} palette={palette} />
      <ValidationBadges validations={state.validations} />
      <ApprovalBanner state={state} />
    </SkinShell>
  );
}

export { DesignSkin };
