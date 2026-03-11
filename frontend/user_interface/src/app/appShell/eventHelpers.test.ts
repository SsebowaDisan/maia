import { describe, expect, it } from "vitest";
import { extractAgentEvents, splitAgentEventsBySuggestionType } from "./eventHelpers";

function makeRawEvent(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    event_id: "evt-1",
    run_id: "run-1",
    event_type: "tool_started",
    title: "Tool started",
    detail: "",
    timestamp: "2026-03-11T08:00:00Z",
    metadata: {},
    ...overrides,
  };
}

describe("extractAgentEvents", () => {
  it("supports flat AgentActivityEvent[] rows", () => {
    const rows = [makeRawEvent({ event_id: "evt-flat" })];
    const events = extractAgentEvents(rows);
    expect(events).toHaveLength(1);
    expect(events[0]?.event_id).toBe("evt-flat");
  });

  it("supports wrapped rows and maps event.payload -> event.data when needed", () => {
    const rows = [
      {
        type: "event",
        payload: makeRawEvent({
          event_id: "evt-wrapped",
          payload: { status: "warning" },
        }),
      },
    ];
    const events = extractAgentEvents(rows);
    expect(events).toHaveLength(1);
    expect(events[0]?.event_id).toBe("evt-wrapped");
    expect(events[0]?.data?.status).toBe("warning");
  });

  it("ignores non-event rows", () => {
    const rows = [
      { type: "ready", payload: { ok: true } },
      { type: "event", payload: makeRawEvent({ event_id: "evt-ok" }) },
    ];
    const events = extractAgentEvents(rows);
    expect(events).toHaveLength(1);
    expect(events[0]?.event_id).toBe("evt-ok");
  });
});

describe("splitAgentEventsBySuggestionType", () => {
  it("separates interaction_suggestion events from primary events", () => {
    const rows = [
      makeRawEvent({ event_id: "evt-tool", event_type: "tool_started" }),
      makeRawEvent({ event_id: "evt-suggestion", event_type: "interaction_suggestion" }),
    ];
    const events = extractAgentEvents(rows);
    const split = splitAgentEventsBySuggestionType(events);
    expect(split.primaryEvents.map((event) => event.event_id)).toEqual(["evt-tool"]);
    expect(split.suggestionEvents.map((event) => event.event_id)).toEqual(["evt-suggestion"]);
  });
});
