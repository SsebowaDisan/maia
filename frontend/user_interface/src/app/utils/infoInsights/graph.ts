import { cleanSourceLabel, compactLabel } from "./text";
import type { ClaimInsight, EvidenceCard, SourceGraph, SourceGraphEdge } from "./types";

function buildSourceGraph(
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

    const sourceHits = new Map<
      string,
      { sourceId: string; evidenceIds: Set<string>; count: number }
    >();
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

export { buildSourceGraph };
