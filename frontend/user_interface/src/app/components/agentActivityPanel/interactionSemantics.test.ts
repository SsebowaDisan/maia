import { describe, expect, it } from "vitest";
import type { AgentActivityEvent } from "../../types";
import {
  agentColorFromEvent,
  agentEventTypeFromEvent,
  agentLabelFromEvent,
  cursorLabelFromSemantics,
  eventTab,
  isApiRuntimeEvent,
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

  it("supports zoom action semantics for cursor labels", () => {
    const label = cursorLabelFromSemantics({
      action: "zoom_to_region",
      actionStatus: "ok",
      actionPhase: "active",
      sceneSurfaceLabel: "Document",
      roleLabel: "Verifier",
    });
    expect(label).toContain("Verifier");
    expect(label.toLowerCase()).toContain("inspect");
  });

  it("reads agent identity and alias event type from metadata", () => {
    const event = makeEvent({
      agent_label: "Planner",
      agent_color: "#7c3aed",
      agent_event_type: "agent.handoff",
      owner_role: "planner",
    });
    expect(agentLabelFromEvent(event)).toBe("Planner");
    expect(agentColorFromEvent(event)).toBe("#7c3aed");
    expect(agentEventTypeFromEvent(event)).toBe("agent.handoff");
  });

  it("marks api scene events as api runtime events", () => {
    const event = makeEvent({
      event_family: "api",
      scene_surface: "api",
    });
    expect(eventTab(event)).toBe("system");
    expect(isApiRuntimeEvent(event)).toBe(true);
  });

  it("treats shadow events as system tab events", () => {
    const event = makeEvent(
      { scene_surface: "google_docs" },
      { shadow: true, tool_id: "workspace.docs.research_notes" },
    );
    expect(eventTab(event)).toBe("system");
  });

  it("keeps workspace logging sheet events on system tab without sheet URL signals", () => {
    const event = makeEvent(
      {
        scene_surface: "google_sheets",
        tool_id: "workspace.sheets.track_step",
        __workspace_logging_step: true,
      },
      {},
    );
    event.event_type = "tool_started";
    expect(eventTab(event)).toBe("system");
  });
});
