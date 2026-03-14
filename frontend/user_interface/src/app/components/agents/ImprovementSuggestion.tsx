type ImprovementSuggestionProps = {
  feedbackCount: number;
  currentPrompt: string;
  suggestedPrompt: string;
  onApply: () => void;
  onDismiss: () => void;
};

export function ImprovementSuggestion({
  feedbackCount,
  currentPrompt,
  suggestedPrompt,
  onApply,
  onDismiss,
}: ImprovementSuggestionProps) {
  return (
    <section className="rounded-2xl border border-[#bfdbfe] bg-[#eff6ff] p-4">
      <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#1d4ed8]">Improvement suggestion</p>
      <h3 className="mt-1 text-[18px] font-semibold text-[#1e3a8a]">
        Based on {feedbackCount} corrections, prompt improvements are available
      </h3>
      <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
        <div className="rounded-xl border border-[#bfdbfe] bg-white p-3">
          <p className="text-[12px] font-semibold text-[#1d4ed8]">Current prompt</p>
          <p className="mt-1 text-[13px] text-[#334155]">{currentPrompt}</p>
        </div>
        <div className="rounded-xl border border-[#86efac] bg-white p-3">
          <p className="text-[12px] font-semibold text-[#15803d]">Suggested prompt</p>
          <p className="mt-1 text-[13px] text-[#166534]">{suggestedPrompt}</p>
        </div>
      </div>
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={onApply}
          className="rounded-full bg-[#111827] px-4 py-2 text-[12px] font-semibold text-white"
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
      </div>
    </section>
  );
}

