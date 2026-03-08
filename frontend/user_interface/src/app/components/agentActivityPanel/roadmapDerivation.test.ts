import { describe, expect, it } from "vitest";
import type { AgentActivityEvent } from "../../types";
import { derivePlannedRoadmap } from "./roadmapDerivation";

function makeEvent(
  eventType: string,
  metadata: Record<string, unknown> = {},
  data: Record<string, unknown> = {},
): AgentActivityEvent {
  return {
    event_id: `evt-${eventType}`,
    run_id: "run-1",
    event_type: eventType,
    title: eventType,
    detail: "",
    timestamp: "2026-03-08T12:00:00Z",
    metadata,
    data,
  };
}

describe("roadmapDerivation", () => {
  it("derives roadmap tasks from plan steps", () => {
    const events = [
      makeEvent("plan_ready", {
        steps: [
          { tool_id: "marketing.web_research", title: "Collect web sources", why_this_step: "Need evidence" },
          { tool_id: "docs.create", title: "Draft report", why_this_step: "Assemble findings" },
        ],
      }),
    ];
    const result = derivePlannedRoadmap(events);
    expect(result.plannedRoadmapSteps).toHaveLength(2);
    expect(result.plannedRoadmapSteps[0].title).toBe("Collect web sources");
    expect(result.roadmapActiveIndex).toBe(0);
  });

  it("marks completed tools done and advances active cursor", () => {
    const events = [
      makeEvent("plan_ready", {
        steps: [
          { tool_id: "marketing.web_research", title: "Collect web sources" },
          { tool_id: "docs.create", title: "Draft report" },
        ],
      }),
      makeEvent("tool_started", { tool_id: "marketing.web_research" }),
      makeEvent("tool_completed", { tool_id: "marketing.web_research" }),
    ];
    const result = derivePlannedRoadmap(events);
    expect(result.roadmapActiveIndex).toBe(1);
  });

  it("ignores shadow completions for roadmap done state", () => {
    const events = [
      makeEvent("plan_ready", {
        steps: [
          { tool_id: "marketing.web_research", title: "Collect web sources" },
          { tool_id: "docs.create", title: "Draft report" },
        ],
      }),
      makeEvent("tool_started", { tool_id: "marketing.web_research" }),
      makeEvent("tool_completed", { tool_id: "marketing.web_research", shadow: true }),
    ];
    const result = derivePlannedRoadmap(events);
    expect(result.roadmapActiveIndex).toBe(0);
  });

  it("falls back to contract required outputs when plan steps are missing", () => {
    const events = [
      makeEvent("llm.task_contract_completed", {
        required_outputs: ["  Summary  report ", "Key findings"],
      }),
    ];
    const result = derivePlannedRoadmap(events);
    expect(result.plannedRoadmapSteps).toHaveLength(2);
    expect(result.plannedRoadmapSteps[0].title).toBe("Summary report");
    expect(result.roadmapActiveIndex).toBe(0);
  });

  it("reads steps from event data when metadata is empty", () => {
    const events = [
      makeEvent(
        "plan_ready",
        {},
        {
          steps: [{ tool_id: "marketing.web_research", title: "Collect web sources" }],
        },
      ),
    ];
    const result = derivePlannedRoadmap(events);
    expect(result.plannedRoadmapSteps).toHaveLength(1);
    expect(result.plannedRoadmapSteps[0].toolId).toBe("marketing.web_research");
  });
});
