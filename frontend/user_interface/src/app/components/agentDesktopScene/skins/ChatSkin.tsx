import type { SkinProps } from "./skinTypes";
import { ApprovalBanner, SkinHeader, SkinShell, ValidationBadges } from "./shared";

/** Slack / Discord / Teams channel view — message bubble appearing live. */
function ChatSkin({ state, palette, descriptor, activeTitle }: SkinProps) {
  const data = state.toolParams ?? {};
  const title = activeTitle || state.operationLabel || descriptor.actionVerb;
  const channel = String(data["channel"] || data["channel_id"] || state.objectId || "#general");
  const message = String(data["text"] || data["content"] || data["body"] || state.summaryText || "Typing…");

  return (
    <SkinShell palette={palette}>
      <SkinHeader palette={palette} descriptor={descriptor} title={title} status={state.statusLabel} />

      {/* Channel header */}
      <div className={`flex items-center gap-2 rounded-lg ${palette.accentBg} px-3 py-2`}>
        <span className={`text-[16px] font-bold ${palette.accentText}`}>#</span>
        <span className={`text-[14px] font-semibold ${palette.textPrimary}`}>{channel}</span>
      </div>

      {/* Message bubble */}
      <div className={`rounded-xl border ${palette.cardBorder} bg-white/60 p-4`}>
        <div className="flex items-start gap-3">
          <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${palette.accentBg} text-[14px] font-bold ${palette.accentText}`}>
            M
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className={`text-[13px] font-bold ${palette.textPrimary}`}>Maia Agent</span>
              <span className={`text-[11px] ${palette.textSecondary}`}>just now</span>
            </div>
            <p className={`mt-1 whitespace-pre-wrap text-[13px] leading-relaxed ${palette.textPrimary}`}>{message}</p>
          </div>
        </div>
      </div>

      <ValidationBadges validations={state.validations} />
      <ApprovalBanner state={state} />
    </SkinShell>
  );
}

export { ChatSkin };
