import { describe, expect, it } from "vitest";
import type { AgentActivityEvent } from "../../types";
import { deriveTheatreStage, desiredPreviewTabForStage } from "./deriveTheatreStage";
import { phaseForEvent } from "./helpers";
import { deriveSurfaceCommit } from "./surfaceCommitDerivation";

let eventCounter = 0;

function makeEvent({
  eventType,
  data = {},
  metadata = {},
}: {
  eventType: string;
  data?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}): AgentActivityEvent {
  return {
    event_id: `evt-${eventType}-${++eventCounter}`,
    run_id: "run-flow",
    event_type: eventType,
    title: eventType,
    detail: eventType,
    timestamp: "2026-03-10T12:00:00Z",
    data,
    metadata,
  };
}

function stageFrom(events: AgentActivityEvent[], streaming: boolean, hasApprovalGate = false): string {
  const activeEvent = events[events.length - 1] || null;
  return deriveTheatreStage({
    streaming,
    hasEvents: events.length > 0,
    activePhase: phaseForEvent(activeEvent),
    surfaceCommit: deriveSurfaceCommit(events),
    needsHumanReview: false,
    hasApprovalGate,
    isBlocked: false,
    needsInput: false,
    hasError: false,
  });
}

describe("theatre flow integration", () => {
  it("follows understand -> breakdown -> analyze -> execute -> review -> confirm -> done", () => {
    const events: AgentActivityEvent[] = [];

    events.push(makeEvent({ eventType: "task_understanding_started" }));
    expect(stageFrom(events, true)).toBe("understand");

    events.push(makeEvent({ eventType: "plan_ready" }));
    expect(stageFrom(events, true)).toBe("breakdown");

    events.push(makeEvent({ eventType: "tool_started" }));
    expect(stageFrom(events, true)).toBe("analyze");

    events.push(
      makeEvent({
        eventType: "browser_navigate",
        data: { scene_surface: "website", url: "https://example.org" },
      }),
    );
    expect(stageFrom(events, true)).toBe("execute");

    events.push(makeEvent({ eventType: "verification_completed" }));
    expect(stageFrom(events, true)).toBe("review");

    events.push(makeEvent({ eventType: "approval_required" }));
    expect(stageFrom(events, true, true)).toBe("confirm");

    events.push(makeEvent({ eventType: "email_sent" }));
    expect(stageFrom(events, false)).toBe("done");
  });

  it("keeps latest committed modality in mixed-surface execution", () => {
    const events: AgentActivityEvent[] = [
      makeEvent({
        eventType: "browser_navigate",
        data: {
          ui_target: "browser",
          ui_commit: { surface: "browser", commit: "navigate", url: "https://example.org" },
        },
      }),
      makeEvent({
        eventType: "docs.insert_text",
        data: {
          ui_target: "document",
          ui_commit: { surface: "document", commit: "open_document", url: "https://docs.google.com/document/d/1/edit" },
        },
      }),
      makeEvent({
        eventType: "sheets.update",
        data: {
          ui_target: "document",
          ui_commit: { surface: "document", commit: "open_sheet", url: "https://docs.google.com/spreadsheets/d/1/edit" },
        },
      }),
      makeEvent({
        eventType: "email_set_subject",
        data: {
          ui_target: "email",
          ui_commit: { surface: "email", commit: "email_set_subject" },
        },
      }),
    ];

    const commit = deriveSurfaceCommit(events);
    expect(commit?.tab).toBe("email");
    const tab = desiredPreviewTabForStage({
      stage: "execute",
      sceneTab: "system",
      surfaceCommit: commit,
      fallbackPreviewTab: "system",
      manualOverride: false,
    });
    expect(tab).toBe("email");
  });
});
