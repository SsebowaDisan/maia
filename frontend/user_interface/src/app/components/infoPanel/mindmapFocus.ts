import type { FocusNodePayload } from "../mindmapViewer/types";
import type { EvidenceCard } from "../../utils/infoInsights";
import type { VerificationSourceItem } from "./verificationModels";

type MindmapFocusResolution = {
  sourceId: string;
  evidenceCard: EvidenceCard | null;
  evidenceIndex: number;
};

function cleanText(value: unknown): string {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function normalizeId(value: unknown): string {
  return cleanText(value).toLowerCase();
}

function tokenize(value: string): Set<string> {
  return new Set(
    cleanText(value)
      .toLowerCase()
      .split(/[^a-z0-9]+/)
      .map((row) => row.trim())
      .filter((row) => row.length >= 3)
      .slice(0, 80),
  );
}

function findSourceId(node: FocusNodePayload, sources: VerificationSourceItem[]): string {
  const explicitSourceId = normalizeId(node.sourceId);
  if (explicitSourceId && sources.some((source) => source.id === explicitSourceId)) {
    return explicitSourceId;
  }
  const sourceName = cleanText(node.sourceName).toLowerCase();
  if (sourceName) {
    const exact = sources.find((source) => cleanText(source.title).toLowerCase() === sourceName);
    if (exact) {
      return exact.id;
    }
    const partial = sources.find((source) => cleanText(source.title).toLowerCase().includes(sourceName));
    if (partial) {
      return partial.id;
    }
  }
  return sources[0]?.id || "";
}

function scoreEvidence(card: EvidenceCard, queryTokens: Set<string>, pageHint: string): number {
  if (!queryTokens.size) {
    return 0;
  }
  const cardTokens = tokenize(`${card.title} ${card.extract} ${card.source}`);
  let overlap = 0;
  for (const token of queryTokens) {
    if (cardTokens.has(token)) {
      overlap += 1;
    }
  }
  const overlapScore = overlap / queryTokens.size;
  const pageMatch = pageHint && cleanText(card.page).includes(pageHint) ? 0.25 : 0;
  return overlapScore + pageMatch;
}

function resolveMindmapFocus(params: {
  node: FocusNodePayload;
  sources: VerificationSourceItem[];
  evidenceBySource: Record<string, EvidenceCard[]>;
}): MindmapFocusResolution {
  const sourceId = findSourceId(params.node, params.sources);
  const sourceEvidence = params.evidenceBySource[sourceId] || [];
  if (!sourceEvidence.length) {
    return {
      sourceId,
      evidenceCard: null,
      evidenceIndex: -1,
    };
  }
  const query = [params.node.title, params.node.text, params.node.sourceName].map(cleanText).join(" ");
  const queryTokens = tokenize(query);
  const pageHint = cleanText(params.node.pageRef).match(/\d+/)?.[0] || "";
  let bestIndex = 0;
  let bestScore = -1;
  for (let index = 0; index < sourceEvidence.length; index += 1) {
    const score = scoreEvidence(sourceEvidence[index], queryTokens, pageHint);
    if (score > bestScore) {
      bestScore = score;
      bestIndex = index;
    }
  }
  return {
    sourceId,
    evidenceCard: sourceEvidence[bestIndex] || null,
    evidenceIndex: bestIndex,
  };
}

export { resolveMindmapFocus };
export type { MindmapFocusResolution };
