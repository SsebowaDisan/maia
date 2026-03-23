import type { SkinProps } from "./skinTypes";
import { ApprovalBanner, FieldDiffsList, SkinHeader, SkinShell, ValidationBadges } from "./shared";

/** Sheets / Excel / Airtable — spreadsheet grid with row highlight. */
function SheetSkin({ state, palette, descriptor, activeTitle }: SkinProps) {
  const title = activeTitle || state.operationLabel || descriptor.actionVerb;
  const cols = ["A", "B", "C", "D", "E"];

  return (
    <SkinShell palette={palette}>
      <SkinHeader palette={palette} descriptor={descriptor} title={title} status={state.statusLabel} subtitle={state.summaryText} />

      {/* Spreadsheet grid */}
      <div className={`overflow-hidden rounded-xl border ${palette.cardBorder}`}>
        {/* Column headers */}
        <div className={`grid grid-cols-6 ${palette.accentBg}`}>
          <div className={`border-r border-black/5 px-3 py-1.5 text-[11px] font-medium ${palette.textSecondary}`} />
          {cols.map((c) => (
            <div key={c} className={`border-r border-black/5 px-3 py-1.5 text-center text-[11px] font-bold ${palette.accentText}`}>{c}</div>
          ))}
        </div>
        {/* Rows */}
        {[1, 2, 3].map((row) => (
          <div key={row} className={`grid grid-cols-6 border-t border-black/5 ${row === 2 ? palette.accentBg : "bg-white/60"}`}>
            <div className={`border-r border-black/5 px-3 py-2 text-[11px] font-medium ${palette.textSecondary}`}>{row}</div>
            {cols.map((c) => {
              const diff = state.fieldDiffs.find((d) => d.field.toLowerCase().includes(c.toLowerCase()));
              return (
                <div key={c} className={`border-r border-black/5 px-3 py-2 text-[12px] ${palette.textPrimary}`}>
                  {row === 2 && diff ? (
                    <span className={`font-medium ${palette.accentText}`}>{diff.toValue || "—"}</span>
                  ) : (
                    <span className="opacity-30">—</span>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>

      <FieldDiffsList diffs={state.fieldDiffs} palette={palette} />
      <ValidationBadges validations={state.validations} />
      <ApprovalBanner state={state} />
    </SkinShell>
  );
}

export { SheetSkin };
