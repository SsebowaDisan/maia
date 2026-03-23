import type { SkinProps } from "./skinTypes";
import { ApprovalBanner, FieldDiffsList, SkinHeader, SkinShell, ValidationBadges } from "./shared";

/** Notion / Confluence / Dropbox / Box / DocuSign — document viewer/editor. */
function DocumentSkin({ state, palette, descriptor, activeTitle }: SkinProps) {
  const data = state.toolParams ?? {};
  const title = activeTitle || state.operationLabel || descriptor.actionVerb;
  const docTitle = String(data["title"] || data["page_title"] || data["file_name"] || state.objectType || "Untitled");
  const content = String(data["content"] || data["body"] || data["text"] || state.summaryText || "");

  return (
    <SkinShell palette={palette}>
      <SkinHeader palette={palette} descriptor={descriptor} title={title} status={state.statusLabel} />

      {/* Document page */}
      <div className={`flex-1 rounded-xl border ${palette.cardBorder} bg-white/80 p-5`}>
        <h2 className={`text-[18px] font-bold leading-tight ${palette.textPrimary}`}>{docTitle}</h2>
        <div className={`mt-1 flex items-center gap-2 text-[11px] ${palette.textSecondary}`}>
          <span>{descriptor.brand}</span>
          <span>·</span>
          <span>{state.operationLabel}</span>
          {state.objectId ? (
            <>
              <span>·</span>
              <span className="font-mono">{state.objectId}</span>
            </>
          ) : null}
        </div>
        {content ? (
          <p className={`mt-4 whitespace-pre-wrap text-[13px] leading-relaxed ${palette.textPrimary}`}>
            {content.length > 600 ? content.slice(0, 600) + "…" : content}
          </p>
        ) : (
          <div className="mt-4 space-y-2">
            {[...Array(4)].map((_, i) => (
              <div key={i} className={`h-3 rounded ${palette.accentBg}`} style={{ width: `${85 - i * 12}%` }} />
            ))}
          </div>
        )}
      </div>

      <FieldDiffsList diffs={state.fieldDiffs} palette={palette} />
      <ValidationBadges validations={state.validations} />
      <ApprovalBanner state={state} />
    </SkinShell>
  );
}

export { DocumentSkin };
