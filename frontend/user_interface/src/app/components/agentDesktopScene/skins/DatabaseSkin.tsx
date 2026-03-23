import type { SkinProps } from "./skinTypes";
import { ApprovalBanner, SkinHeader, SkinShell, ValidationBadges } from "./shared";

/** PostgreSQL / Supabase / BigQuery / Pinecone — query + results table. */
function DatabaseSkin({ state, palette, descriptor, activeTitle }: SkinProps) {
  const data = state.toolParams ?? {};
  const title = activeTitle || state.operationLabel || descriptor.actionVerb;
  const sql = String(data["sql"] || data["query"] || data["filter"] || "");
  const table = String(data["table"] || data["index_name"] || data["dataset_id"] || state.objectType || "—");

  return (
    <SkinShell palette={palette}>
      <SkinHeader palette={palette} descriptor={descriptor} title={title} status={state.statusLabel} />

      {/* SQL / Query preview */}
      {sql ? (
        <div className={`rounded-xl border ${palette.cardBorder} bg-black/30 p-3`}>
          <p className={`mb-1 text-[11px] uppercase tracking-[0.08em] ${palette.textSecondary}`}>Query</p>
          <pre className={`whitespace-pre-wrap font-mono text-[12px] leading-relaxed ${palette.textPrimary}`}>
            {sql.length > 500 ? sql.slice(0, 500) + "…" : sql}
          </pre>
        </div>
      ) : null}

      {/* Table / Resource info */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className={`rounded-xl border ${palette.cardBorder} bg-black/20 p-3`}>
          <p className={`text-[11px] uppercase tracking-[0.08em] ${palette.textSecondary}`}>Table / Index</p>
          <p className={`mt-1 font-mono text-[14px] font-semibold ${palette.textPrimary}`}>{table}</p>
        </div>
        <div className={`rounded-xl border ${palette.cardBorder} bg-black/20 p-3`}>
          <p className={`text-[11px] uppercase tracking-[0.08em] ${palette.textSecondary}`}>Operation</p>
          <p className={`mt-1 text-[14px] font-semibold ${palette.textPrimary}`}>{state.operationLabel}</p>
        </div>
        <div className={`rounded-xl border ${palette.cardBorder} bg-black/20 p-3`}>
          <p className={`text-[11px] uppercase tracking-[0.08em] ${palette.textSecondary}`}>Status</p>
          <p className={`mt-1 text-[14px] font-semibold ${palette.accentText}`}>{state.statusLabel || "executing"}</p>
        </div>
      </div>

      {/* Results placeholder */}
      {state.summaryText ? (
        <div className={`rounded-xl border ${palette.cardBorder} bg-black/20 p-3`}>
          <p className={`text-[11px] uppercase tracking-[0.08em] ${palette.textSecondary}`}>Result</p>
          <p className={`mt-1 whitespace-pre-wrap text-[13px] leading-relaxed ${palette.textPrimary}`}>
            {state.summaryText}
          </p>
        </div>
      ) : null}

      <ValidationBadges validations={state.validations} />
      <ApprovalBanner state={state} />
    </SkinShell>
  );
}

export { DatabaseSkin };
