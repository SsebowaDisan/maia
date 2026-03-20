import { describe, expect, it } from "vitest";
import { tabForEventType } from "./tabs";

describe("tabForEventType", () => {
  it("routes approval and handoff lifecycle events to system tab", () => {
    expect(tabForEventType("approval_required")).toBe("system");
    expect(tabForEventType("approval_granted")).toBe("system");
    expect(tabForEventType("handoff_paused")).toBe("system");
    expect(tabForEventType("handoff_resumed")).toBe("system");
    expect(tabForEventType("brain_review_decision")).toBe("system");
    expect(tabForEventType("agent_dialogue_turn")).toBe("system");
    expect(tabForEventType("assembly_step_added")).toBe("system");
  });

  it("keeps browser/document routing unchanged", () => {
    expect(tabForEventType("browser_navigate")).toBe("browser");
    expect(tabForEventType("docs.insert_completed")).toBe("document");
  });
});
