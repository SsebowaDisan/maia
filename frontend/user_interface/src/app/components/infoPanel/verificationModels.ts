import type { AgentSourceRecord, CitationFocus, SourceUsageRecord } from "../../types";
import type { EvidenceCard } from "../../utils/infoInsights";
import { normalizeHttpUrl } from "./urlHelpers";

export type VerificationSourceKind = "pdf" | "web" | "image" | "other";
export type VerificationSourceStatus = "loading" | "ready" | "evidence_found";

export type VerificationSourceItem = {
  id: string;
  title: string;
  kind: VerificationSourceKind;
  status: VerificationSourceStatus;
  url?: string;
  fileId?: string;
  evidenceCount: number;
  citedCount: number;
  maxStrengthScore: number;
};

export type EvidenceQualitySummary = {
  level: "low" | "medium" | "high";
  score: number;
  warning: string;
};

function normalizeLabel(value: unknown, fallback: string): string {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text || fallback;
}

function normalizeSourceId(raw: string): string {
  return raw.trim().toLowerCase();
}

function sourceKindFromHints(params: {
  sourceType?: string;
  label?: string;
  url?: string;
}): VerificationSourceKind {
  const sourceType = String(params.sourceType || "").trim().toLowerCase();
  const label = String(params.label || "").trim().toLowerCase();
  const url = String(params.url || "").trim().toLowerCase();
  if (sourceType.includes("web") || sourceType.includes("url") || sourceType.includes("site")) {
    return "web";
  }
  if (sourceType.includes("pdf")) {
    return "pdf";
  }
  if (sourceType.includes("image")) {
    return "image";
  }
  if (label.endsWith(".pdf") || url.endsWith(".pdf")) {
    return "pdf";
  }
  if (/\.(png|jpg|jpeg|webp|gif|svg)(\?|$)/i.test(label) || /\.(png|jpg|jpeg|webp|gif|svg)(\?|$)/i.test(url)) {
    return "image";
  }
  if (url.startsWith("http://") || url.startsWith("https://")) {
    return "web";
  }
  return "other";
}

function sourceIdFromEvidenceCard(card: EvidenceCard): string {
  const fileId = String(card.fileId || "").trim();
  if (fileId) {
    return normalizeSourceId(`file:${fileId}`);
  }
  const sourceUrl = normalizeHttpUrl(card.sourceUrl);
  if (sourceUrl) {
    return normalizeSourceId(`url:${sourceUrl}`);
  }
  return normalizeSourceId(`label:${normalizeLabel(card.source, "indexed source")}`);
}

function sourceIdFromSourceRecord(source: AgentSourceRecord): string {
  const fileId = String(source.file_id || "").trim();
  if (fileId) {
    return normalizeSourceId(`file:${fileId}`);
  }
  const sourceUrl = normalizeHttpUrl(source.url);
  if (sourceUrl) {
    return normalizeSourceId(`url:${sourceUrl}`);
  }
  return normalizeSourceId(`label:${normalizeLabel(source.label, "indexed source")}`);
}

function sourceIdFromCitationFocus(citation: CitationFocus | null): string {
  if (!citation) {
    return "";
  }
  const fileId = String(citation.fileId || "").trim();
  if (fileId) {
    return normalizeSourceId(`file:${fileId}`);
  }
  const sourceUrl = normalizeHttpUrl(citation.sourceUrl);
  if (sourceUrl) {
    return normalizeSourceId(`url:${sourceUrl}`);
  }
  return normalizeSourceId(`label:${normalizeLabel(citation.sourceName, "indexed source")}`);
}

function evidenceQualityWeight(card: EvidenceCard): number {
  const tier = Number(card.strengthTier || 0);
  const score = Number(card.strengthScore || 0);
  const confidence = Number(card.confidence || 0);
  const quality = String(card.matchQuality || "").trim().toLowerCase();

  const tierValue = Number.isFinite(tier) && tier > 0 ? Math.min(1, tier / 3) : 0.45;
  const scoreValue = Number.isFinite(score) && score > 0 ? Math.min(1, score) : 0.45;
  const confidenceValue = Number.isFinite(confidence) && confidence > 0 ? Math.min(1, confidence) : 0.5;
  const qualityValue =
    quality === "exact" ? 1 : quality === "high" ? 0.88 : quality === "estimated" ? 0.65 : 0.5;

  return tierValue * 0.35 + scoreValue * 0.35 + confidenceValue * 0.15 + qualityValue * 0.15;
}

function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .map((token) => token.trim())
    .filter((token) => token.length >= 3)
    .map((token) => token.replace(/(ing|ed|es|s|ly|ment|tion)$/i, ""))
    .filter((token) => token.length >= 3);
}

function semanticScore(card: EvidenceCard, query: string): number {
  const q = String(query || "").trim();
  if (!q) {
    return 1;
  }
  const normalizedQuery = q.toLowerCase();
  const haystack = `${card.title} ${card.source} ${card.extract}`.toLowerCase();
  const exactBoost = haystack.includes(normalizedQuery) ? 0.45 : 0;
  const queryTokens = tokenize(normalizedQuery);
  if (!queryTokens.length) {
    return exactBoost;
  }
  const cardTokens = new Set(tokenize(haystack));
  let hits = 0;
  for (const token of queryTokens) {
    if (cardTokens.has(token)) {
      hits += 1;
      continue;
    }
    for (const candidate of cardTokens) {
      if (candidate.includes(token) || token.includes(candidate)) {
        hits += 0.6;
        break;
      }
    }
  }
  const ratio = hits / queryTokens.length;
  return Math.max(exactBoost, Math.min(1, ratio));
}

export function buildVerificationSources(params: {
  evidenceCards: EvidenceCard[];
  sourcesUsed: AgentSourceRecord[];
  sourceUsage: SourceUsageRecord[];
}): {
  sources: VerificationSourceItem[];
  evidenceBySource: Record<string, EvidenceCard[]>;
} {
  const sourceMap = new Map<string, VerificationSourceItem>();
  const evidenceBySource = new Map<string, EvidenceCard[]>();

  for (const card of params.evidenceCards) {
    const sourceId = sourceIdFromEvidenceCard(card);
    const list = evidenceBySource.get(sourceId) || [];
    list.push(card);
    evidenceBySource.set(sourceId, list);

    const existing = sourceMap.get(sourceId);
    const url = normalizeHttpUrl(card.sourceUrl);
    const kind = sourceKindFromHints({ sourceType: card.sourceType, label: card.source, url });
    const strength = Number(card.strengthScore || 0);
    if (!existing) {
      sourceMap.set(sourceId, {
        id: sourceId,
        title: normalizeLabel(card.source, "Indexed source"),
        kind,
        status: "evidence_found",
        url: url || undefined,
        fileId: String(card.fileId || "").trim() || undefined,
        evidenceCount: 1,
        citedCount: 1,
        maxStrengthScore: Number.isFinite(strength) ? Math.max(0, strength) : 0,
      });
      continue;
    }
    existing.evidenceCount += 1;
    existing.citedCount += 1;
    existing.maxStrengthScore = Math.max(existing.maxStrengthScore, Number.isFinite(strength) ? Math.max(0, strength) : 0);
  }

  for (const source of params.sourcesUsed) {
    const sourceId = sourceIdFromSourceRecord(source);
    const existing = sourceMap.get(sourceId);
    const url = normalizeHttpUrl(source.url);
    const kind = sourceKindFromHints({
      sourceType: source.source_type,
      label: source.label,
      url,
    });
    if (!existing) {
      sourceMap.set(sourceId, {
        id: sourceId,
        title: normalizeLabel(source.label, "Indexed source"),
        kind,
        status: "ready",
        url: url || undefined,
        fileId: String(source.file_id || "").trim() || undefined,
        evidenceCount: 0,
        citedCount: 0,
        maxStrengthScore: 0,
      });
    }
  }

  for (const row of params.sourceUsage) {
    const sourceId = normalizeSourceId(`label:${normalizeLabel(row.source_name, row.source_id || "indexed source")}`);
    const existing = sourceMap.get(sourceId);
    if (!existing) {
      sourceMap.set(sourceId, {
        id: sourceId,
        title: normalizeLabel(row.source_name, "Indexed source"),
        kind: sourceKindFromHints({ sourceType: row.source_type }),
        status: row.cited_count > 0 ? "evidence_found" : "ready",
        evidenceCount: row.cited_count,
        citedCount: row.cited_count,
        maxStrengthScore: Number.isFinite(row.max_strength_score) ? Math.max(0, row.max_strength_score) : 0,
      });
      continue;
    }
    existing.citedCount = Math.max(existing.citedCount, Math.max(0, Number(row.cited_count || 0)));
    existing.maxStrengthScore = Math.max(existing.maxStrengthScore, Number.isFinite(row.max_strength_score) ? Math.max(0, row.max_strength_score) : 0);
    existing.status = existing.citedCount > 0 || existing.evidenceCount > 0 ? "evidence_found" : "ready";
  }

  const sources = Array.from(sourceMap.values()).sort((left, right) => {
    if (right.evidenceCount !== left.evidenceCount) {
      return right.evidenceCount - left.evidenceCount;
    }
    if (right.citedCount !== left.citedCount) {
      return right.citedCount - left.citedCount;
    }
    return left.title.localeCompare(right.title);
  });

  const grouped: Record<string, EvidenceCard[]> = {};
  for (const source of sources) {
    grouped[source.id] = evidenceBySource.get(source.id) || [];
  }
  return {
    sources,
    evidenceBySource: grouped,
  };
}

export function inferPreferredSourceId(params: {
  citationFocus: CitationFocus | null;
  sources: VerificationSourceItem[];
  fallback?: string;
}): string {
  const fromFocus = sourceIdFromCitationFocus(params.citationFocus);
  if (fromFocus && params.sources.some((source) => source.id === fromFocus)) {
    return fromFocus;
  }
  const fallback = String(params.fallback || "").trim().toLowerCase();
  if (fallback && params.sources.some((source) => source.id === fallback)) {
    return fallback;
  }
  return params.sources[0]?.id || "";
}

export function filterEvidenceByConcept(cards: EvidenceCard[], query: string): EvidenceCard[] {
  const normalizedQuery = String(query || "").trim();
  if (!normalizedQuery) {
    return cards;
  }
  const ranked = cards
    .map((card) => ({ card, score: semanticScore(card, normalizedQuery) }))
    .filter((row) => row.score >= 0.2)
    .sort((left, right) => right.score - left.score);
  if (!ranked.length) {
    return [];
  }
  return ranked.map((row) => row.card);
}

export function summarizeEvidenceQuality(cards: EvidenceCard[]): EvidenceQualitySummary {
  if (!cards.length) {
    return {
      level: "low",
      score: 0,
      warning: "No supporting evidence found. Add sources before relying on this answer.",
    };
  }
  let total = 0;
  for (const card of cards) {
    total += evidenceQualityWeight(card);
  }
  const score = Number((total / cards.length).toFixed(2));
  const level = score >= 0.75 ? "high" : score >= 0.5 ? "medium" : "low";
  const warning =
    level === "low"
      ? "Supporting evidence is weak. Review source highlights before using this result."
      : level === "medium"
        ? "Evidence is usable but mixed. Verify key claims in source context."
        : "";
  return { level, score, warning };
}
