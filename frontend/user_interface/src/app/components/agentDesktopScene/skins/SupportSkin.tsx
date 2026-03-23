import type { SkinProps } from "./skinTypes";
import { ApprovalBanner, FieldDiffsList, SkinHeader, SkinShell, ToolParamsPreview, ValidationBadges } from "./shared";

/** Zendesk / Intercom — ticket view with status, priority, and conversation. */
function SupportSkin({ state, palette, descriptor, activeTitle }: SkinProps) {
  const data = state.toolParams ?? {};
  const title = activeTitle || state.operationLabel || descriptor.actionVerb;
  const ticketId = String(data["ticket_id"] || data["conversation_id"] || state.objectId || "#—");
  const priority = String(data["priority"] || "normal");
  const subject = String(data["subject"] || state.operationLabel || "Support request");

  const priorityColor: Record<string, string> = {
    urgent: "bg-red-100 text-red-800 border-red-200",
    high: "bg-orange-100 text-orange-800 border-orange-200",
    normal: "bg-blue-100 text-blue-800 border-blue-200",
    low: "bg-gray-100 text-gray-700 border-gray-200",
  };

  return (
    <SkinShell palette={palette}>
      <SkinHeader palette={palette} descriptor={descriptor} title={title} status={state.statusLabel} />

      {/* Ticket header */}
      <div className={`flex items-center gap-3 rounded-xl border ${palette.cardBorder} bg-white/60 p-3`}>
        <span className={`rounded-md border px-2 py-0.5 text-[12px] font-bold ${palette.accentText} ${palette.accentBg}`}>{ticketId}</span>
        <span className={`flex-1 text-[14px] font-semibold ${palette.textPrimary}`}>{subject}</span>
        <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${priorityColor[priority] || priorityColor.normal}`}>
          {priority}
        </span>
      </div>

      {/* Conversation thread */}
      <div className={`space-y-2 rounded-xl border ${palette.cardBorder} bg-white/60 p-3`}>
        <p className={`text-[12px] font-semibold ${palette.textPrimary}`}>Response</p>
        <p className={`whitespace-pre-wrap text-[13px] leading-relaxed ${palette.textPrimary}`}>
          {String(data["body"] || data["comment"] || data["description"] || state.summaryText || "Drafting response…")}
        </p>
      </div>

      <FieldDiffsList diffs={state.fieldDiffs} palette={palette} />
      <ValidationBadges validations={state.validations} />
      <ApprovalBanner state={state} />
    </SkinShell>
  );
}

export { SupportSkin };
