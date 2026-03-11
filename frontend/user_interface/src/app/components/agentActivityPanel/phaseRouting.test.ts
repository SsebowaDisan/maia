import { describe, expect, it } from "vitest";
import type { AgentActivityEvent } from "../../types";
import { derivePhaseTimeline, phaseForEvent } from "./phaseRouting";

function makeEvent(eventType: string): AgentActivityEvent {
  return {
    event_id: `evt-${eventType}`,
    run_id: "run-phases",
    event_type: eventType,
    title: eventType,
    detail: eventType,
    timestamp: "2026-03-11T10:00:00Z",
    metadata: {},
    data: {},
  };
}

describe("phaseRouting", () => {
  it("maps preflight events to understanding", () => {
    expect(phaseForEvent(makeEvent("preflight_started"))).toBe("understanding");
    expect(phaseForEvent(makeEvent("preflight_completed"))).toBe("understanding");
  });

  it("maps approval and handoff events to verification", () => {
    expect(phaseForEvent(makeEvent("approval_required"))).toBe("verification");
    expect(phaseForEvent(makeEvent("approval_granted"))).toBe("verification");
    expect(phaseForEvent(makeEvent("handoff_paused"))).toBe("verification");
    expect(phaseForEvent(makeEvent("handoff_resumed"))).toBe("verification");
    expect(phaseForEvent(makeEvent("agent.waiting"))).toBe("verification");
    expect(phaseForEvent(makeEvent("agent.handoff"))).toBe("verification");
  });

  it("keeps verification phase active during agent.waiting", () => {
    const visibleEvents = [
      makeEvent("task_understanding_started"),
      makeEvent("tool_started"),
      makeEvent("agent.waiting"),
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
      makeEvent("task_understanding_started"),
      makeEvent("llm.task_contract_completed"),
      makeEvent("planning_started"),
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

  it("prevents phase regression when a late contract event arrives after planning", () => {
    const visibleEvents = [
      makeEvent("task_understanding_started"),
      makeEvent("planning_started"),
      makeEvent("llm.task_contract_started"),
    ];
    const timeline = derivePhaseTimeline(visibleEvents, visibleEvents[2]);
    const active = timeline.find((row) => row.state === "active");
    expect(active?.key).toBe("planning");
  });
});
