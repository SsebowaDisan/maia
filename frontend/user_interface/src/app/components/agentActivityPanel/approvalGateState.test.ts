import { describe, expect, it } from "vitest";
import type { AgentActivityEvent } from "../../types";
import { latestOpenApprovalEvent } from "./approvalGateState";

function makeEvent(eventType: string, eventId: string): AgentActivityEvent {
  return {
    event_id: eventId,
    run_id: "run-approval",
    event_type: eventType,
    title: eventType,
    detail: eventType,
    timestamp: "2026-03-11T12:00:00Z",
    metadata: {},
    data: {},
  };
}

describe("latestOpenApprovalEvent", () => {
  it("returns latest approval_required when no grant follows", () => {
    const events = [
      makeEvent("tool_started", "evt-1"),
      makeEvent("approval_required", "evt-2"),
    ];
    expect(latestOpenApprovalEvent(events)?.event_id).toBe("evt-2");
  });

  it("returns null when approval_granted happens after approval_required", () => {
    const events = [
      makeEvent("approval_required", "evt-1"),
      makeEvent("approval_granted", "evt-2"),
    ];
    expect(latestOpenApprovalEvent(events)).toBeNull();
  });

  it("keeps gate open if a new approval_required appears after a previous grant", () => {
    const events = [
      makeEvent("approval_required", "evt-1"),
      makeEvent("approval_granted", "evt-2"),
      makeEvent("approval_required", "evt-3"),
    ];
    expect(latestOpenApprovalEvent(events)?.event_id).toBe("evt-3");
  });
});
