import type { SkinProps } from "./skinTypes";
import { ApprovalBanner, SkinHeader, SkinShell, ValidationBadges } from "./shared";

/** Twitter / LinkedIn / YouTube / Spotify — post/feed view. */
function SocialSkin({ state, palette, descriptor, activeTitle }: SkinProps) {
  const data = state.toolParams ?? {};
  const title = activeTitle || state.operationLabel || descriptor.actionVerb;
  const postContent = String(data["text"] || data["content"] || data["body"] || data["query"] || state.summaryText || "");
  const username = String(data["username"] || "maia_agent");

  return (
    <SkinShell palette={palette}>
      <SkinHeader palette={palette} descriptor={descriptor} title={title} status={state.statusLabel} />

      {/* Post card */}
      <div className={`rounded-xl border ${palette.cardBorder} bg-white/60 p-4`}>
        <div className="flex items-start gap-3">
          <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${palette.accentBg} text-[15px] font-bold ${palette.accentText}`}>
            {descriptor.brand.charAt(0)}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className={`text-[14px] font-bold ${palette.textPrimary}`}>Maia Agent</span>
              <span className={`text-[12px] ${palette.textSecondary}`}>@{username}</span>
              <span className={`text-[12px] ${palette.textSecondary}`}>· just now</span>
            </div>
            <p className={`mt-2 whitespace-pre-wrap text-[14px] leading-relaxed ${palette.textPrimary}`}>
              {postContent || "Composing post…"}
            </p>
            {/* Engagement bar */}
            <div className={`mt-3 flex items-center gap-6 text-[12px] ${palette.textSecondary}`}>
              <span>💬 0</span>
              <span>🔁 0</span>
              <span>❤️ 0</span>
              <span>📊 0</span>
            </div>
          </div>
        </div>
      </div>

      <ValidationBadges validations={state.validations} />
      <ApprovalBanner state={state} />
    </SkinShell>
  );
}

export { SocialSkin };
