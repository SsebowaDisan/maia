import { describe, expect, it } from "vitest";
import type { AgentActivityEvent } from "../../types";
import { derivePhaseTimeline, phaseForEvent } from "./phaseRouting";

function makeEvent(
  eventType: string,
  options?: {
    stage?: string;
    eventFamily?: string;
    actionPhase?: string;
    title?: string;
  },
): AgentActivityEvent {
  return {
    event_id: `evt-${eventType}-${options?.stage || "none"}`,
    run_id: "run-phases",
    event_type: eventType,
    title: options?.title || eventType,
    detail: eventType,
    timestamp: "2026-03-11T10:00:00Z",
    stage: options?.stage as AgentActivityEvent["stage"],
    event_family: options?.eventFamily as AgentActivityEvent["event_family"],
    metadata: options?.actionPhase ? { action_phase: options.actionPhase } : {},
    data: {},
  };
}

describe("phaseRouting", () => {
  it("maps explicit stage metadata to canonical phases", () => {
    expect(phaseForEvent(makeEvent("custom_event", { stage: "understanding" }))).toBe("understanding");
    expect(phaseForEvent(makeEvent("custom_event", { stage: "contract" }))).toBe("contract");
    expect(phaseForEvent(makeEvent("custom_event", { stage: "clarification" }))).toBe("clarification");
    expect(phaseForEvent(makeEvent("custom_event", { stage: "planning" }))).toBe("planning");
    expect(phaseForEvent(makeEvent("custom_event", { stage: "execution" }))).toBe("execution");
    expect(phaseForEvent(makeEvent("custom_event", { stage: "verification" }))).toBe("verification");
    expect(phaseForEvent(makeEvent("custom_event", { stage: "delivery" }))).toBe("delivery");
  });

  it("maps event family hints when explicit stage is absent", () => {
    expect(phaseForEvent(makeEvent("assembly_step_added", { eventFamily: "plan" }))).toBe("planning");
    expect(phaseForEvent(makeEvent("workflow_step_started", { eventFamily: "workflow" }))).toBe(
      "execution",
    );
  });

  it("uses action_phase metadata as a fallback signal", () => {
    expect(phaseForEvent(makeEvent("foo", { actionPhase: "review" }))).toBe("verification");
  });

  it("keeps verification phase active when latest metadata says verification", () => {
    const visibleEvents = [
      makeEvent("preflight_started", { stage: "understanding" }),
      makeEvent("tool_started", { stage: "execution" }),
      makeEvent("approval_required", { stage: "verification" }),
    ];
    const timeline = derivePhaseTimeline(visibleEvents, visibleEvents[2]);
    const active = timeline.find((row) => row.state === "active");
    expect(active?.key).toBe("verification");
  });

  it("ignores interaction_suggestion events for phase mapping", () => {
    expect(phaseForEvent(makeEvent("interaction_suggestion"))).toBeNull();
  });

  it("hides clarification phase when no clarification signals exist", () => {
    const visibleEvents = [
      makeEvent("task_intake", { stage: "understanding" }),
      makeEvent("contract_decision", { stage: "contract" }),
      makeEvent("assembly_started", { stage: "planning" }),
    ];
    const timeline = derivePhaseTimeline(visibleEvents, visibleEvents[2]);
    expect(timeline.map((row) => row.key)).toEqual([
      "understanding",
      "contract",
      "planning",
      "execution",
      "verification",
      "delivery",
    ]);
  });

  it("prevents phase regression when a late contract signal arrives after planning", () => {
    const visibleEvents = [
      makeEvent("task_intake", { stage: "understanding" }),
      makeEvent("assembly_started", { stage: "planning" }),
      makeEvent("contract_backfill", { stage: "contract" }),
    ];
    const timeline = derivePhaseTimeline(visibleEvents, visibleEvents[2]);
    const active = timeline.find((row) => row.state === "active");
    expect(active?.key).toBe("planning");
  });

  it("uses user-friendly labels and event captions", () => {
    const visibleEvents = [
      makeEvent("workflow_step_started", { stage: "execution" }),
    ];
    const timeline = derivePhaseTimeline(visibleEvents, visibleEvents[0]);
    const executionRow = timeline.find((row) => row.key === "execution");
    expect(executionRow?.label).toBe("Doing the work");
    expect(String(executionRow?.latestEventTitle || "").toLowerCase()).toContain("workflow step started");
  });
});
