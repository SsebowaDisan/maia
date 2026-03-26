/**
 * Evaluation framework — measure agent quality with datasets.
 *
 * Usage:
 *   const results = await evaluate(brain, dataset, scorers);
 *   console.log(results.summary);
 */

export interface EvalExample {
  /** Input goal/question. */
  input: string;
  /** Expected output (for exact/fuzzy match). */
  expected?: string;
  /** Tags for filtering (e.g., "research", "simple"). */
  tags?: string[];
  /** Custom metadata. */
  metadata?: Record<string, any>;
}

export interface EvalDataset {
  name: string;
  examples: EvalExample[];
}

export interface ScorerResult {
  scorerId: string;
  score: number;
  passed: boolean;
  reason?: string;
}

export type Scorer = (input: string, output: string, expected?: string) => ScorerResult | Promise<ScorerResult>;

export interface EvalResult {
  input: string;
  output: string;
  expected?: string;
  scores: ScorerResult[];
  costUsd: number;
  tokensUsed: number;
  durationMs: number;
  passed: boolean;
}

export interface EvalSummary {
  datasetName: string;
  total: number;
  passed: number;
  failed: number;
  passRate: number;
  avgScore: number;
  totalCostUsd: number;
  totalTokens: number;
  totalDurationMs: number;
  byScorer: Record<string, { avg: number; passRate: number }>;
  results: EvalResult[];
}

// ── Built-in Scorers ─────────────────────────────────────────────────────────

/** Exact string match. */
export function exactMatch(): Scorer {
  return (_input, output, expected) => {
    if (!expected) return { scorerId: "exact_match", score: 1, passed: true };
    const match = output.trim() === expected.trim();
    return { scorerId: "exact_match", score: match ? 1 : 0, passed: match };
  };
}

/** Fuzzy match — token overlap ratio. */
export function fuzzyMatch(threshold: number = 0.6): Scorer {
  return (_input, output, expected) => {
    if (!expected) return { scorerId: "fuzzy_match", score: 1, passed: true };
    const outTokens = new Set(output.toLowerCase().split(/\s+/));
    const expTokens = new Set(expected.toLowerCase().split(/\s+/));
    const overlap = [...outTokens].filter((t) => expTokens.has(t)).length;
    const score = overlap / Math.max(1, expTokens.size);
    return { scorerId: "fuzzy_match", score: Math.round(score * 100) / 100, passed: score >= threshold };
  };
}

/** Check that output contains specific keywords. */
export function containsKeywords(...keywords: string[]): Scorer {
  return (_input, output) => {
    const lower = output.toLowerCase();
    const found = keywords.filter((k) => lower.includes(k.toLowerCase()));
    const score = found.length / Math.max(1, keywords.length);
    return {
      scorerId: "contains_keywords", score: Math.round(score * 100) / 100,
      passed: score >= 1, reason: score < 1 ? `Missing: ${keywords.filter((k) => !lower.includes(k.toLowerCase())).join(", ")}` : undefined,
    };
  };
}

/** Check output length is within range. */
export function lengthRange(min: number, max: number): Scorer {
  return (_input, output) => {
    const len = output.length;
    const passed = len >= min && len <= max;
    return {
      scorerId: "length_range", score: passed ? 1 : 0, passed,
      reason: !passed ? `Length ${len} outside [${min}, ${max}]` : undefined,
    };
  };
}

/** No hallucination — output must not contain forbidden phrases. */
export function noHallucination(...forbidden: string[]): Scorer {
  return (_input, output) => {
    const lower = output.toLowerCase();
    const found = forbidden.filter((f) => lower.includes(f.toLowerCase()));
    return {
      scorerId: "no_hallucination", score: found.length === 0 ? 1 : 0,
      passed: found.length === 0, reason: found.length > 0 ? `Found: ${found.join(", ")}` : undefined,
    };
  };
}

// ── Runner ───────────────────────────────────────────────────────────────────

/**
 * Run evaluation on a dataset with the Brain.
 */
export async function evaluate(
  runFn: (input: string) => Promise<{ output: string; totalCostUsd: number; totalTokens: number }>,
  dataset: EvalDataset,
  scorers: Scorer[],
  options?: { concurrency?: number; onResult?: (result: EvalResult, index: number) => void },
): Promise<EvalSummary> {
  const results: EvalResult[] = [];

  for (let i = 0; i < dataset.examples.length; i++) {
    const example = dataset.examples[i];
    const start = Date.now();

    let output = "";
    let costUsd = 0;
    let tokensUsed = 0;

    try {
      const result = await runFn(example.input);
      output = result.output;
      costUsd = result.totalCostUsd;
      tokensUsed = result.totalTokens;
    } catch (err) {
      output = `[Error: ${err instanceof Error ? err.message : String(err)}]`;
    }

    const durationMs = Date.now() - start;
    const scores: ScorerResult[] = [];
    for (const scorer of scorers) {
      scores.push(await scorer(example.input, output, example.expected));
    }

    const passed = scores.every((s) => s.passed);
    const evalResult: EvalResult = { input: example.input, output, expected: example.expected, scores, costUsd, tokensUsed, durationMs, passed };
    results.push(evalResult);
    options?.onResult?.(evalResult, i);
  }

  // Compute summary
  const passed = results.filter((r) => r.passed).length;
  const allScores = results.flatMap((r) => r.scores);
  const byScorer: Record<string, { avg: number; passRate: number }> = {};
  for (const scorer of scorers) {
    const sid = typeof scorer === "function" ? (scorer as any)("", "", "")?.scorerId ?? "unknown" : "unknown";
    // Get actual results for this scorer from already-computed scores
    const scorerResults = allScores.filter((s) => s.scorerId === sid);
    if (scorerResults.length > 0) {
      byScorer[sid] = {
        avg: Math.round((scorerResults.reduce((a, s) => a + s.score, 0) / scorerResults.length) * 100) / 100,
        passRate: Math.round((scorerResults.filter((s) => s.passed).length / scorerResults.length) * 100) / 100,
      };
    }
  }

  return {
    datasetName: dataset.name,
    total: results.length,
    passed,
    failed: results.length - passed,
    passRate: results.length > 0 ? Math.round((passed / results.length) * 100) / 100 : 0,
    avgScore: allScores.length > 0 ? Math.round((allScores.reduce((a, s) => a + s.score, 0) / allScores.length) * 100) / 100 : 0,
    totalCostUsd: Math.round(results.reduce((a, r) => a + r.costUsd, 0) * 10000) / 10000,
    totalTokens: results.reduce((a, r) => a + r.tokensUsed, 0),
    totalDurationMs: results.reduce((a, r) => a + r.durationMs, 0),
    byScorer,
    results,
  };
}