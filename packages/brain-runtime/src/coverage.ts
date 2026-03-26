/**
 * Coverage tracking — LLM verifies step outputs satisfy required facts/actions.
 * Mirrors platform's coverage.py: semantic checking, not keyword matching.
 */

import type { LLMConfig } from "./types";
import { callLLMJson } from "./llm";
import type { LLMCallResult } from "./llm";

export interface CoverageItem {
  description: string;
  satisfied: boolean;
  evidence?: string;
  confidence: number;
}

export interface CoverageResult {
  facts: CoverageItem[];
  actions: CoverageItem[];
  factsCoveredRatio: number;
  actionsCoveredRatio: number;
  allSatisfied: boolean;
  gaps: string[];
  cost: LLMCallResult;
}

const CONFIDENCE_THRESHOLD = 0.65;

/**
 * Check whether a step's output satisfies the required facts and actions.
 * Uses LLM semantic evaluation — no keyword matching.
 */
export async function checkCoverage(
  llm: LLMConfig,
  stepOutput: string,
  requiredFacts: string[],
  requiredActions: string[],
): Promise<CoverageResult> {
  if (!requiredFacts.length && !requiredActions.length) {
    return {
      facts: [], actions: [], factsCoveredRatio: 1, actionsCoveredRatio: 1,
      allSatisfied: true, gaps: [], cost: emptyCost(llm),
    };
  }

  const factsList = requiredFacts.map((f, i) => `F${i + 1}: ${f}`).join("\n");
  const actionsList = requiredActions.map((a, i) => `A${i + 1}: ${a}`).join("\n");

  const systemPrompt =
    "You are a semantic coverage checker. Given step output and a list of required facts/actions, "
    + "determine which are satisfied by the output. Use semantic understanding, not keyword matching.\n\n"
    + "Return JSON: {\n"
    + "  \"facts\": [{\"id\": \"F1\", \"satisfied\": true/false, \"confidence\": 0.0-1.0, \"evidence\": \"quote from output\"}],\n"
    + "  \"actions\": [{\"id\": \"A1\", \"satisfied\": true/false, \"confidence\": 0.0-1.0, \"evidence\": \"quote from output\"}]\n"
    + "}\n\n"
    + "A fact is satisfied if the output contains the information (even paraphrased).\n"
    + "An action is satisfied if the output shows the action was performed or its result.";

  const userPrompt =
    `Step output:\n${stepOutput.slice(0, 3000)}\n\n`
    + (factsList ? `Required facts:\n${factsList}\n\n` : "")
    + (actionsList ? `Required actions:\n${actionsList}` : "");

  const { data, cost } = await callLLMJson<{
    facts?: Array<{ id?: string; satisfied?: boolean; confidence?: number; evidence?: string }>;
    actions?: Array<{ id?: string; satisfied?: boolean; confidence?: number; evidence?: string }>;
  }>(llm, systemPrompt, userPrompt, { facts: [], actions: [] });

  const facts: CoverageItem[] = requiredFacts.map((desc, i) => {
    const match = (data.facts ?? []).find((f) => f.id === `F${i + 1}`);
    const confidence = match?.confidence ?? 0;
    return {
      description: desc,
      satisfied: (match?.satisfied ?? false) && confidence >= CONFIDENCE_THRESHOLD,
      evidence: match?.evidence,
      confidence,
    };
  });

  const actions: CoverageItem[] = requiredActions.map((desc, i) => {
    const match = (data.actions ?? []).find((a) => a.id === `A${i + 1}`);
    const confidence = match?.confidence ?? 0;
    return {
      description: desc,
      satisfied: (match?.satisfied ?? false) && confidence >= CONFIDENCE_THRESHOLD,
      evidence: match?.evidence,
      confidence,
    };
  });

  const satisfiedFacts = facts.filter((f) => f.satisfied).length;
  const satisfiedActions = actions.filter((a) => a.satisfied).length;
  const factsCoveredRatio = requiredFacts.length > 0 ? satisfiedFacts / requiredFacts.length : 1;
  const actionsCoveredRatio = requiredActions.length > 0 ? satisfiedActions / requiredActions.length : 1;

  const gaps: string[] = [
    ...facts.filter((f) => !f.satisfied).map((f) => `Missing fact: ${f.description}`),
    ...actions.filter((a) => !a.satisfied).map((a) => `Missing action: ${a.description}`),
  ];

  return {
    facts,
    actions,
    factsCoveredRatio: Math.round(factsCoveredRatio * 1000) / 1000,
    actionsCoveredRatio: Math.round(actionsCoveredRatio * 1000) / 1000,
    allSatisfied: gaps.length === 0,
    gaps,
    cost,
  };
}

function emptyCost(llm: LLMConfig): LLMCallResult {
  return { text: "", tokensUsed: 0, costUsd: 0, model: llm.model ?? "gpt-4o", success: true };
}