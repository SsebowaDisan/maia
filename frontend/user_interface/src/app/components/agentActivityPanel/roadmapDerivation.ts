import type { AgentActivityEvent } from "../../types";

type RoadmapStep = { toolId: string; title: string; whyThisStep: string };

const REQUEST_TEXT_KEYS = [
  "original_request",
  "request_message",
  "objective",
  "contract_objective",
  "summary",
  "message",
  "task",
] as const;

const STOPWORDS = new Set([
  "the",
  "and",
  "for",
  "with",
  "that",
  "this",
  "from",
  "into",
  "about",
  "your",
  "their",
  "then",
  "when",
  "what",
  "where",
  "which",
  "while",
  "after",
  "before",
  "please",
  "should",
  "would",
  "could",
  "have",
  "has",
  "had",
  "use",
  "using",
  "into",
  "over",
  "under",
  "across",
  "through",
]);

function eventPayload(event: AgentActivityEvent): Record<string, unknown> {
  const data = (event.data || {}) as Record<string, unknown>;
  const metadata = (event.metadata || {}) as Record<string, unknown>;
  return { ...data, ...metadata };
}

function normalizeWhitespace(value: unknown): string {
  return String(value || "")
    .split(/\s+/)
    .join(" ")
    .trim();
}

function parseStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => normalizeWhitespace(item))
    .filter((item) => item.length > 0);
}

function requestTextFromEvents(visibleEvents: AgentActivityEvent[]): string {
  for (let i = visibleEvents.length - 1; i >= 0; i -= 1) {
    const payload = eventPayload(visibleEvents[i]);
    for (const key of REQUEST_TEXT_KEYS) {
      const value = normalizeWhitespace(payload[key]);
      if (value.length > 0) {
        return value;
      }
    }
    const requiredActions = parseStringList(payload.required_actions);
    if (requiredActions.length) {
      return requiredActions.join(" and ");
    }
  }
  return "";
}

function sentenceCase(value: string): string {
  const cleaned = normalizeWhitespace(value).replace(/[.;:,]+$/g, "");
  if (!cleaned) {
    return "";
  }
  return `${cleaned.charAt(0).toUpperCase()}${cleaned.slice(1)}`;
}

function deriveRoadmapFromRequestText(requestText: string): RoadmapStep[] {
  const normalized = normalizeWhitespace(requestText);
  if (!normalized) {
    return [];
  }
  const splitByConjunction = normalized
    .split(/\s+(?:and then|then|and)\s+/i)
    .map((part) => sentenceCase(part))
    .filter((part) => part.length > 0);
  const clauses = (splitByConjunction.length > 1
    ? splitByConjunction
    : normalized
        .split(/[.!?;]+/)
        .map((part) => sentenceCase(part))
        .filter((part) => part.length > 0)
  ).slice(0, 5);
  if (!clauses.length) {
    return [];
  }
  return clauses.map((title, index) => ({
    toolId: `prompt.request_step_${index + 1}`,
    title,
    whyThisStep: "Directly requested by the user.",
  }));
}

function tokenizeForAlignment(value: string): string[] {
  return normalizeWhitespace(value)
    .toLowerCase()
    .replace(/[^a-z0-9@./\s_-]/g, " ")
    .split(/\s+/)
    .map((token) => token.trim())
    .filter((token) => token.length >= 3 && !STOPWORDS.has(token));
}

function roadmapMatchesRequest(roadmapSteps: RoadmapStep[], requestText: string): boolean {
  if (!roadmapSteps.length) {
    return false;
  }
  const requestTokens = tokenizeForAlignment(requestText);
  if (requestTokens.length < 2) {
    return true;
  }
  const requestTokenSet = new Set(requestTokens);
  let alignedSteps = 0;
  for (const step of roadmapSteps) {
    const stepTokens = tokenizeForAlignment(`${step.title} ${step.whyThisStep} ${step.toolId}`);
    if (!stepTokens.length) {
      continue;
    }
    let overlap = 0;
    for (const token of stepTokens) {
      if (requestTokenSet.has(token)) {
        overlap += 1;
      }
    }
    const overlapRatio = overlap / stepTokens.length;
    if (overlap >= 2 || overlapRatio >= 0.34) {
      alignedSteps += 1;
    }
  }
  const minAligned = roadmapSteps.length <= 2 ? 1 : Math.ceil(roadmapSteps.length / 2);
  return alignedSteps >= minAligned;
}

function parsePlanStepsFromEvents(visibleEvents: AgentActivityEvent[]): RoadmapStep[] {
  for (let i = visibleEvents.length - 1; i >= 0; i -= 1) {
    const event = visibleEvents[i];
    const eventType = String(event.event_type || "").toLowerCase();
    if (eventType !== "plan_ready" && eventType !== "plan_candidate" && eventType !== "plan_refined") {
      continue;
    }
    const payload = eventPayload(event);
    if (!Array.isArray(payload.steps) || payload.steps.length === 0) {
      continue;
    }
    return (payload.steps as Record<string, unknown>[])
      .map((row) => ({
        toolId: normalizeWhitespace(row.tool_id),
        title: normalizeWhitespace(row.title),
        whyThisStep: normalizeWhitespace(row.why_this_step),
      }))
      .filter((row) => row.title.length > 0);
  }
  const planStepRows = visibleEvents
    .filter((event) => String(event.event_type || "").toLowerCase() === "llm.plan_step")
    .map((event, rowIndex) => {
      const payload = eventPayload(event);
      const title = normalizeWhitespace(payload.title);
      if (!title) {
        return null;
      }
      const stepRaw = Number(payload.step);
      const stepOrder = Number.isFinite(stepRaw) && stepRaw >= 1 ? Math.round(stepRaw) : rowIndex + 1;
      return {
        toolId: normalizeWhitespace(payload.tool_id),
        title,
        whyThisStep: normalizeWhitespace(payload.why_this_step),
        stepOrder,
      };
    })
    .filter(
      (
        row,
      ): row is {
        toolId: string;
        title: string;
        whyThisStep: string;
        stepOrder: number;
      } => Boolean(row),
    )
    .sort((left, right) => left.stepOrder - right.stepOrder);
  if (planStepRows.length) {
    return planStepRows.map(({ toolId, title, whyThisStep }) => ({
      toolId,
      title,
      whyThisStep,
    }));
  }
  for (let i = visibleEvents.length - 1; i >= 0; i -= 1) {
    const event = visibleEvents[i];
    const eventType = String(event.event_type || "").toLowerCase();
    if (eventType !== "llm.task_contract_completed") {
      continue;
    }
    const payload = eventPayload(event);
    const outputs = Array.isArray(payload.required_outputs) ? payload.required_outputs : [];
    const rows = outputs
      .map((item, index) => {
        const title = normalizeWhitespace(item);
        if (!title) {
          return null;
        }
        return {
          toolId: `contract_output_${index + 1}`,
          title,
          whyThisStep: "",
        };
      })
      .filter((row): row is RoadmapStep => Boolean(row));
    if (rows.length) {
      return rows;
    }
  }
  return [];
}

function deriveRoadmapActiveIndex(
  visibleEvents: AgentActivityEvent[],
  roadmapSteps: RoadmapStep[],
): number {
  if (!roadmapSteps.length) {
    return -1;
  }
  let hasExecutionStarted = false;
  let completedCursor = -1;
  for (const event of visibleEvents) {
    const eventType = String(event.event_type || "").toLowerCase();
    const payload = eventPayload(event);
    if (
      eventType === "tool_started" ||
      eventType === "tool_completed" ||
      eventType === "tool_failed" ||
      eventType === "tool_skipped"
    ) {
      hasExecutionStarted = true;
    }
    if (eventType === "workspace.sheets.track_step") {
      const stepName = String(payload.step_name || "");
      const match = stepName.match(/^(\d+)\./);
      if (match) {
        const stepNum = Number(match[1]);
        if (Number.isFinite(stepNum) && stepNum >= 1) {
          completedCursor = Math.max(completedCursor, stepNum - 1);
        }
      }
      continue;
    }
    if (eventType !== "tool_completed") {
      continue;
    }
    if (Boolean(payload.shadow)) {
      continue;
    }
    const toolId = normalizeWhitespace(payload.tool_id);
    if (!toolId) {
      continue;
    }
    for (let idx = Math.max(0, completedCursor + 1); idx < roadmapSteps.length; idx += 1) {
      if (roadmapSteps[idx].toolId === toolId) {
        completedCursor = idx;
        break;
      }
    }
  }
  if (!hasExecutionStarted) {
    return 0;
  }
  const nextCursor = completedCursor + 1;
  return Math.min(Math.max(0, nextCursor), roadmapSteps.length);
}

function derivePlannedRoadmap(
  visibleEvents: AgentActivityEvent[],
): { plannedRoadmapSteps: RoadmapStep[]; roadmapActiveIndex: number } {
  const requestText = requestTextFromEvents(visibleEvents);
  const plannedRoadmapSteps = parsePlanStepsFromEvents(visibleEvents);
  if (!plannedRoadmapSteps.length) {
    const requestRoadmapSteps = deriveRoadmapFromRequestText(requestText);
    if (requestRoadmapSteps.length) {
      return { plannedRoadmapSteps: requestRoadmapSteps, roadmapActiveIndex: 0 };
    }
    return { plannedRoadmapSteps: [], roadmapActiveIndex: -1 };
  }
  if (requestText && !roadmapMatchesRequest(plannedRoadmapSteps, requestText)) {
    const requestRoadmapSteps = deriveRoadmapFromRequestText(requestText);
    if (requestRoadmapSteps.length) {
      const roadmapActiveIndex = deriveRoadmapActiveIndex(visibleEvents, requestRoadmapSteps);
      return { plannedRoadmapSteps: requestRoadmapSteps, roadmapActiveIndex };
    }
  }
  const roadmapActiveIndex = deriveRoadmapActiveIndex(visibleEvents, plannedRoadmapSteps);
  return {
    plannedRoadmapSteps,
    roadmapActiveIndex,
  };
}

export { derivePlannedRoadmap };
export type { RoadmapStep };
