import type { AgentActivityEvent } from "../../types";

type RoadmapStep = { toolId: string; title: string; whyThisStep: string };

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
  const plannedRoadmapSteps = parsePlanStepsFromEvents(visibleEvents);
  if (!plannedRoadmapSteps.length) {
    return { plannedRoadmapSteps: [], roadmapActiveIndex: -1 };
  }
  const roadmapActiveIndex = deriveRoadmapActiveIndex(visibleEvents, plannedRoadmapSteps);
  return {
    plannedRoadmapSteps,
    roadmapActiveIndex,
  };
}

export { derivePlannedRoadmap };
export type { RoadmapStep };
