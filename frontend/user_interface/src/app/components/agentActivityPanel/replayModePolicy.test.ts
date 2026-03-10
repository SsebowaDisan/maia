import { describe, expect, it } from "vitest";

import type { AgentActivityEvent } from "../../types";
import { normalizeReplayMode, timelineRowsForMode } from "./replayModePolicy";

function makeEvent(index: number): AgentActivityEvent {
  return {
    event_id: `evt-${index}`,
    run_id: "run-1",
    event_type: "tool_progress",
    title: `Event ${index}`,
    detail: "",
    timestamp: "2026-03-07T12:00:00Z",
    status: "info",
    metadata: {},
    data: {},
  };
}

describe("normalizeReplayMode", () => {
  it("maps full to full_theatre and defaults to balanced", () => {
    expect(normalizeReplayMode("fast")).toBe("fast");
    expect(normalizeReplayMode("balanced")).toBe("balanced");
    expect(normalizeReplayMode("full")).toBe("full_theatre");
    expect(normalizeReplayMode("full_theatre")).toBe("full_theatre");
    expect(normalizeReplayMode("unknown")).toBe("balanced");
  });
});

describe("timelineRowsForMode", () => {
  it("keeps full fidelity for full_theatre", () => {
    const events = Array.from({ length: 28 }, (_, idx) => makeEvent(idx + 1));
    const rows = timelineRowsForMode({
      visibleEvents: events,
      safeCursor: 20,
      replayMode: "full_theatre",
    });
    expect(rows.length).toBe(events.length);
  });

  it("keeps full fidelity for fast mode", () => {
    const events = Array.from({ length: 40 }, (_, idx) => makeEvent(idx + 1));
    events[7].replay_importance = "high";
    const rows = timelineRowsForMode({
      visibleEvents: events,
      safeCursor: 29,
      replayMode: "fast",
    });
    expect(rows.length).toBe(events.length);
    expect(rows.some((row) => row.index === 29)).toBe(true);
    expect(rows.some((row) => row.index === 7)).toBe(true);
  });
});
