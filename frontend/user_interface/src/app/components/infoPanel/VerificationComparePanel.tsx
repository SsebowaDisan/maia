import { useMemo, useState } from "react";

import type { EvidenceCard } from "../../utils/infoInsights";
import { choosePreferredSourceUrl, evidenceSourceLabel } from "./urlHelpers";

type VerificationComparePanelProps = {
  cards: EvidenceCard[];
  onSelectCard: (card: EvidenceCard, index: number) => void;
};

function optionLabel(card: EvidenceCard, index: number): string {
  const source = evidenceSourceLabel(card);
  const snippet = String(card.extract || card.title || "").replace(/\s+/g, " ").trim();
  const shortSnippet = snippet.length > 72 ? `${snippet.slice(0, 72)}...` : snippet;
  return `[${index + 1}] ${source} - ${shortSnippet}`;
}

function ComparisonCard({
  card,
  index,
  onOpen,
}: {
  card: EvidenceCard;
  index: number;
  onOpen: (card: EvidenceCard, index: number) => void;
}) {
  const sourceUrl = choosePreferredSourceUrl([card.sourceUrl]);
  return (
    <div className="rounded-xl border border-black/[0.08] bg-white px-3 py-2">
      <p className="text-[11px] text-[#6e6e73]">{evidenceSourceLabel(card)}</p>
      <p className="mt-1 text-[12px] leading-[1.45] text-[#1d1d1f]">{String(card.extract || card.title || "").replace(/\s+/g, " ").trim()}</p>
      <div className="mt-2 flex items-center gap-2">
        <button
          type="button"
          onClick={() => onOpen(card, index)}
          className="rounded-lg border border-black/[0.08] px-2 py-1 text-[10px] text-[#4c4c50] hover:bg-[#f3f4f7]"
        >
          Jump to evidence
        </button>
        {sourceUrl ? (
          <a
            href={sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-lg border border-black/[0.08] px-2 py-1 text-[10px] text-[#4c4c50] hover:bg-[#f3f4f7]"
          >
            Open source
          </a>
        ) : null}
      </div>
    </div>
  );
}

function VerificationComparePanel({ cards, onSelectCard }: VerificationComparePanelProps) {
  const [leftIndex, setLeftIndex] = useState(0);
  const [rightIndex, setRightIndex] = useState(() => (cards.length > 1 ? 1 : 0));

  const safeLeft = Math.max(0, Math.min(cards.length - 1, leftIndex));
  const safeRight = Math.max(0, Math.min(cards.length - 1, rightIndex));
  const leftCard = cards[safeLeft];
  const rightCard = cards[safeRight];
  const scoreText = useMemo(() => {
    if (!leftCard || !rightCard) {
      return "";
    }
    const leftStrength = Number(leftCard.strengthScore || 0);
    const rightStrength = Number(rightCard.strengthScore || 0);
    if (!Number.isFinite(leftStrength) || !Number.isFinite(rightStrength)) {
      return "No strength score available for comparison.";
    }
    const delta = Math.abs(leftStrength - rightStrength).toFixed(2);
    return `Strength delta: ${delta}`;
  }, [leftCard, rightCard]);

  if (!cards.length) {
    return (
      <div className="rounded-xl border border-black/[0.06] bg-white p-3 text-[12px] text-[#6e6e73]">
        No evidence available for compare mode.
      </div>
    );
  }

  return (
    <div className="space-y-2 rounded-2xl border border-[#d2d2d7] bg-white px-3 py-3 shadow-sm">
      <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Compare evidence</p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <select
          value={String(safeLeft)}
          onChange={(event) => setLeftIndex(Number(event.target.value))}
          className="rounded-lg border border-black/[0.08] bg-[#fafafc] px-2 py-1.5 text-[11px] text-[#1d1d1f]"
        >
          {cards.map((card, index) => (
            <option key={`left-${card.id}-${index}`} value={String(index)}>
              {optionLabel(card, index)}
            </option>
          ))}
        </select>
        <select
          value={String(safeRight)}
          onChange={(event) => setRightIndex(Number(event.target.value))}
          className="rounded-lg border border-black/[0.08] bg-[#fafafc] px-2 py-1.5 text-[11px] text-[#1d1d1f]"
        >
          {cards.map((card, index) => (
            <option key={`right-${card.id}-${index}`} value={String(index)}>
              {optionLabel(card, index)}
            </option>
          ))}
        </select>
      </div>
      {scoreText ? <p className="text-[11px] text-[#6e6e73]">{scoreText}</p> : null}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {leftCard ? <ComparisonCard card={leftCard} index={safeLeft} onOpen={onSelectCard} /> : null}
        {rightCard ? <ComparisonCard card={rightCard} index={safeRight} onOpen={onSelectCard} /> : null}
      </div>
    </div>
  );
}

export { VerificationComparePanel };
