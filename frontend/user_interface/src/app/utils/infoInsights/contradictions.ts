import { SEVERITY_RANK } from "./constants";
import {
  detectPolarity,
  findNumericConflict,
  findOppositeTerms,
  overlapScore,
} from "./contradictionCore";
import { extractNumericFacts } from "./numeric";
import { tokenize } from "./text";
import type { ClaimInsight, ContradictionFinding, EvidenceCard } from "./types";

function detectContradictions(
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

export { detectContradictions };
