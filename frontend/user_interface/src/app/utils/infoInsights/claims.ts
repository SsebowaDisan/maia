import { tokenize, plainText, normalizeText } from "./text";
import type { ClaimInsight, ClaimStatus, EvidenceCard } from "./types";

function extractClaims(answerText: string): string[] {
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

function buildClaimInsights(
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

function supportRate(claims: ClaimInsight[]): number {
  if (!claims.length) {
    return 0;
  }
  const supported = claims.filter((claim) => claim.status === "supported").length;
  return Math.round((supported / claims.length) * 100);
}

export { buildClaimInsights, extractClaims, supportRate };
