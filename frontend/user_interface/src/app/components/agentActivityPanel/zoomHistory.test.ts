import { describe, expect, it } from "vitest";

import type { AgentActivityEvent } from "../../types";
import { appendZoomHistory, collectReferenceTokens } from "./zoomHistory";

function makeEvent(overrides: Partial<AgentActivityEvent> = {}): AgentActivityEvent {
  return {
    event_id: "evt-1",
    run_id: "run-1",
    event_type: "pdf_zoom_to_region",
    title: "Zoom",
    detail: "Inspect table",
    timestamp: "2026-03-07T15:10:30Z",
    metadata: {},
    ...overrides,
  };
}

describe("zoomHistory helpers", () => {
  it("collects fallback reference tokens from payload and event id", () => {
    const event = makeEvent({ event_id: "evt-44" });
    const refs = collectReferenceTokens(event, {
      graph_node_id: "node-44",
      scene_ref: "scene.pdf.reader",
    });
    expect(refs.graphNodeIds).toEqual(["node-44"]);
    expect(refs.sceneRefs).toEqual(["scene.pdf.reader"]);
    expect(refs.eventRefs).toEqual(["evt-44"]);
  });

  it("appends zoom history entry from embedded zoom_event payload", () => {
    const event = makeEvent({
      event_id: "evt-9",
      event_type: "pdf_zoom_to_region",
      event_index: 9,
    });
    const next = appendZoomHistory([], event, {
      zoom_event: {
        event_ref: "evt-9",
        event_type: "pdf_zoom_to_region",
        event_index: 9,
        action: "zoom_to_region",
        scene_surface: "document",
        scene_ref: "scene.pdf.reader",
        graph_node_id: "node-pdf-9",
        zoom_level: 2.2,
        zoom_reason: "verifier escalation",
        zoom_policy_triggers: ["verifier_escalation"],
      },
    });
    expect(next).toHaveLength(1);
    expect(next[0]?.eventRef).toBe("evt-9");
    expect(next[0]?.action).toBe("zoom_to_region");
    expect(next[0]?.sceneRef).toBe("scene.pdf.reader");
    expect(next[0]?.graphNodeId).toBe("node-pdf-9");
    expect(next[0]?.zoomReason).toBe("verifier escalation");
  });
});
