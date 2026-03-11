import { INTERACTION_SUGGESTION_MIN_CONFIDENCE } from "./interactionSuggestionMerge";
import type { InteractionSuggestion } from "./interactionSuggestionMerge";

const ACTION_ICON: Record<string, string> = {
  navigate: "↗",
  click: "↳",
  hover: "◎",
  type: "✎",
  scroll: "⇅",
  extract: "◈",
  verify: "✓",
  highlight: "✦",
  search: "⌕",
};

const ACTION_LABEL: Record<string, string> = {
  navigate: "Navigate",
  click: "Click",
  hover: "Check",
  type: "Type",
  scroll: "Scroll",
  extract: "Extract",
  verify: "Verify",
  highlight: "Highlight",
  search: "Search",
};

const ACTION_COLOR: Record<string, { badge: string; dot: string }> = {
  navigate:  { badge: "text-blue-700 bg-blue-50 border-blue-200",    dot: "bg-blue-400" },
  click:     { badge: "text-indigo-700 bg-indigo-50 border-indigo-200", dot: "bg-indigo-400" },
  hover:     { badge: "text-purple-700 bg-purple-50 border-purple-200", dot: "bg-purple-400" },
  type:      { badge: "text-emerald-700 bg-emerald-50 border-emerald-200", dot: "bg-emerald-400" },
  scroll:    { badge: "text-slate-600 bg-slate-50 border-slate-200",  dot: "bg-slate-400" },
  extract:   { badge: "text-amber-700 bg-amber-50 border-amber-200",  dot: "bg-amber-400" },
  verify:    { badge: "text-green-700 bg-green-50 border-green-200",  dot: "bg-green-400" },
  highlight: { badge: "text-orange-700 bg-orange-50 border-orange-200", dot: "bg-orange-400" },
  search:    { badge: "text-sky-700 bg-sky-50 border-sky-200",        dot: "bg-sky-400" },
};

const DEFAULT_COLOR = { badge: "text-slate-600 bg-slate-50 border-slate-200", dot: "bg-slate-400" };

type InteractionSuggestionsPanelProps = {
  suggestions: InteractionSuggestion[] | null;
};

function InteractionSuggestionsPanel({ suggestions }: InteractionSuggestionsPanelProps) {
  if (!suggestions || suggestions.length === 0) {
    return null;
  }

  const visible = suggestions
    .filter(
      (s) =>
        s.advisory === true &&
        s.noExecution === true &&
        s.confidence >= INTERACTION_SUGGESTION_MIN_CONFIDENCE,
    )
    .slice(0, 5);

  if (visible.length === 0) {
    return null;
  }

  return (
    <div className="mt-2.5 rounded-xl border border-[#e8eaef] bg-white px-3 py-2.5 shadow-[0_2px_8px_-4px_rgba(15,23,42,0.10)]">
      <p className="mb-2 text-[9.5px] font-semibold uppercase tracking-widest text-[#9ca3af]">
        Follow-along hints
      </p>
      <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
        {visible.map((s, i) => {
          const action = String(s.action || "").toLowerCase();
          const colors = ACTION_COLOR[action] ?? DEFAULT_COLOR;
          const icon = ACTION_ICON[action] ?? "·";
          const label = ACTION_LABEL[action] ?? action;
          const hasHighlight = Boolean(s.highlightText);
          return (
            <div
              key={`${s.eventId || ""}-${i}`}
              className="flex min-w-0 items-start gap-2 rounded-lg border border-[#f0f1f5] bg-[#fafbfc] px-2.5 py-2"
            >
              {/* Action badge */}
              <span
                className={`mt-px shrink-0 rounded border px-1.5 py-px text-[8.5px] font-bold leading-tight tracking-wide ${colors.badge}`}
              >
                {icon}&nbsp;{label}
              </span>
              {/* Content */}
              <div className="min-w-0 flex-1">
                <p className="truncate text-[11px] font-medium leading-tight text-[#1f2937]">
                  {s.targetLabel || "(unknown target)"}
                </p>
                {hasHighlight ? (
                  <p className="mt-0.5 truncate text-[10px] italic leading-tight text-[#6b7280]">
                    &ldquo;{s.highlightText}&rdquo;
                  </p>
                ) : s.reason ? (
                  <p className="mt-0.5 line-clamp-1 text-[10px] leading-tight text-[#9ca3af]">
                    {s.reason}
                  </p>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export { InteractionSuggestionsPanel };
