import { useMemo, useState } from "react";

const VARIABLE_HINTS = [
  "{{user.name}}",
  "{{company.name}}",
  "{{memory.recent_episodes}}",
  "{{tool.results}}",
  "{{date.today}}",
];

type SystemPromptEditorProps = {
  value: string;
  onChange: (next: string) => void;
};

function estimateTokens(text: string): number {
  const words = String(text || "").trim().split(/\s+/g).filter(Boolean).length;
  return Math.ceil(words * 1.35);
}

export function SystemPromptEditor({ value, onChange }: SystemPromptEditorProps) {
  const [showHints, setShowHints] = useState(false);
  const [hintFilter, setHintFilter] = useState("");
  const tokenEstimate = useMemo(() => estimateTokens(value), [value]);

  const hintOptions = useMemo(() => {
    if (!hintFilter) {
      return VARIABLE_HINTS;
    }
    const normalized = hintFilter.toLowerCase();
    return VARIABLE_HINTS.filter((hint) => hint.toLowerCase().includes(normalized));
  }, [hintFilter]);

  const handleChange = (next: string) => {
    onChange(next);
    const cursorToken = next.slice(-32);
    const lastHandle = cursorToken.lastIndexOf("{{");
    if (lastHandle >= 0) {
      const query = cursorToken.slice(lastHandle + 2).replace(/[{}\s]/g, "");
      setHintFilter(query);
      setShowHints(true);
      return;
    }
    setShowHints(false);
    setHintFilter("");
  };

  const insertHint = (hint: string) => {
    onChange(`${value}${value.endsWith(" ") || !value ? "" : " "}${hint}`);
    setShowHints(false);
    setHintFilter("");
  };

  return (
    <div className="relative rounded-2xl border border-black/[0.08] bg-white p-4">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">System prompt</p>
        <div className="text-[12px] text-[#667085]">
          {value.length} chars · ~{tokenEstimate} tokens
        </div>
      </div>
      <textarea
        value={value}
        onChange={(event) => handleChange(event.target.value)}
        placeholder="Define the agent behavior, boundaries, and output style..."
        className="h-[220px] w-full resize-none rounded-xl border border-black/[0.12] px-3 py-2 text-[14px] leading-[1.5] text-[#111827] focus:border-black/[0.28] focus:outline-none"
      />
      {showHints && hintOptions.length ? (
        <div className="absolute left-4 top-[58px] z-20 w-[320px] rounded-xl border border-black/[0.12] bg-white p-2 shadow-[0_18px_34px_rgba(15,23,42,0.16)]">
          <p className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-[0.1em] text-[#667085]">Variable hints</p>
          <div className="space-y-1">
            {hintOptions.map((hint) => (
              <button
                key={hint}
                type="button"
                onClick={() => insertHint(hint)}
                className="w-full rounded-lg px-2 py-1.5 text-left text-[13px] text-[#111827] hover:bg-[#f8fafc]"
              >
                {hint}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

