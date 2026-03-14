type ImprovementSuggestionProps = {
  feedbackCount: number;
  currentPrompt: string;
  suggestedPrompt: string;
  reasoning?: string;
  loading?: boolean;
  error?: string;
  onApply: () => void;
  onRefresh?: () => void;
  onDismiss: () => void;
};

export function ImprovementSuggestion({
  feedbackCount,
  currentPrompt,
  suggestedPrompt,
  reasoning = "",
  loading = false,
  error = "",
  onApply,
  onRefresh,
  onDismiss,
}: ImprovementSuggestionProps) {
  const hasSuggestion = Boolean(String(suggestedPrompt || "").trim());
  return (
    <section className="rounded-2xl border border-[#bfdbfe] bg-[#eff6ff] p-4">
      <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#1d4ed8]">
        Improvement suggestion
      </p>
      <h3 className="mt-1 text-[18px] font-semibold text-[#1e3a8a]">
        Based on {feedbackCount} feedback records, prompt improvements are available
      </h3>
      {loading ? (
        <p className="mt-3 rounded-xl border border-[#bfdbfe] bg-white px-3 py-2 text-[13px] text-[#1e3a8a]">
          Generating suggestion...
        </p>
      ) : null}
      {error ? (
        <p className="mt-3 rounded-xl border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-[13px] text-[#b42318]">
          {error}
        </p>
      ) : null}
      {hasSuggestion ? (
        <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
          <div className="rounded-xl border border-[#bfdbfe] bg-white p-3">
            <p className="text-[12px] font-semibold text-[#1d4ed8]">Current prompt</p>
            <p className="mt-1 whitespace-pre-wrap text-[13px] text-[#334155]">{currentPrompt}</p>
          </div>
          <div className="rounded-xl border border-[#86efac] bg-white p-3">
            <p className="text-[12px] font-semibold text-[#15803d]">Suggested prompt</p>
            <p className="mt-1 whitespace-pre-wrap text-[13px] text-[#166534]">{suggestedPrompt}</p>
          </div>
        </div>
      ) : null}
      {reasoning ? (
        <div className="mt-3 rounded-xl border border-[#bfdbfe] bg-white p-3">
          <p className="text-[12px] font-semibold text-[#1d4ed8]">Why this change</p>
          <p className="mt-1 whitespace-pre-wrap text-[13px] text-[#334155]">{reasoning}</p>
        </div>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onApply}
          disabled={!hasSuggestion || loading}
          className="rounded-full bg-[#111827] px-4 py-2 text-[12px] font-semibold text-white disabled:opacity-50"
        >
          Apply
        </button>
        <button
          type="button"
          onClick={onDismiss}
          className="rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[12px] font-semibold text-[#344054]"
        >
          Dismiss
        </button>
        {onRefresh ? (
          <button
            type="button"
            onClick={onRefresh}
            disabled={loading}
            className="rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[12px] font-semibold text-[#344054] disabled:opacity-50"
          >
            Refresh
          </button>
        ) : null}
      </div>
    </section>
  );
}
