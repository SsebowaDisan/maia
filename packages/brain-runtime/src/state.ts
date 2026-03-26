/**
 * Brain state — full working memory including contract, coverage,
 * evidence pool, step outcomes, and revision budget.
 * Mirrors platform's state.py + signals.py.
 */

import type { BrainStep, ConversationTurn } from "./types";
import type { CoverageItem } from "./coverage";

// ── Signal Types ─────────────────────────────────────────────────────────────

export type StepVerdict = "proceed" | "revise" | "question" | "escalate" | "halt";

export interface StepOutcome {
  stepIndex: number;
  agentId: string;
  task: string;
  output: string;
  verdict: StepVerdict;
  reviewRound: number;
  costUsd: number;
  tokensUsed: number;
}

export interface BrainSignal {
  type: "coverage_gap" | "revision_needed" | "dialogue_needed" | "budget_warning" | "stuckness";
  severity: "low" | "medium" | "high" | "critical";
  message: string;
  data?: Record<string, unknown>;
}

export interface BrainDirective {
  action: "continue" | "add_steps" | "halt" | "escalate" | "pivot";
  reason: string;
  newSteps?: BrainStep[];
}

// ── Contract ─────────────────────────────────────────────────────────────────

export interface TaskContract {
  goal: string;
  requiredFacts: string[];
  requiredActions: string[];
  definitionOfDone: string;
}

// ── Coverage Tracking ────────────────────────────────────────────────────────

export interface CoverageState {
  facts: CoverageItem[];
  actions: CoverageItem[];
  factsCoveredRatio: number;
  actionsCoveredRatio: number;
  allSatisfied: boolean;
}

// ── Brain State ──────────────────────────────────────────────────────────────

export interface BrainState {
  /** The task contract defining what must be achieved. */
  contract: TaskContract;
  /** Current coverage of required facts/actions. */
  coverage: CoverageState;
  /** Evidence gathered from step outputs. */
  evidencePool: string[];
  /** All step outcomes in order. */
  stepOutcomes: StepOutcome[];
  /** All signals raised during execution. */
  signals: BrainSignal[];
  /** Active directive (what to do next). */
  directive: BrainDirective;
  /** Revision budget remaining. */
  revisionBudgetRemaining: number;
  /** Maximum revisions allowed. */
  maxRevisions: number;
  /** All conversations across all steps. */
  conversations: ConversationTurn[];
  /** Running cost total. */
  totalCostUsd: number;
  /** Running token total. */
  totalTokens: number;
}

/**
 * Create a fresh Brain state from a goal.
 */
export function createBrainState(
  goal: string,
  requiredFacts: string[] = [],
  requiredActions: string[] = [],
  maxRevisions: number = 2,
): BrainState {
  return {
    contract: {
      goal,
      requiredFacts,
      requiredActions,
      definitionOfDone: `Complete: ${goal}`,
    },
    coverage: {
      facts: requiredFacts.map((f) => ({ description: f, satisfied: false, confidence: 0 })),
      actions: requiredActions.map((a) => ({ description: a, satisfied: false, confidence: 0 })),
      factsCoveredRatio: 0,
      actionsCoveredRatio: 0,
      allSatisfied: false,
    },
    evidencePool: [],
    stepOutcomes: [],
    signals: [],
    directive: { action: "continue", reason: "Initial state" },
    revisionBudgetRemaining: maxRevisions,
    maxRevisions,
    conversations: [],
    totalCostUsd: 0,
    totalTokens: 0,
  };
}

/**
 * Record a step outcome and update evidence pool.
 */
export function recordStepOutcome(state: BrainState, outcome: StepOutcome): void {
  state.stepOutcomes.push(outcome);
  if (outcome.output) {
    state.evidencePool.push(outcome.output.slice(0, 500));
  }
  state.totalCostUsd += outcome.costUsd;
  state.totalTokens += outcome.tokensUsed;
}

/**
 * Update coverage state from a coverage check result.
 */
export function updateCoverage(
  state: BrainState,
  facts: CoverageItem[],
  actions: CoverageItem[],
): void {
  state.coverage.facts = facts;
  state.coverage.actions = actions;
  state.coverage.factsCoveredRatio = facts.length > 0
    ? facts.filter((f) => f.satisfied).length / facts.length
    : 1;
  state.coverage.actionsCoveredRatio = actions.length > 0
    ? actions.filter((a) => a.satisfied).length / actions.length
    : 1;
  state.coverage.allSatisfied =
    state.coverage.factsCoveredRatio >= 1 && state.coverage.actionsCoveredRatio >= 1;
}

/**
 * Raise a signal.
 */
export function raiseSignal(state: BrainState, signal: BrainSignal): void {
  state.signals.push(signal);
}

/**
 * Consume one revision from the budget. Returns false if no budget left.
 */
export function consumeRevisionBudget(state: BrainState): boolean {
  if (state.revisionBudgetRemaining <= 0) return false;
  state.revisionBudgetRemaining--;
  return true;
}