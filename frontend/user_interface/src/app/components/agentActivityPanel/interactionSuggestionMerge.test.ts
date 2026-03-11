import { describe, expect, it, vi } from "vitest";
import type { AgentActivityEvent } from "../../types";
import {
  extractSuggestionLayer,
  INTERACTION_SUGGESTION_MIN_CONFIDENCE,
  mergeSuggestion,
  suggestionLookupKeyForEvent,
} from "./interactionSuggestionMerge";

function makeEvent(
  eventType: string,
  overrides: Partial<AgentActivityEvent> = {},
): AgentActivityEvent {
  return {
    event_id: overrides.event_id || `${eventType}-id`,
    run_id: overrides.run_id || "run-1",
    event_type: eventType,
    title: overrides.title || eventType,
    detail: overrides.detail || "",
    timestamp: overrides.timestamp || "2026-03-11T09:00:00Z",
    metadata: overrides.metadata || {},
    data: overrides.data || {},
    status: overrides.status,
  };
}

describe("extractSuggestionLayer", () => {
  it("returns empty map for empty arrays", () => {
    expect(extractSuggestionLayer([]).size).toBe(0);
  });

  it("keeps only interaction_suggestion events", () => {
    const events = [
      makeEvent("tool_started"),
      makeEvent("interaction_suggestion", {
        metadata: { step_index: 2 },
        data: { advisory: true, __no_execution: true, confidence: 0.7 },
      }),
    ];
    const layer = extractSuggestionLayer(events);
    expect(layer.size).toBe(1);
  });

  it("rejects suggestions without advisory guard", () => {
    const events = [
      makeEvent("interaction_suggestion", {
        metadata: { step_index: 2 },
        data: { advisory: false, __no_execution: true, confidence: 0.8 },
      }),
    ];
    expect(extractSuggestionLayer(events).size).toBe(0);
  });

  it("rejects suggestions without __no_execution guard", () => {
    const events = [
      makeEvent("interaction_suggestion", {
        metadata: { step_index: 2 },
        data: { advisory: true, __no_execution: false, confidence: 0.8 },
      }),
    ];
    expect(extractSuggestionLayer(events).size).toBe(0);
  });

  it("keys suggestions by run_id + step_index", () => {
    const event = makeEvent("interaction_suggestion", {
      run_id: "run-22",
      metadata: { step_index: 9 },
      data: { advisory: true, __no_execution: true, confidence: 0.72 },
    });
    const layer = extractSuggestionLayer([event]);
    expect(layer.has("run-22:9")).toBe(true);
  });

  it("stores multiple valid suggestions for different step indexes", () => {
    const events = [
      makeEvent("interaction_suggestion", {
        metadata: { step_index: 1 },
        data: { advisory: true, __no_execution: true, confidence: 0.66 },
      }),
      makeEvent("interaction_suggestion", {
        event_id: "s2",
        metadata: { step_index: 2 },
        data: { advisory: true, __no_execution: true, confidence: 0.88 },
      }),
    ];
    const layer = extractSuggestionLayer(events);
    expect(layer.size).toBe(2);
    expect(layer.get("run-1:1")?.[0]?.confidence).toBe(0.66);
    expect(layer.get("run-1:2")?.[0]?.confidence).toBe(0.88);
  });

  it("appends multiple suggestions for the same step key", () => {
    const events = [
      makeEvent("interaction_suggestion", {
        metadata: { step_index: 2 },
        data: { advisory: true, __no_execution: true, confidence: 0.44 },
      }),
      makeEvent("interaction_suggestion", {
        event_id: "s-same-step-2",
        metadata: { step_index: 2 },
        data: { advisory: true, __no_execution: true, confidence: 0.81 },
      }),
    ];
    const layer = extractSuggestionLayer(events);
    expect(layer.get("run-1:2")?.map((entry) => entry.confidence)).toEqual([0.44, 0.81]);
  });
});

describe("suggestionLookupKeyForEvent", () => {
  it("uses run_id + step_index when available", () => {
    const event = makeEvent("tool_started", {
      run_id: "run-2",
      metadata: { step_index: 4 },
    });
    expect(suggestionLookupKeyForEvent(event)).toBe("run-2:4");
  });

  it("falls back to event_id when step index is missing", () => {
    const event = makeEvent("tool_started", { event_id: "evt-fallback" });
    expect(suggestionLookupKeyForEvent(event)).toBe("evt-fallback");
  });
});

describe("mergeSuggestion", () => {
  const suggestion = {
    action: "scroll",
    targetLabel: "Main content",
    cursorX: 62,
    cursorY: 34,
    scrollPercent: 72,
    confidence: 0.9,
    reason: "Likely reading section",
    advisory: true as const,
    noExecution: true as const,
    source: "llm_suggestion" as const,
    stepIndex: 2,
    eventId: "sg-1",
    runId: "run-1",
  };

  it("prefers deterministic cursor coordinates over suggestion", () => {
    const merged = mergeSuggestion(12, 24, "click", "Submit", 30, [suggestion]);
    expect(merged.source).toBe("deterministic");
    expect(merged.cursorX).toBe(12);
    expect(merged.cursorY).toBe(24);
  });

  it("falls through to suggestion when deterministic cursor is incomplete", () => {
    const merged = mergeSuggestion(12, null, "", "", null, [suggestion]);
    expect(merged.source).toBe("suggested");
    expect(merged.cursorX).toBe(62);
    expect(merged.cursorY).toBe(34);
  });

  it("uses the highest-confidence suggestion when multiple exist", () => {
    const merged = mergeSuggestion(12, null, "", "", null, [
      { ...suggestion, confidence: 0.58, cursorX: 21, cursorY: 22 },
      { ...suggestion, confidence: 0.92, cursorX: 84, cursorY: 48 },
      { ...suggestion, confidence: 0.81, cursorX: 40, cursorY: 36 },
    ]);
    expect(merged.source).toBe("suggested");
    expect(merged.cursorX).toBe(84);
    expect(merged.cursorY).toBe(48);
    expect(merged.suggestionConfidence).toBe(0.92);
  });

  it("rejects low-confidence suggestions", () => {
    const onRejected = vi.fn();
    const merged = mergeSuggestion(
      null,
      null,
      "",
      "",
      null,
      [{ ...suggestion, confidence: INTERACTION_SUGGESTION_MIN_CONFIDENCE - 0.01 }],
      INTERACTION_SUGGESTION_MIN_CONFIDENCE,
      { x: 88, y: 51 },
      onRejected,
    );
    expect(merged.source).toBe("synthetic_fallback");
    expect(onRejected).toHaveBeenCalledWith("low_confidence", expect.any(Object));
  });

  it("accepts threshold boundary confidence", () => {
    const merged = mergeSuggestion(
      null,
      null,
      "",
      "",
      null,
      [{ ...suggestion, confidence: INTERACTION_SUGGESTION_MIN_CONFIDENCE }],
      INTERACTION_SUGGESTION_MIN_CONFIDENCE,
    );
    expect(merged.source).toBe("suggested");
  });

  it("rejects missing advisory guard regardless of confidence", () => {
    const onRejected = vi.fn();
    const merged = mergeSuggestion(
      null,
      null,
      "",
      "",
      null,
      [{ ...suggestion, advisory: false as true }],
      INTERACTION_SUGGESTION_MIN_CONFIDENCE,
      { x: 58, y: 50 },
      onRejected,
    );
    expect(merged.source).toBe("synthetic_fallback");
    expect(onRejected).toHaveBeenCalledWith("missing_advisory_guard", expect.any(Object));
  });

  it("rejects missing __no_execution guard regardless of confidence", () => {
    const onRejected = vi.fn();
    const merged = mergeSuggestion(
      null,
      null,
      "",
      "",
      null,
      [{ ...suggestion, noExecution: false as true }],
      INTERACTION_SUGGESTION_MIN_CONFIDENCE,
      { x: 58, y: 50 },
      onRejected,
    );
    expect(merged.source).toBe("synthetic_fallback");
    expect(onRejected).toHaveBeenCalledWith("missing_advisory_guard", expect.any(Object));
  });

  it("uses suggestion scroll_percent only when merged action is scroll", () => {
    const merged = mergeSuggestion(null, null, "", "", null, [suggestion]);
    expect(merged.source).toBe("suggested");
    expect(merged.scrollPercent).toBe(72);
  });

  it("keeps deterministic scroll percent over suggestion", () => {
    const merged = mergeSuggestion(null, null, "", "", 45, [suggestion]);
    expect(merged.source).toBe("suggested");
    expect(merged.scrollPercent).toBe(45);
  });

  it("does not apply suggestion scroll percent for non-scroll action", () => {
    const merged = mergeSuggestion(
      null,
      null,
      "",
      "",
      null,
      [{ ...suggestion, action: "click", scrollPercent: 72 }],
    );
    expect(merged.source).toBe("suggested");
    expect(merged.scrollPercent).toBeNull();
  });

  it("returns none when deterministic, suggestion, and synthetic fallback are absent", () => {
    const merged = mergeSuggestion(null, null, "", "", null, null, INTERACTION_SUGGESTION_MIN_CONFIDENCE, null);
    expect(merged.source).toBe("none");
    expect(merged.cursorX).toBeNull();
    expect(merged.cursorY).toBeNull();
  });
});
