export interface DiffViewerProps {
  before: string;
  after: string;
}

export function DiffViewer({ before, after }: DiffViewerProps) {
  if (!before && !after) return null;

  const beforeWords = before.split(/\s+/).filter(Boolean);
  const afterWords = after.split(/\s+/).filter(Boolean);

  const beforeSet = new Set(beforeWords);
  const afterSet = new Set(afterWords);

  const removed = beforeWords.filter((w) => !afterSet.has(w)).slice(0, 40);
  const added = afterWords.filter((w) => !beforeSet.has(w)).slice(0, 40);

  if (!removed.length && !added.length) return null;

  return (
    <div
      className="pointer-events-none absolute bottom-3 right-3 z-30 w-64 rounded-xl border border-black/[0.12] bg-white/95 p-3 shadow-lg backdrop-blur-sm"
      style={{ animation: "diff-drop-in 300ms ease-out forwards" }}
    >
      <style>{`
        @keyframes diff-drop-in {
          0%   { opacity: 0; transform: translateY(8px) scale(0.96); }
          100% { opacity: 1; transform: translateY(0) scale(1); }
        }
      `}</style>
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-[#6e6e73]">
        Document edit
      </p>
      {removed.length > 0 ? (
        <div className="mb-1.5 flex flex-wrap gap-1">
          {removed.map((w, i) => (
            <span
              key={i}
              className="rounded bg-[#ff3b30]/10 px-1 py-0.5 text-[10px] text-[#c0392b] line-through"
            >
              {w}
            </span>
          ))}
        </div>
      ) : null}
      {added.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {added.map((w, i) => (
            <span
              key={i}
              className="rounded bg-[#34c759]/12 px-1 py-0.5 text-[10px] text-[#1a7a30]"
            >
              {w}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
