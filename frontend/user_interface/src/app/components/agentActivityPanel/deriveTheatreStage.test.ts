import { describe, expect, it } from "vitest";
import { deriveTheatreStage, desiredPreviewTabForStage } from "./deriveTheatreStage";

describe("deriveTheatreStage", () => {
  it("keeps system-first during understanding without commits", () => {
    const stage = deriveTheatreStage({
      streaming: true,
      hasEvents: true,
      activeStageSignal: "understanding",
      activeEventType: "task_understanding_started",
      activeEventStatus: "running",
      activeEventTitle: "Task understanding started",
      surfaceCommit: null,
      needsHumanReview: false,
      hasApprovalGate: false,
      isBlocked: false,
      needsInput: false,
      hasError: false,
    });
    expect(stage).toBe("understand");
  });

  it("stays in analyze during execution until a surface commit exists", () => {
    const stage = deriveTheatreStage({
      streaming: true,
      hasEvents: true,
      activeStageSignal: "execution",
      activeEventType: "tool_started",
      activeEventStatus: "running",
      activeEventTitle: "Tool started",
      surfaceCommit: null,
      needsHumanReview: false,
      hasApprovalGate: false,
      isBlocked: false,
      needsInput: false,
      hasError: false,
    });
    expect(stage).toBe("analyze");
  });

  it("moves to execute once a surface commit exists", () => {
    const stage = deriveTheatreStage({
      streaming: true,
      hasEvents: true,
      activeStageSignal: "execution",
      activeEventType: "browser_navigate",
      activeEventStatus: "running",
      activeEventTitle: "Browser navigate",
      surfaceCommit: {
        tab: "browser",
        surface: "website",
        subtype: "website",
        sourceUrl: "https://example.org",
        committedEventId: "evt-1",
        committedAt: "2026-03-10T12:00:00Z",
        confidence: "high",
      },
      needsHumanReview: false,
      hasApprovalGate: false,
      isBlocked: false,
      needsInput: false,
      hasError: false,
    });
    expect(stage).toBe("execute");
  });

  it("routes to blocked when blocked signal is present", () => {
    const stage = deriveTheatreStage({
      streaming: true,
      hasEvents: true,
      activeStageSignal: "execution",
      activeEventType: "policy_blocked",
      activeEventStatus: "failed",
      activeEventTitle: "Blocked",
      surfaceCommit: null,
      needsHumanReview: false,
      hasApprovalGate: false,
      isBlocked: true,
      needsInput: false,
      hasError: false,
    });
    expect(stage).toBe("blocked");
  });

  it("routes to needs_input before execution", () => {
    const stage = deriveTheatreStage({
      streaming: true,
      hasEvents: true,
      activeStageSignal: "planning",
      activeEventType: "llm.clarification_requested",
      activeEventStatus: "waiting",
      activeEventTitle: "Need input",
      surfaceCommit: null,
      needsHumanReview: false,
      hasApprovalGate: false,
      isBlocked: false,
      needsInput: true,
      hasError: false,
    });
    expect(stage).toBe("needs_input");
  });

  it("routes to confirm when approval is required", () => {
    const stage = deriveTheatreStage({
      streaming: true,
      hasEvents: true,
      activeStageSignal: "verification",
      activeEventType: "approval_required",
      activeEventStatus: "waiting",
      activeEventTitle: "Approval required",
      surfaceCommit: null,
      needsHumanReview: false,
      hasApprovalGate: true,
      isBlocked: false,
      needsInput: false,
      hasError: false,
    });
    expect(stage).toBe("confirm");
  });
});

describe("desiredPreviewTabForStage", () => {
  it("keeps browser tab during breakdown when a browser scene is already active", () => {
    const tab = desiredPreviewTabForStage({
      stage: "breakdown",
      sceneTab: "browser",
      surfaceCommit: null,
      fallbackPreviewTab: "browser",
      manualOverride: false,
    });
    expect(tab).toBe("browser");
  });

  it("uses committed tab for execute stage", () => {
    const tab = desiredPreviewTabForStage({
      stage: "execute",
      sceneTab: "system",
      surfaceCommit: {
        tab: "email",
        surface: "email",
        subtype: "email",
        sourceUrl: "",
        committedEventId: "evt-2",
        committedAt: "2026-03-10T12:10:00Z",
        confidence: "high",
      },
      fallbackPreviewTab: "system",
      manualOverride: false,
    });
    expect(tab).toBe("email");
  });
});
