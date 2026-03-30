import { ExternalLink, RefreshCcw } from "lucide-react";
import type { EvidenceCard } from "../../utils/infoInsights";
import { choosePreferredSourceUrl, evidenceSourceLabel, normalizeEvidenceId } from "./urlHelpers";

type EvidenceCardsListProps = {
  cards: EvidenceCard[];
  selectedEvidenceId?: string;
  evidenceMode?: "exact" | "context";
  maxCards?: number;
  onSelectCard: (card: EvidenceCard, index: number) => void;
  onHoverCard?: (card: EvidenceCard, index: number) => void;
};

function qualityLabel(matchQuality: string): string {
  const normalized = String(matchQuality || "").trim().toLowerCase();
  if (!normalized) {
    return "";
  }
  if (normalized === "exact") {
    return "exact match";
  }
  if (normalized === "high") {
    return "high confidence";
  }
  if (normalized === "estimated") {
    return "estimated";
  }
  return normalized;
}

function strengthLabel(tier: number | undefined): string {
  const value = Number(tier);
  if (!Number.isFinite(value) || value <= 0) {
    return "";
  }
  if (value >= 3) {
    return "strong";
  }
  if (value >= 2) {
    return "moderate";
  }
  return "weak";
}

function EvidenceCardsList({
  cards,
  selectedEvidenceId = "",
  evidenceMode = "exact",
  maxCards = 24,
  onSelectCard,
  onHoverCard,
}: EvidenceCardsListProps) {
  if (!cards.length) {
    return (
      <div className="rounded-xl border border-black/[0.06] bg-white p-3 text-[12px] text-[#6e6e73]">
        No evidence cards were extracted from this run.
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      {cards.slice(0, maxCards).map((card, index) => {
        const refLabel = String(index + 1);
        const sourceLabel = evidenceSourceLabel(card);
        const sourceUrl = choosePreferredSourceUrl([card.sourceUrl]);
        const snippet = String(card.extract || card.title || "No extract available for this citation.")
          .replace(/\s+/g, " ")
          .trim();
        const snippetLimit = evidenceMode === "exact" ? 220 : 420;
        const trimmedSnippet = snippet.length > snippetLimit ? `${snippet.slice(0, snippetLimit).trimEnd()}...` : snippet;
        const normalizedCardId = normalizeEvidenceId(card.id);
        const selected = selectedEvidenceId && selectedEvidenceId === normalizedCardId;
        const quality = qualityLabel(card.matchQuality || "");
        const strength = strengthLabel(card.strengthTier);
        return (
          <div
            key={`${card.id || `evidence-${index + 1}`}:${sourceLabel}`}
            id={normalizedCardId || undefined}
            data-evidence-card-id={normalizedCardId || undefined}
            className={`rounded-xl border bg-white px-3 py-2 transition-colors ${
              selected ? "border-[#0a84ff]/40 bg-[#f1f7ff]" : "border-black/[0.06] hover:bg-[#f8f9fc]"
            }`}
          >
            <button
              type="button"
              onClick={() => onSelectCard(card, index)}
              onMouseEnter={() => onHoverCard?.(card, index)}
              className="w-full text-left"
            >
              <div className="mb-1.5 flex items-center gap-2 text-[11px] text-[#5f6472]">
                <span className="rounded-full border border-[#ccd3e2] bg-[#f5f7fb] px-2 py-0.5 font-semibold text-[#2f3a51]">
                  [{refLabel}]
                </span>
                <span className="truncate">{sourceLabel}</span>
                {card.page ? (
                  <span className="shrink-0 rounded-full border border-black/[0.08] bg-white px-1.5 py-0.5 text-[#6e6e73]">
                    p. {card.page}
                  </span>
                ) : null}
              </div>
              <p className="text-[12px] leading-[1.45] text-[#1e2532]">
                {trimmedSnippet || "No extract available."}
              </p>
            </button>
            <div className="mt-2 flex items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
                {quality ? (
                  <span className="rounded-full border border-black/[0.08] bg-[#f5f5f7] px-2 py-0.5 text-[#4c4c50]">
                    {quality}
                  </span>
                ) : null}
                {strength ? (
                  <span className="rounded-full border border-black/[0.08] bg-[#f5f5f7] px-2 py-0.5 text-[#4c4c50]">
                    {strength}
                  </span>
                ) : null}
              </div>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => onSelectCard(card, index)}
                  className="inline-flex items-center gap-1 rounded-lg border border-black/[0.08] bg-white px-2 py-1 text-[10px] text-[#45474f] hover:bg-[#f3f4f7]"
                >
                  <RefreshCcw className="h-3 w-3" />
                  Replay
                </button>
                {sourceUrl ? (
                  <a
                    href={sourceUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-lg border border-black/[0.08] bg-white px-2 py-1 text-[10px] text-[#45474f] hover:bg-[#f3f4f7]"
                  >
                    <ExternalLink className="h-3 w-3" />
                    Open
                  </a>
                ) : null}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export { EvidenceCardsList };
