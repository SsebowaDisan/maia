import type { ChatTurn, CitationFocus, CitationHighlightBox } from "../../types";
import { parseEvidence } from "../../utils/infoInsights";
import type { EvidenceCard } from "../../utils/infoInsights";

const CITATION_ANCHOR_SELECTOR = "a.citation, a[href^='#evidence-'], a[data-file-id]";

function normalizePageLabel(...candidates: Array<string | undefined | null>): string | undefined {
  for (const candidate of candidates) {
    const raw = String(candidate || "").trim();
    if (!raw) {
      continue;
    }
    const match = raw.match(/(\d{1,4})/);
    if (match?.[1]) {
      return match[1];
    }
  }
  return undefined;
}

function normalizeCitationExtract(...candidates: Array<string | undefined | null>): string {
  const MAX_EXTRACT_CHARS = 260;
  for (const candidate of candidates) {
    const raw = String(candidate || "").replace(/\s+/g, " ").trim();
    if (!raw) {
      continue;
    }
    if (/^(?:\[\d{1,4}\]|【\d{1,4}】)$/.test(raw)) {
      continue;
    }
    if (raw.length <= MAX_EXTRACT_CHARS) {
      return raw;
    }
    const clipped = raw.slice(0, MAX_EXTRACT_CHARS);
    const sentenceCut = Math.max(clipped.lastIndexOf("."), clipped.lastIndexOf("!"), clipped.lastIndexOf("?"));
    if (sentenceCut >= 120) {
      return clipped.slice(0, sentenceCut + 1).trim();
    }
    const wordCut = clipped.lastIndexOf(" ");
    if (wordCut >= 120) {
      return clipped.slice(0, wordCut).trim();
    }
    return clipped.trim();
  }
  return "No extract available for this citation.";
}

function normalizeHighlightBox(raw: unknown): CitationHighlightBox | null {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const entry = raw as Record<string, unknown>;
  const clamp01 = (value: number) => Math.max(0, Math.min(1, value));
  const x = Number(entry.x);
  const y = Number(entry.y);
  const width = Number(entry.width);
  const height = Number(entry.height);
  if (![x, y, width, height].every((value) => Number.isFinite(value))) {
    return null;
  }
  const nx = clamp01(x);
  const ny = clamp01(y);
  const nw = Math.max(0, Math.min(1 - nx, width));
  const nh = Math.max(0, Math.min(1 - ny, height));
  if (nw < 0.002 || nh < 0.002) {
    return null;
  }
  return {
    x: Number(nx.toFixed(6)),
    y: Number(ny.toFixed(6)),
    width: Number(nw.toFixed(6)),
    height: Number(nh.toFixed(6)),
  };
}

function parseHighlightBoxes(...candidates: Array<string | undefined | null>): CitationHighlightBox[] {
  for (const candidate of candidates) {
    const raw = String(candidate || "").trim();
    if (!raw) {
      continue;
    }
    try {
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) {
        continue;
      }
      const boxes: CitationHighlightBox[] = [];
      for (const row of parsed) {
        const normalized = normalizeHighlightBox(row);
        if (!normalized) {
          continue;
        }
        boxes.push(normalized);
        if (boxes.length >= 24) {
          break;
        }
      }
      if (boxes.length) {
        return boxes;
      }
    } catch {
      // Ignore malformed payloads and continue with other candidates.
    }
  }
  return [];
}

function extractCitationClaimText(citationAnchor: HTMLAnchorElement): string {
  const claimHost =
    citationAnchor.closest("p, li, blockquote, td, th, h1, h2, h3, h4, h5, h6") ||
    citationAnchor.parentElement;
  const raw = normalizeCitationExtract(
    claimHost?.textContent || "",
    citationAnchor.textContent?.trim(),
  );
  const cleaned = raw.replace(/(?:\[\d{1,4}\]|【\d{1,4}】)/g, "").replace(/\s+/g, " ").trim();
  return cleaned.length >= 16 ? cleaned : "";
}

function resolveStrengthTier(rawTier: number | undefined, rawScore: number | undefined): number {
  const tier = Number(rawTier);
  if (Number.isFinite(tier) && tier >= 1) {
    return Math.max(1, Math.min(3, Math.round(tier)));
  }
  const score = Number(rawScore);
  if (!Number.isFinite(score) || score <= 0) {
    return 0;
  }
  if (score >= 0.7) {
    return 3;
  }
  if (score >= 0.42) {
    return 2;
  }
  return 1;
}

function extractRefNumber(value: string): number | null {
  const match = String(value || "").match(/(\d{1,4})/);
  if (!match?.[1]) {
    return null;
  }
  const parsed = Number(match[1]);
  if (!Number.isFinite(parsed) || parsed < 1) {
    return null;
  }
  return Math.round(parsed);
}

function tokenizeForMatch(value: string): Set<string> {
  const tokens = String(value || "")
    .toLowerCase()
    .match(/[a-z0-9]{3,}/g);
  return new Set(tokens || []);
}

function evidenceCardRefNumber(card: EvidenceCard): number | null {
  const fromId = extractRefNumber(String(card.id || ""));
  if (fromId) {
    return fromId;
  }
  return extractRefNumber(String(card.source || ""));
}

function bestEvidenceByText(query: string, cards: EvidenceCard[]): EvidenceCard | null {
  const queryTokens = tokenizeForMatch(query);
  if (!queryTokens.size || !cards.length) {
    return null;
  }
  let best: EvidenceCard | null = null;
  let bestScore = 0;
  for (const card of cards) {
    const cardTokens = tokenizeForMatch(
      [card.extract || "", card.source || "", card.page || ""].join(" "),
    );
    if (!cardTokens.size) {
      continue;
    }
    let overlap = 0;
    for (const token of queryTokens) {
      if (cardTokens.has(token)) {
        overlap += 1;
      }
    }
    if (!overlap) {
      continue;
    }
    const score = overlap / Math.max(queryTokens.size, cardTokens.size);
    if (score > bestScore) {
      best = card;
      bestScore = score;
    }
  }
  return best;
}

function parseEvidenceRefId(citationAnchor: HTMLAnchorElement): string {
  const evidenceIdAttr = (citationAnchor.getAttribute("data-evidence-id") || "").trim();
  const evidenceIdAttrMatch = evidenceIdAttr.match(/(evidence-\d{1,4})/i);
  if (evidenceIdAttrMatch?.[1]) {
    return evidenceIdAttrMatch[1].toLowerCase();
  }
  const href = citationAnchor.getAttribute("href") || "";
  const hrefMatch = href.match(/#(evidence-\d{1,4})/i);
  if (hrefMatch?.[1]) {
    return hrefMatch[1].toLowerCase();
  }
  const ariaControls = (citationAnchor.getAttribute("aria-controls") || "").trim();
  const controlsMatch = ariaControls.match(/(evidence-\d{1,4})/i);
  if (controlsMatch?.[1]) {
    return controlsMatch[1].toLowerCase();
  }
  const idValue = (citationAnchor.getAttribute("id") || "").trim();
  const idMatch = idValue.match(/(?:citation|mark)-(\d{1,4})/i);
  if (idMatch?.[1]) {
    return `evidence-${idMatch[1]}`;
  }
  const citationNumberAttr = (citationAnchor.getAttribute("data-citation-number") || "").trim();
  if (/^\d{1,4}$/.test(citationNumberAttr)) {
    return `evidence-${citationNumberAttr}`;
  }
  const labelMatch = String(citationAnchor.textContent || "").match(/(\d{1,4})/);
  if (labelMatch?.[1]) {
    return `evidence-${labelMatch[1]}`;
  }
  return "";
}

type ResolvedCitationFocus = {
  focus: CitationFocus;
  strengthTierResolved: number;
  evidenceCards: EvidenceCard[];
  matchedEvidence: EvidenceCard | null;
};

function resolveCitationFocusFromAnchor(params: {
  turn: ChatTurn;
  citationAnchor: HTMLAnchorElement;
  evidenceCards?: EvidenceCard[];
}): ResolvedCitationFocus {
  const { turn, citationAnchor } = params;
  const evidenceCards = params.evidenceCards || parseEvidence(turn.info || "");
  const fileIdAttr = citationAnchor.getAttribute("data-file-id") || "";
  const pageAttr = citationAnchor.getAttribute("data-page") || "";
  const phraseAttr =
    citationAnchor.getAttribute("data-phrase") ||
    citationAnchor.getAttribute("data-search") ||
    "";
  const boxesAttr =
    citationAnchor.getAttribute("data-boxes") ||
    citationAnchor.getAttribute("data-bboxes") ||
    "";
  const strengthAttr = Number(citationAnchor.getAttribute("data-strength") || "");
  const strengthTierAttr = Number(citationAnchor.getAttribute("data-strength-tier") || "");
  const matchQualityAttr = (citationAnchor.getAttribute("data-match-quality") || "").trim();
  const unitIdAttr = (citationAnchor.getAttribute("data-unit-id") || "").trim();
  const charStartAttr = Number(citationAnchor.getAttribute("data-char-start") || "");
  const charEndAttr = Number(citationAnchor.getAttribute("data-char-end") || "");
  const evidenceId = parseEvidenceRefId(citationAnchor);
  const expectedRefNumber = extractRefNumber(evidenceId);
  let matchedEvidence = evidenceId
    ? evidenceCards.find((card) => String(card.id || "").toLowerCase() === evidenceId) || null
    : null;
  if (!matchedEvidence && expectedRefNumber) {
    matchedEvidence =
      evidenceCards.find((card) => evidenceCardRefNumber(card) === expectedRefNumber) ||
      (expectedRefNumber >= 1 && expectedRefNumber <= evidenceCards.length
        ? evidenceCards[expectedRefNumber - 1] || null
        : null);
  }
  if (!matchedEvidence && phraseAttr) {
    matchedEvidence = bestEvidenceByText(phraseAttr, evidenceCards);
  }
  if (!matchedEvidence && pageAttr) {
    matchedEvidence =
      evidenceCards.find((card) => normalizePageLabel(card.page) === normalizePageLabel(pageAttr)) ||
      null;
  }
  if (!matchedEvidence && fileIdAttr) {
    matchedEvidence = evidenceCards.find((card) => String(card.fileId || "") === fileIdAttr) || null;
  }
  const fallbackEvidence =
    matchedEvidence ||
    evidenceCards.find((card) => Boolean(card.fileId)) ||
    evidenceCards[0] ||
    null;
  const attachmentFileId =
    (turn.attachments || []).find((attachment) => Boolean(attachment.fileId))?.fileId || "";
  const sourceName = (matchedEvidence?.source || fallbackEvidence?.source || "Indexed source")
    .replace(/^\[\d+\]\s*/, "")
    .trim();

  const highlightBoxes = parseHighlightBoxes(
    boxesAttr,
    JSON.stringify(matchedEvidence?.highlightBoxes || []),
  );

  const strengthScore = Number.isFinite(strengthAttr)
    ? strengthAttr
    : matchedEvidence?.strengthScore;
  const strengthTier = Number.isFinite(strengthTierAttr)
    ? strengthTierAttr
    : matchedEvidence?.strengthTier;

  const focus: CitationFocus = {
    fileId: fileIdAttr || matchedEvidence?.fileId || fallbackEvidence?.fileId || attachmentFileId,
    sourceName: sourceName || "Indexed source",
    page: normalizePageLabel(pageAttr, matchedEvidence?.page, fallbackEvidence?.page),
    extract: normalizeCitationExtract(
      phraseAttr,
      matchedEvidence?.extract,
      fallbackEvidence?.extract,
      citationAnchor.textContent?.trim(),
    ),
    claimText: extractCitationClaimText(citationAnchor) || undefined,
    evidenceId: evidenceId || undefined,
    highlightBoxes: highlightBoxes.length ? highlightBoxes : undefined,
    strengthScore,
    strengthTier,
    matchQuality: matchQualityAttr || matchedEvidence?.matchQuality,
    unitId: unitIdAttr || matchedEvidence?.unitId,
    charStart: Number.isFinite(charStartAttr) ? charStartAttr : matchedEvidence?.charStart,
    charEnd: Number.isFinite(charEndAttr) ? charEndAttr : matchedEvidence?.charEnd,
  };

  return {
    focus,
    strengthTierResolved: resolveStrengthTier(focus.strengthTier, focus.strengthScore),
    evidenceCards,
    matchedEvidence,
  };
}

export {
  CITATION_ANCHOR_SELECTOR,
  normalizeCitationExtract,
  parseEvidenceRefId,
  resolveCitationFocusFromAnchor,
  resolveStrengthTier,
};
export type { ResolvedCitationFocus };
