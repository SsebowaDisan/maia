import type { EvidenceCard } from "../../utils/infoInsights";
import { evidenceSourceLabel } from "./urlHelpers";

type VerificationTrailPanelProps = {
  cards: EvidenceCard[];
  onSelectCard: (card: EvidenceCard, index: number) => void;
};

function VerificationTrailPanel({ cards, onSelectCard }: VerificationTrailPanelProps) {
  if (!cards.length) {
    return (
      <div className="rounded-xl border border-black/[0.06] bg-white p-3 text-[12px] text-[#6e6e73]">
        Evidence trail is empty for this response.
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-[#d2d2d7] bg-white px-3 py-3 shadow-sm">
      <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Evidence trail</p>
      <div className="mt-2 space-y-2">
        {cards.slice(0, 16).map((card, index) => (
          <button
            key={`${card.id}-${index}`}
            type="button"
            onClick={() => onSelectCard(card, index)}
            className="flex w-full items-start gap-2 rounded-lg border border-black/[0.08] px-2.5 py-2 text-left hover:bg-[#f7f8fc]"
          >
            <span className="mt-0.5 inline-flex h-5 min-w-[20px] items-center justify-center rounded-full border border-black/[0.1] bg-[#f5f5f7] text-[10px] text-[#4c4c50]">
              {index + 1}
            </span>
            <div className="min-w-0">
              <p className="truncate text-[12px] text-[#1d1d1f]">{evidenceSourceLabel(card)}</p>
              <p className="truncate text-[11px] text-[#6e6e73]">{String(card.extract || card.title || "").replace(/\s+/g, " ").trim()}</p>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

export { VerificationTrailPanel };
