/**
 * Guardrails — input + output safety rails for agent responses.
 *
 * Two types:
 * - Input guardrails: validate/filter user input BEFORE the LLM sees it
 * - Output guardrails: validate/filter agent output BEFORE the user sees it
 *
 * Built-in guards + custom guard support.
 */

export interface GuardrailResult {
  passed: boolean;
  blocked: boolean;
  reason?: string;
  modified?: string;
  guardId: string;
}

export type GuardFn = (text: string) => GuardrailResult | Promise<GuardrailResult>;

export interface GuardrailConfig {
  inputGuards?: GuardFn[];
  outputGuards?: GuardFn[];
  /** Block or warn on failure (default: "block"). */
  mode?: "block" | "warn";
}

// ── Built-in Guards ──────────────────────────────────────────────────────────

/** Block prompt injection attempts. */
export function injectionGuard(): GuardFn {
  const patterns = [
    /ignore (?:all )?(?:previous|above|prior) instructions/i,
    /you are now/i,
    /forget (?:everything|all|your)/i,
    /disregard (?:all|your|the)/i,
    /new instructions:/i,
    /system:\s*you are/i,
    /\bDAN\b.*mode/i,
    /jailbreak/i,
  ];
  return (text) => {
    for (const p of patterns) {
      if (p.test(text)) {
        return { passed: false, blocked: true, reason: "Possible prompt injection detected", guardId: "injection" };
      }
    }
    return { passed: true, blocked: false, guardId: "injection" };
  };
}

/** Block PII (emails, phones, SSNs). */
export function piiGuard(): GuardFn {
  const patterns = [
    { regex: /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, type: "email" },
    { regex: /\b\d{3}[-.]?\d{2}[-.]?\d{4}\b/g, type: "SSN" },
    { regex: /\b(?:\+?1[-.]?)?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4}\b/g, type: "phone" },
    { regex: /\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b/g, type: "credit card" },
  ];
  return (text) => {
    for (const { regex, type } of patterns) {
      if (regex.test(text)) {
        regex.lastIndex = 0; // Reset after test
        return { passed: false, blocked: true, reason: `PII detected: ${type}`, guardId: "pii" };
      }
    }
    return { passed: true, blocked: false, guardId: "pii" };
  };
}

/** Block toxic/harmful content. */
export function toxicityGuard(): GuardFn {
  const patterns = [
    /\b(?:kill|murder|assassinate|bomb|explode)\b.*\b(?:how|instructions|steps|guide)\b/i,
    /\b(?:hack|exploit|breach)\b.*\b(?:instructions|tutorial|steps)\b/i,
    /\bself[- ]?harm\b/i,
  ];
  return (text) => {
    for (const p of patterns) {
      if (p.test(text)) {
        return { passed: false, blocked: true, reason: "Potentially harmful content detected", guardId: "toxicity" };
      }
    }
    return { passed: true, blocked: false, guardId: "toxicity" };
  };
}

/** Enforce max output length. */
export function lengthGuard(maxChars: number = 10000): GuardFn {
  return (text) => {
    if (text.length > maxChars) {
      return {
        passed: false, blocked: false, guardId: "length",
        reason: `Output exceeds ${maxChars} chars (${text.length})`,
        modified: text.slice(0, maxChars) + "\n\n[Output truncated]",
      };
    }
    return { passed: true, blocked: false, guardId: "length" };
  };
}

/** Custom guard with a validation function. */
export function customGuard(id: string, fn: (text: string) => boolean | string): GuardFn {
  return (text) => {
    const result = fn(text);
    if (result === true) return { passed: true, blocked: false, guardId: id };
    if (result === false) return { passed: false, blocked: true, reason: `Custom guard "${id}" failed`, guardId: id };
    return { passed: false, blocked: false, reason: result, modified: undefined, guardId: id };
  };
}

// ── Runner ───────────────────────────────────────────────────────────────────

/**
 * Run all guards on a text. Returns combined result.
 */
export async function runGuards(
  text: string,
  guards: GuardFn[],
  mode: "block" | "warn" = "block",
): Promise<{ text: string; passed: boolean; results: GuardrailResult[] }> {
  const results: GuardrailResult[] = [];
  let current = text;

  for (const guard of guards) {
    const result = await guard(current);
    results.push(result);

    if (result.blocked && mode === "block") {
      return { text: "", passed: false, results };
    }

    if (result.modified) {
      current = result.modified;
    }
  }

  const allPassed = results.every((r) => r.passed);
  return { text: current, passed: allPassed, results };
}

/**
 * Create a full guardrail pipeline.
 */
export function createGuardrails(config: GuardrailConfig = {}) {
  const inputGuards = config.inputGuards ?? [injectionGuard()];
  const outputGuards = config.outputGuards ?? [piiGuard(), toxicityGuard(), lengthGuard()];
  const mode = config.mode ?? "block";

  return {
    /** Run input guards on user message. */
    async checkInput(text: string) { return runGuards(text, inputGuards, mode); },
    /** Run output guards on agent response. */
    async checkOutput(text: string) { return runGuards(text, outputGuards, mode); },
  };
}