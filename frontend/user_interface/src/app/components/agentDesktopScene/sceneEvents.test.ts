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

  it("returns failure overlay for failed action status", () => {
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
    expect(overlay?.variant).toBe("human-alert");
    expect(overlay?.text).toContain("failed");
  });
});
