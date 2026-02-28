import {
  NEGATION_TERMS,
  OPPOSITE_TERM_PAIRS,
  POSITIVE_TERMS,
} from "./constants";
import type { NumericFact } from "./types";

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

export { detectPolarity, findNumericConflict, findOppositeTerms, overlapScore };
