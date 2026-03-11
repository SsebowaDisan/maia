import { describe, expect, it } from "vitest";
import type { AgentActivityEvent } from "../../types";
import { styleForEvent } from "./styles";

function makeVerificationEvent(status: string): AgentActivityEvent {
  return {
    event_id: `evt-${status}`,
    run_id: "run-style",
    event_type: "verification_check",
    title: "Check",
    detail: "",
    timestamp: "2026-03-11T09:00:00Z",
    metadata: { status },
    data: {},
  };
}

describe("styleForEvent", () => {
  it("uses warning accent for verification warnings", () => {
    const style = styleForEvent(makeVerificationEvent("warning"));
    expect(style.label).toBe("Check Warning");
    expect(style.accent).toBe("text-[#b45309]");
  });

  it("uses fail accent for verification failures", () => {
    const style = styleForEvent(makeVerificationEvent("fail"));
    expect(style.label).toBe("Check Failed");
    expect(style.accent).toBe("text-[#9b1c1c]");
  });

  it("uses pass accent for verification pass", () => {
    const style = styleForEvent(makeVerificationEvent("pass"));
    expect(style.label).toBe("Check Passed");
    expect(style.accent).toBe("text-[#2f6a3f]");
  });
});
