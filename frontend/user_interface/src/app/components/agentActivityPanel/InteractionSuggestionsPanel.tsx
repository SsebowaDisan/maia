import { INTERACTION_SUGGESTION_MIN_CONFIDENCE } from "./interactionSuggestionMerge";
import type { InteractionSuggestion } from "./interactionSuggestionMerge";
import {
  EVT_INTERACTION_SUGGESTION_SEND,
  type InteractionSuggestionSendDetail,
} from "../../constants/uiEvents";

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

const ACTION_COLOR: Record<string, string> = {
  navigate: "text-blue-700 bg-blue-50 border-blue-200",
  click: "text-indigo-700 bg-indigo-50 border-indigo-200",
  hover: "text-purple-700 bg-purple-50 border-purple-200",
  type: "text-emerald-700 bg-emerald-50 border-emerald-200",
  scroll: "text-slate-600 bg-slate-50 border-slate-200",
  extract: "text-amber-700 bg-amber-50 border-amber-200",
  verify: "text-green-700 bg-green-50 border-green-200",
  highlight: "text-orange-700 bg-orange-50 border-orange-200",
  search: "text-sky-700 bg-sky-50 border-sky-200",
};

const DEFAULT_COLOR = "text-slate-600 bg-slate-50 border-slate-200";

type InteractionSuggestionsPanelProps = {
  suggestions: InteractionSuggestion[] | null;
};

function pickPrimarySuggestion(suggestions: InteractionSuggestion[]): InteractionSuggestion {
  const explicitPrimary = suggestions.find((suggestion) => suggestion.primary);
  if (explicitPrimary) {
    return explicitPrimary;
  }
  return [...suggestions].sort((left, right) => right.confidence - left.confidence)[0];
}

function actionStyle(action: string): string {
  return ACTION_COLOR[action] ?? DEFAULT_COLOR;
}

function actionLabel(action: string): string {
  const normalized = String(action || "").trim().toLowerCase();
  return ACTION_LABEL[normalized] || normalized || "Action";
}

function buildSuggestionPrompt(suggestion: InteractionSuggestion): string {
  const action = String(suggestion.action || "").trim().toLowerCase();
  const target = String(suggestion.targetLabel || "").trim() || "this target";
  const reason = String(suggestion.reason || "").trim();
  if (action === "scroll") {
    return `Continue with the browser task: scroll to "${target}" and summarize what you find.`;
  }
  if (action === "click") {
    return `Continue with the browser task: click "${target}" and proceed to the next step.`;
  }
  if (action === "type") {
    return `Continue with the browser task: type into "${target}" and continue.`;
  }
  if (action === "extract") {
    return `Continue with the browser task: extract details from "${target}".`;
  }
  if (action === "verify") {
    return `Continue with the browser task: verify "${target}" and report the result.`;
  }
  const base = `Continue with the browser task: ${action || "check"} "${target}".`;
  return reason ? `${base} Context: ${reason}` : base;
}

function dispatchSuggestionPrompt(prompt: string) {
  if (typeof window === "undefined") {
    return;
  }
  const trimmedPrompt = String(prompt || "").trim();
  if (!trimmedPrompt) {
    return;
  }
  window.dispatchEvent(
    new CustomEvent<InteractionSuggestionSendDetail>(EVT_INTERACTION_SUGGESTION_SEND, {
      detail: { prompt: trimmedPrompt },
    }),
  );
}

function InteractionSuggestionsPanel({ suggestions }: InteractionSuggestionsPanelProps) {
  if (!suggestions || suggestions.length === 0) {
    return null;
  }

  const visible = suggestions
    .filter(
      (suggestion) =>
        suggestion.advisory === true &&
        suggestion.noExecution === true &&
        suggestion.confidence >= INTERACTION_SUGGESTION_MIN_CONFIDENCE,
    )
    .slice(0, 5);

  if (visible.length === 0) {
    return null;
  }

  const primarySuggestion = pickPrimarySuggestion(visible);
  const secondarySuggestions = visible.filter((suggestion) => suggestion !== primarySuggestion);
  const primaryAction = String(primarySuggestion.action || "").toLowerCase();
  const primaryBadgeClass = actionStyle(primaryAction);

  return (
    <div className="mt-2.5 rounded-xl border border-[#e8eaef] bg-white px-3 py-2.5 shadow-[0_2px_8px_-4px_rgba(15,23,42,0.10)]">
      <p className="mb-2 text-[9.5px] font-semibold uppercase tracking-widest text-[#9ca3af]">
        Follow-along hints
      </p>

      <button
        type="button"
        onClick={() => dispatchSuggestionPrompt(buildSuggestionPrompt(primarySuggestion))}
        className="w-full rounded-xl border border-[#dde3f1] bg-[#f8fbff] p-3 text-left shadow-[0_8px_18px_-14px_rgba(37,99,235,0.45)] transition hover:border-[#bfd1fb] hover:bg-[#f2f7ff]"
      >
        <div className="flex items-start justify-between gap-2">
          <span
            className={`rounded border px-1.5 py-px text-[9px] font-bold uppercase tracking-wide ${primaryBadgeClass}`}
          >
            {actionLabel(primaryAction)}
          </span>
          <span className="rounded-full border border-[#bbd4ff] bg-[#ebf3ff] px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-[#1e4fa8]">
            Recommended
          </span>
        </div>
        <p className="mt-2 text-[12px] font-semibold leading-snug text-[#1f2937]">
          {primarySuggestion.targetLabel || "(unknown target)"}
        </p>
        {primarySuggestion.highlightText ? (
          <p className="mt-1 text-[11px] italic leading-snug text-[#4b5563]">
            "{primarySuggestion.highlightText}"
          </p>
        ) : null}
        {primarySuggestion.reason ? (
          <p className="mt-1.5 text-[11px] leading-snug text-[#6b7280]">
            {primarySuggestion.reason}
          </p>
        ) : null}
      </button>

      {secondarySuggestions.length > 0 ? (
        <div className="mt-2 grid grid-cols-1 gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
          {secondarySuggestions.map((suggestion, index) => {
            const action = String(suggestion.action || "").toLowerCase();
            return (
              <button
                type="button"
                onClick={() => dispatchSuggestionPrompt(buildSuggestionPrompt(suggestion))}
                key={`${suggestion.eventId || ""}-${index}`}
                className="flex min-w-0 items-start gap-2 rounded-lg border border-[#f0f1f5] bg-[#fafbfc] px-2.5 py-2 text-left transition hover:border-[#dbe1ea] hover:bg-white"
              >
                <span
                  className={`mt-px shrink-0 rounded border px-1.5 py-px text-[8.5px] font-bold leading-tight tracking-wide ${actionStyle(action)}`}
                >
                  {actionLabel(action)}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[11px] font-medium leading-tight text-[#1f2937]">
                    {suggestion.targetLabel || "(unknown target)"}
                  </p>
                  {suggestion.highlightText ? (
                    <p className="mt-0.5 truncate text-[10px] italic leading-tight text-[#6b7280]">
                      "{suggestion.highlightText}"
                    </p>
                  ) : null}
                </div>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

export { InteractionSuggestionsPanel };
