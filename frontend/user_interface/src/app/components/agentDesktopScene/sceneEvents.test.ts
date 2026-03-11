import { describe, expect, it } from "vitest";
import { overlayForInteractionEvent } from "./sceneEvents";

describe("overlayForInteractionEvent", () => {
  it("maps normalized navigate action to a centered overlay", () => {
    const overlay = overlayForInteractionEvent({
      eventType: "browser_navigate",
      sceneSurface: "website",
      activeDetail: "Opening source page",
      scrollDirection: "",
      action: "navigate",
      actionPhase: "active",
      actionStatus: "ok",
      actionTargetLabel: "https://example.com",
    });
    expect(overlay).not.toBeNull();
    expect(overlay?.variant).toBe("center-pill");
    expect(overlay?.text).toContain("Opening");
  });

  it("returns human alert for approval barriers", () => {
    const overlay = overlayForInteractionEvent({
      eventType: "approval_required",
      sceneSurface: "email",
      activeDetail: "Awaiting confirmation before send",
      scrollDirection: "",
      action: "verify",
      actionPhase: "active",
      actionStatus: "ok",
      actionTargetLabel: "Send",
    });
    expect(overlay).not.toBeNull();
    expect(overlay?.variant).toBe("human-alert");
    expect(overlay?.text).toContain("Human verification");
  });

  it("renders waiting overlay with distinct copy for agent.waiting", () => {
    const overlay = overlayForInteractionEvent({
      eventType: "agent.waiting",
      sceneSurface: "system",
      activeDetail: "",
      scrollDirection: "",
      action: "",
      actionPhase: "",
      actionStatus: "ok",
      actionTargetLabel: "",
    });
    expect(overlay).not.toBeNull();
    expect(overlay?.variant).toBe("human-alert");
    expect(overlay?.text).toContain("Waiting for your input");
  });

  it("renders paused copy for handoff_paused", () => {
    const overlay = overlayForInteractionEvent({
      eventType: "handoff_paused",
      sceneSurface: "system",
      activeDetail: "",
      scrollDirection: "",
      action: "",
      actionPhase: "",
      actionStatus: "ok",
      actionTargetLabel: "",
    });
    expect(overlay).not.toBeNull();
    expect(overlay?.variant).toBe("human-alert");
    expect(overlay?.text).toContain("Paused for human review");
  });

  it("shows resume chip for handoff_resumed", () => {
    const overlay = overlayForInteractionEvent({
      eventType: "handoff_resumed",
      sceneSurface: "system",
      activeDetail: "",
      scrollDirection: "",
      action: "",
      actionPhase: "",
      actionStatus: "ok",
      actionTargetLabel: "",
    });
    expect(overlay).not.toBeNull();
    expect(overlay?.variant).toBe("left-chip");
    expect(overlay?.text).toContain("Resumed after verification");
  });

  it("returns compact retry overlay for failed action status", () => {
    const overlay = overlayForInteractionEvent({
      eventType: "docs.insert_completed",
      sceneSurface: "google_docs",
      activeDetail: "Insert failed due to rate limit",
      scrollDirection: "",
      action: "type",
      actionPhase: "failed",
      actionStatus: "failed",
      actionTargetLabel: "Body",
    });
    expect(overlay).not.toBeNull();
    expect(overlay?.variant).toBe("left-chip");
    expect(overlay?.text.toLowerCase()).toContain("retry");
  });

  it("maps zoom actions to focused overlay text", () => {
    const overlay = overlayForInteractionEvent({
      eventType: "pdf_zoom_to_region",
      sceneSurface: "document",
      activeDetail: "Inspecting small table text",
      scrollDirection: "",
      action: "zoom_to_region",
      actionPhase: "active",
      actionStatus: "ok",
      actionTargetLabel: "totals table",
    });
    expect(overlay).not.toBeNull();
    expect(overlay?.text.toLowerCase()).toContain("zoom");
  });

  it("renders agent handoff overlays", () => {
    const overlay = overlayForInteractionEvent({
      eventType: "agent.handoff",
      sceneSurface: "website",
      activeDetail: "Planner to Browser handoff",
      scrollDirection: "",
      action: "",
      actionPhase: "",
      actionStatus: "info",
      actionTargetLabel: "",
    });
    expect(overlay).not.toBeNull();
    expect(overlay?.text.toLowerCase()).toContain("handing off");
  });

  it("maps api extract actions to record-centric overlays", () => {
    const overlay = overlayForInteractionEvent({
      eventType: "api_call_started",
      sceneSurface: "api",
      activeDetail: "Fetching analytics report",
      scrollDirection: "",
      action: "extract",
      actionPhase: "active",
      actionStatus: "ok",
      actionTargetLabel: "",
    });
    expect(overlay).not.toBeNull();
    expect(overlay?.text.toLowerCase()).toContain("record");
  });
});
