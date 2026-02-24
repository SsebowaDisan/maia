export type EvidenceCard = {
  id: string;
  title: string;
  source: string;
  page?: string;
  fileId?: string;
  extract: string;
  imageSrc?: string;
};

export type ClaimStatus = "supported" | "weak" | "missing";

export type ClaimInsight = {
  id: string;
  text: string;
  status: ClaimStatus;
  matchedEvidenceIds: string[];
  score: number;
};

export type SourceGraphNode = {
  id: string;
  kind: "claim" | "source";
  label: string;
  status?: ClaimStatus;
  score?: number;
  evidenceCount?: number;
};

export type SourceGraphEdge = {
  id: string;
  claimId: string;
  sourceId: string;
  weight: number;
  evidenceIds: string[];
};

export type SourceGraph = {
  claimNodes: SourceGraphNode[];
  sourceNodes: SourceGraphNode[];
  edges: SourceGraphEdge[];
  orphanClaimIds: string[];
};

export type ContradictionSeverity = "high" | "medium" | "low";

export type ContradictionFinding = {
  id: string;
  severity: ContradictionSeverity;
  summary: string;
  detail: string;
  confidence: number;
  claimId?: string;
  evidenceId?: string;
  source?: string;
  relatedClaimId?: string;
};

const STOPWORDS = new Set([
  "about",
  "after",
  "also",
  "among",
  "and",
  "are",
  "been",
  "being",
  "between",
  "both",
  "but",
  "can",
  "does",
  "each",
  "from",
  "have",
  "into",
  "its",
  "more",
  "most",
  "much",
  "other",
  "over",
  "that",
  "their",
  "them",
  "then",
  "there",
  "these",
  "they",
  "this",
  "those",
  "under",
  "very",
  "what",
  "when",
  "where",
  "which",
  "while",
  "with",
  "would",
  "your",
]);

const NEGATION_TERMS = new Set([
  "absent",
  "cannot",
  "cant",
  "decline",
  "decrease",
  "failed",
  "false",
  "lack",
  "missing",
  "never",
  "no",
  "none",
  "not",
  "without",
  "wont",
]);

const POSITIVE_TERMS = new Set([
  "available",
  "complete",
  "completed",
  "contains",
  "exists",
  "has",
  "include",
  "included",
  "includes",
  "present",
  "provided",
  "ready",
  "success",
  "successful",
  "true",
  "with",
]);

const OPPOSITE_TERM_PAIRS: Array<[string, string]> = [
  ["increase", "decrease"],
  ["high", "low"],
  ["success", "failure"],
  ["with", "without"],
  ["include", "exclude"],
  ["available", "missing"],
  ["present", "absent"],
  ["completed", "pending"],
];

const SEVERITY_RANK: Record<ContradictionSeverity, number> = {
  high: 3,
  medium: 2,
  low: 1,
};

type NumericFact = {
  value: number;
  unit: string;
  raw: string;
};

function normalizeText(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

function plainText(input: string): string {
  if (!input.trim()) {
    return "";
  }
  const hasHtmlTags = /<[a-z][\s\S]*>/i.test(input);
  if (!hasHtmlTags) {
    return normalizeText(input);
  }
  const doc = new DOMParser().parseFromString(input, "text/html");
  return normalizeText(doc.body.textContent || "");
}

function tokenize(text: string): string[] {
  return Array.from(
    new Set(
      text
        .toLowerCase()
        .split(/[^a-z0-9]+/i)
        .filter((token) => token.length > 2 && !STOPWORDS.has(token)),
    ),
  );
}

function compactLabel(text: string, maxLength: number): string {
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, Math.max(0, maxLength - 1)).trimEnd()}...`;
}

function cleanSourceLabel(source: string): string {
  const normalized = normalizeText(source).replace(/^\[\d+\]\s*/, "");
  if (!normalized) {
    return "Indexed source";
  }
  return compactLabel(normalized, 44);
}

function normalizeUnit(unit: string): string {
  const normalized = unit.toLowerCase().trim();
  if (!normalized) {
    return "";
  }
  if (normalized === "percent") {
    return "%";
  }
  if (normalized === "dollar" || normalized === "dollars") {
    return "usd";
  }
  if (normalized === "day" || normalized === "days") {
    return "day";
  }
  if (normalized === "hour" || normalized === "hours") {
    return "hour";
  }
  if (normalized === "year" || normalized === "years") {
    return "year";
  }
  if (normalized === "month" || normalized === "months") {
    return "month";
  }
  if (normalized === "week" || normalized === "weeks") {
    return "week";
  }
  return normalized;
}

function extractNumericFacts(text: string): NumericFact[] {
  const found: NumericFact[] = [];
  const pattern =
    /(-?\d{1,3}(?:,\d{3})*(?:\.\d+)?|-?\d+(?:\.\d+)?)(?:\s?(%|percent|usd|eur|ugx|dollars?|days?|hours?|years?|months?|weeks?|kg|g|km|m|cm|mm))?/gi;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    const rawNumber = (match[1] || "").replace(/,/g, "");
    const parsed = Number(rawNumber);
    if (!Number.isFinite(parsed)) {
      continue;
    }
    found.push({
      value: parsed,
      unit: normalizeUnit(match[2] || ""),
      raw: normalizeText(match[0] || rawNumber),
    });
    if (found.length >= 10) {
      break;
    }
  }
  return found;
}

function overlapScore(tokensA: string[], tokensB: string[]): number {
  if (!tokensA.length || !tokensB.length) {
    return 0;
  }
  const setB = new Set(tokensB);
  let shared = 0;
  for (const token of tokensA) {
    if (setB.has(token)) {
      shared += 1;
    }
  }
  return shared / tokensA.length;
}

function detectPolarity(tokens: string[]): "positive" | "negative" | "neutral" {
  const hasNegation = tokens.some((token) => NEGATION_TERMS.has(token));
  const hasPositive = tokens.some((token) => POSITIVE_TERMS.has(token));
  if (hasNegation && !hasPositive) {
    return "negative";
  }
  if (hasPositive && !hasNegation) {
    return "positive";
  }
  return "neutral";
}

function findOppositeTerms(tokensA: string[], tokensB: string[]): [string, string] | null {
  const setA = new Set(tokensA);
  const setB = new Set(tokensB);
  for (const [left, right] of OPPOSITE_TERM_PAIRS) {
    if ((setA.has(left) && setB.has(right)) || (setA.has(right) && setB.has(left))) {
      return [left, right];
    }
  }
  return null;
}

function findNumericConflict(
  first: NumericFact[],
  second: NumericFact[],
): { first: NumericFact; second: NumericFact; delta: number } | null {
  let strongest: { first: NumericFact; second: NumericFact; delta: number } | null = null;

  for (const left of first) {
    for (const right of second) {
      const compatibleUnit = left.unit === right.unit || !left.unit || !right.unit;
      if (!compatibleUnit) {
        continue;
      }
      const baseline = Math.max(Math.abs(left.value), Math.abs(right.value), 1);
      const relativeDelta = Math.abs(left.value - right.value) / baseline;
      if (relativeDelta < 0.25) {
        continue;
      }
      if (!strongest || relativeDelta > strongest.delta) {
        strongest = { first: left, second: right, delta: relativeDelta };
      }
    }
  }

  return strongest;
}

export function parseEvidence(infoHtml: string): EvidenceCard[] {
  if (!infoHtml.trim()) {
    return [];
  }

  const doc = new DOMParser().parseFromString(infoHtml, "text/html");
  const detailsNodes = Array.from(doc.querySelectorAll("details.evidence"));
  if (!detailsNodes.length) {
    const fallback = plainText(infoHtml);
    return fallback
        ? [
          {
            id: "evidence-1",
            title: "Evidence",
            source: "Indexed context",
            extract: fallback,
          },
        ]
      : [];
  }

  return detailsNodes.map((details, index) => {
    const detailsId = (details.getAttribute("id") || "").trim();
    const summary = normalizeText(
      details.querySelector("summary")?.textContent || `Evidence ${index + 1}`,
    );

    let source = "";
    let extract = "";
    const divs = Array.from(details.querySelectorAll("div"));
    for (const div of divs) {
      const text = normalizeText(div.textContent || "");
      if (!source && /^source\s*:/i.test(text)) {
        source = text.replace(/^source\s*:/i, "").trim();
      }
      if (!extract && /^extract\s*:/i.test(text)) {
        extract = text.replace(/^extract\s*:/i, "").trim();
      }
    }

    if (!extract) {
      const evidenceContent = details.querySelector(".evidence-content");
      extract = normalizeText(evidenceContent?.textContent || "");
    }
    if (!extract) {
      extract = normalizeText(details.textContent || "");
    }
    if (!source) {
      source = "Indexed source";
    }

    const imageSrc = details.querySelector("img")?.getAttribute("src") || undefined;
    const pageMatch = summary.match(/page\s+(\d+)/i);
    const fileId = (details.getAttribute("data-file-id") || "").trim() || undefined;

    return {
      id: detailsId || `evidence-${index + 1}`,
      title: summary,
      source,
      page: pageMatch?.[1],
      fileId,
      extract,
      imageSrc,
    };
  });
}

export function extractClaims(answerText: string): string[] {
  const normalized = plainText(answerText)
    .replace(/\[[0-9]{1,3}\]/g, "")
    .replace(/\bEvidence:\s*/gi, "")
    .replace(/(^|\n)\s*#{1,6}\s*/g, "$1")
    .replace(/\*\*/g, "")
    .replace(/\s+-\s+/g, ". ");
  if (!normalized) {
    return [];
  }

  const rawLines = normalized
    .split(/\n+/)
    .map((line) => normalizeText(line))
    .filter(Boolean);

  const lineClaims = rawLines
    .flatMap((line) => line.split(/(?<=[.!?])\s+/))
    .map((segment) => normalizeText(segment))
    .filter((segment) => segment.length > 20);

  const unique: string[] = [];
  for (const claim of lineClaims) {
    if (unique.some((existing) => existing.toLowerCase() === claim.toLowerCase())) {
      continue;
    }
    unique.push(claim);
    if (unique.length >= 8) {
      break;
    }
  }

  return unique;
}

export function buildClaimInsights(
  claims: string[],
  evidenceCards: EvidenceCard[],
): ClaimInsight[] {
  if (!claims.length) {
    return [];
  }

  const evidenceIndex = evidenceCards.map((card) => ({
    id: card.id,
    source: card.source,
    tokens: tokenize(`${card.source} ${card.extract}`),
  }));

  return claims.map((claim, index) => {
    const claimTokens = tokenize(claim);
    if (!claimTokens.length || !evidenceIndex.length) {
      return {
        id: `claim-${index}`,
        text: claim,
        status: "missing",
        matchedEvidenceIds: [],
        score: 0,
      };
    }

    const matches = evidenceIndex.map((evidence) => {
      let hitCount = 0;
      for (const token of claimTokens) {
        if (evidence.tokens.includes(token)) {
          hitCount += 1;
        }
      }
      const score = hitCount / claimTokens.length;
      return { id: evidence.id, score };
    });

    matches.sort((a, b) => b.score - a.score);
    const bestScore = matches[0]?.score || 0;
    const matchedEvidenceIds = matches
      .filter((item) => item.score >= 0.18)
      .slice(0, 3)
      .map((item) => item.id);

    let status: ClaimStatus = "missing";
    if (bestScore >= 0.35) {
      status = "supported";
    } else if (bestScore >= 0.18) {
      status = "weak";
    }

    return {
      id: `claim-${index}`,
      text: claim,
      status,
      matchedEvidenceIds,
      score: bestScore,
    };
  });
}

export function supportRate(claims: ClaimInsight[]): number {
  if (!claims.length) {
    return 0;
  }
  const supported = claims.filter((claim) => claim.status === "supported").length;
  return Math.round((supported / claims.length) * 100);
}

export function buildSourceGraph(
  claimInsights: ClaimInsight[],
  evidenceCards: EvidenceCard[],
): SourceGraph {
  const evidenceById = new Map(evidenceCards.map((card) => [card.id, card]));
  const sourceMap = new Map<
    string,
    {
      id: string;
      label: string;
      evidenceIds: Set<string>;
    }
  >();
  const edges = new Map<string, SourceGraphEdge>();
  const orphanClaimIds: string[] = [];

  for (const card of evidenceCards) {
    const key = cleanSourceLabel(card.source).toLowerCase();
    if (!sourceMap.has(key)) {
      sourceMap.set(key, {
        id: `source-${sourceMap.size + 1}`,
        label: cleanSourceLabel(card.source),
        evidenceIds: new Set(),
      });
    }
    sourceMap.get(key)?.evidenceIds.add(card.id);
  }

  for (const claim of claimInsights) {
    const matched = claim.matchedEvidenceIds
      .map((id) => evidenceById.get(id))
      .filter((item): item is EvidenceCard => Boolean(item));
    if (!matched.length) {
      orphanClaimIds.push(claim.id);
      continue;
    }

    const sourceHits = new Map<string, { sourceId: string; evidenceIds: Set<string>; count: number }>();
    for (const card of matched) {
      const key = cleanSourceLabel(card.source).toLowerCase();
      let sourceEntry = sourceMap.get(key);
      if (!sourceEntry) {
        sourceEntry = {
          id: `source-${sourceMap.size + 1}`,
          label: cleanSourceLabel(card.source),
          evidenceIds: new Set(),
        };
        sourceMap.set(key, sourceEntry);
      }
      sourceEntry.evidenceIds.add(card.id);
      const hit = sourceHits.get(key);
      if (hit) {
        hit.count += 1;
        hit.evidenceIds.add(card.id);
      } else {
        sourceHits.set(key, {
          sourceId: sourceEntry.id,
          count: 1,
          evidenceIds: new Set([card.id]),
        });
      }
    }

    for (const hit of sourceHits.values()) {
      const edgeId = `${claim.id}::${hit.sourceId}`;
      edges.set(edgeId, {
        id: edgeId,
        claimId: claim.id,
        sourceId: hit.sourceId,
        weight: Math.min(1, 0.25 + claim.score * 0.5 + hit.count * 0.15),
        evidenceIds: Array.from(hit.evidenceIds),
      });
    }
  }

  return {
    claimNodes: claimInsights.map((claim) => ({
      id: claim.id,
      kind: "claim",
      label: compactLabel(claim.text, 68),
      status: claim.status,
      score: claim.score,
    })),
    sourceNodes: Array.from(sourceMap.values()).map((source) => ({
      id: source.id,
      kind: "source",
      label: source.label,
      evidenceCount: source.evidenceIds.size,
    })),
    edges: Array.from(edges.values()),
    orphanClaimIds,
  };
}

export function detectContradictions(
  claimInsights: ClaimInsight[],
  evidenceCards: EvidenceCard[],
): ContradictionFinding[] {
  if (!claimInsights.length || !evidenceCards.length) {
    return [];
  }

  const evidenceById = new Map(evidenceCards.map((card) => [card.id, card]));
  const findings = new Map<string, ContradictionFinding>();

  const addFinding = (finding: ContradictionFinding) => {
    const existing = findings.get(finding.id);
    if (!existing || finding.confidence > existing.confidence) {
      findings.set(finding.id, finding);
    }
  };

  for (const claim of claimInsights) {
    if (!claim.matchedEvidenceIds.length) {
      continue;
    }

    const claimTokens = tokenize(claim.text);
    const claimNumbers = extractNumericFacts(claim.text);
    const claimPolarity = detectPolarity(claimTokens);

    for (const evidenceId of claim.matchedEvidenceIds) {
      const evidence = evidenceById.get(evidenceId);
      if (!evidence) {
        continue;
      }

      const evidenceText = `${evidence.source} ${evidence.extract}`;
      const evidenceTokens = tokenize(evidenceText);
      const evidenceNumbers = extractNumericFacts(evidenceText);
      const evidencePolarity = detectPolarity(evidenceTokens);
      const overlap = overlapScore(claimTokens, evidenceTokens);
      if (overlap < 0.16) {
        continue;
      }

      const numericConflict = findNumericConflict(claimNumbers, evidenceNumbers);
      if (numericConflict) {
        const confidence = Math.min(
          0.98,
          0.55 + overlap * 0.25 + Math.min(0.2, numericConflict.delta),
        );
        addFinding({
          id: `num:${claim.id}:${evidence.id}:${numericConflict.first.raw}:${numericConflict.second.raw}`,
          severity: "high",
          summary: "Numeric mismatch between answer and retrieved source",
          detail: `Claim references ${numericConflict.first.raw}, while source evidence shows ${numericConflict.second.raw}.`,
          confidence,
          claimId: claim.id,
          evidenceId: evidence.id,
          source: evidence.source,
        });
      }

      const polarityConflict =
        (claimPolarity === "positive" && evidencePolarity === "negative") ||
        (claimPolarity === "negative" && evidencePolarity === "positive");
      if (polarityConflict) {
        const confidence = Math.min(0.9, 0.45 + overlap * 0.3);
        addFinding({
          id: `polarity:${claim.id}:${evidence.id}`,
          severity: "medium",
          summary: "Polarity conflict with source evidence",
          detail:
            "Answer statement leans opposite of the retrieved source (affirmation vs negation).",
          confidence,
          claimId: claim.id,
          evidenceId: evidence.id,
          source: evidence.source,
        });
      }

      const oppositeTerms = findOppositeTerms(claimTokens, evidenceTokens);
      if (oppositeTerms) {
        const confidence = Math.min(0.85, 0.4 + overlap * 0.3);
        addFinding({
          id: `terms:${claim.id}:${evidence.id}:${oppositeTerms[0]}:${oppositeTerms[1]}`,
          severity: "medium",
          summary: "Opposing terminology detected",
          detail: `The answer and evidence use opposite terms (${oppositeTerms[0]} vs ${oppositeTerms[1]}).`,
          confidence,
          claimId: claim.id,
          evidenceId: evidence.id,
          source: evidence.source,
        });
      }
    }
  }

  for (let i = 0; i < claimInsights.length; i += 1) {
    const claimA = claimInsights[i];
    const tokensA = tokenize(claimA.text);
    const numbersA = extractNumericFacts(claimA.text);
    for (let j = i + 1; j < claimInsights.length; j += 1) {
      const claimB = claimInsights[j];
      const tokensB = tokenize(claimB.text);
      const overlap = overlapScore(tokensA, tokensB);
      if (overlap < 0.32) {
        continue;
      }

      const numericConflict = findNumericConflict(numbersA, extractNumericFacts(claimB.text));
      if (numericConflict) {
        addFinding({
          id: `claim-num:${claimA.id}:${claimB.id}:${numericConflict.first.raw}:${numericConflict.second.raw}`,
          severity: "medium",
          summary: "Two answer claims disagree on numbers",
          detail: `Related claims mention different values (${numericConflict.first.raw} vs ${numericConflict.second.raw}).`,
          confidence: Math.min(0.85, 0.5 + overlap * 0.25),
          claimId: claimA.id,
          relatedClaimId: claimB.id,
        });
      }

      const oppositeTerms = findOppositeTerms(tokensA, tokensB);
      if (oppositeTerms) {
        addFinding({
          id: `claim-terms:${claimA.id}:${claimB.id}:${oppositeTerms[0]}:${oppositeTerms[1]}`,
          severity: "low",
          summary: "Potential claim-to-claim contradiction",
          detail: `Two related claims use opposite language (${oppositeTerms[0]} vs ${oppositeTerms[1]}).`,
          confidence: Math.min(0.75, 0.35 + overlap * 0.25),
          claimId: claimA.id,
          relatedClaimId: claimB.id,
        });
      }
    }
  }

  return Array.from(findings.values())
    .sort((a, b) => {
      const severityDiff = SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity];
      if (severityDiff !== 0) {
        return severityDiff;
      }
      return b.confidence - a.confidence;
    })
    .slice(0, 12);
}
