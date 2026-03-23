import type { SkinProps } from "./skinTypes";
import { ApprovalBanner, SkinHeader, SkinShell, ToolParamsPreview, ValidationBadges } from "./shared";

/** Gmail / Outlook compose view — To, Subject, Body fields filling in live. */
function EmailSkin({ state, palette, descriptor, activeTitle }: SkinProps) {
  const data = state.toolParams ?? {};
  const title = activeTitle || state.operationLabel || descriptor.actionVerb;

  return (
    <SkinShell palette={palette}>
      <SkinHeader palette={palette} descriptor={descriptor} title={title} status={state.statusLabel} subtitle={state.summaryText} />

      {/* Compose-style form */}
      <div className={`space-y-3 rounded-xl border ${palette.cardBorder} bg-white/60 p-4`}>
        <div className="flex items-center gap-3 border-b border-black/5 pb-2">
          <span className={`w-14 text-right text-[12px] font-medium ${palette.textSecondary}`}>To</span>
          <span className={`flex-1 text-[13px] ${palette.textPrimary}`}>{String(data["to"] || data["recipient"] || state.objectId || "…")}</span>
        </div>
        <div className="flex items-center gap-3 border-b border-black/5 pb-2">
          <span className={`w-14 text-right text-[12px] font-medium ${palette.textSecondary}`}>Subject</span>
          <span className={`flex-1 text-[13px] font-medium ${palette.textPrimary}`}>{String(data["subject"] || state.operationLabel || "…")}</span>
        </div>
        {data["cc"] ? (
          <div className="flex items-center gap-3 border-b border-black/5 pb-2">
            <span className={`w-14 text-right text-[12px] font-medium ${palette.textSecondary}`}>Cc</span>
            <span className={`flex-1 text-[13px] ${palette.textPrimary}`}>{String(data["cc"])}</span>
          </div>
        ) : null}
        <div className="pt-1">
          <p className={`min-h-[60px] whitespace-pre-wrap text-[13px] leading-relaxed ${palette.textPrimary}`}>
            {String(data["body"] || data["content"] || data["text"] || state.summaryText || "Composing…")}
          </p>
        </div>
      </div>

      <ValidationBadges validations={state.validations} />
      <ApprovalBanner state={state} />
    </SkinShell>
  );
}

export { EmailSkin };
