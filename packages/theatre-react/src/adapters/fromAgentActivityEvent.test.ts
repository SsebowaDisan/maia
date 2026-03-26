import { describe, expect, it } from "vitest";
import { fromAgentActivityEvent } from "./fromAgentActivityEvent";

describe("fromAgentActivityEvent", () => {
  it("maps Maia browser events into ACP execution events", () => {
    const converted = fromAgentActivityEvent({
      event_id: "evt_1",
      run_id: "run_1",
      seq: 7,
      stage: "execute",
      status: "running",
      event_type: "computer_use_action",
      title: "Computer Use",
      detail: "Running action: click",
      timestamp: "2026-03-26T12:00:00Z",
      data: {
        scene_surface: "browser",
        scene_family: "browser",
        url: "https://example.com",
        action: "click",
        computer_use_session_id: "session_1",
        computer_use_task: "Inspect the page",
      },
      metadata: {
        agent_id: "agent://browser",
      },
    });

    expect(converted.event_type).toBe("event");
    expect(converted.agent_id).toBe("agent://browser");
    expect(converted.payload.activity).toBe("browsing");
    expect(converted.payload.browser?.url).toBe("https://example.com");
    expect(converted.payload.execution?.scene_surface).toBe("browser");
    expect(converted.payload.execution?.browser_state?.computer_use_session_id).toBe("session_1");
  });
});
