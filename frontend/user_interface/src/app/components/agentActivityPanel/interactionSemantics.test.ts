import { describe, expect, it } from "vitest";
import type { AgentActivityEvent } from "../../types";
import {
  cursorLabelFromSemantics,
  eventTab,
  roleKeyFromEvent,
  roleLabelFromKey,
  sceneSurfaceFromEvent,
} from "./interactionSemantics";

function makeEvent(data: Record<string, unknown>, metadata: Record<string, unknown> = {}): AgentActivityEvent {
  return {
    event_id: "evt-1",
    run_id: "run-1",
    event_type: "docs.insert_started",
    title: "Insert doc text",
    detail: "Typing summary paragraph",
    timestamp: "2026-03-07T10:00:00Z",
    metadata,
    data,
  };
}

describe("interactionSemantics", () => {
  it("routes tab from normalized scene surface", () => {
    const event = makeEvent({ scene_surface: "google_docs" });
    expect(sceneSurfaceFromEvent(event)).toBe("google_docs");
    expect(eventTab(event)).toBe("document");
  });

  it("resolves role label from event owner role", () => {
    const event = makeEvent({ owner_role: "research" });
    const key = roleKeyFromEvent(event);
    expect(key).toBe("research");
    expect(roleLabelFromKey(key)).toBe("Research");
  });

  it("builds cursor labels from action semantics", () => {
    const label = cursorLabelFromSemantics({
      action: "extract",
      actionStatus: "ok",
      actionPhase: "active",
      sceneSurfaceLabel: "Website",
      roleLabel: "Research",
    });
    expect(label).toContain("Research");
    expect(label.toLowerCase()).toContain("evidence");
  });
});
