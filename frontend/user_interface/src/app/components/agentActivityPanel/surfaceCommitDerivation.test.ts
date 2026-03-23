import { describe, expect, it } from "vitest";
import type { AgentActivityEvent } from "../../types";
import { deriveSurfaceCommit } from "./surfaceCommitDerivation";

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
    event_id: `evt-${eventType}`,
    run_id: "run-1",
    event_type: eventType,
    title: "step",
    detail: "detail",
    timestamp: "2026-03-10T12:00:00Z",
    data,
    metadata,
  };
}

describe("deriveSurfaceCommit", () => {
  it("commits browser from browser-like URL evidence", () => {
    const commit = deriveSurfaceCommit([
      makeEvent({
        eventType: "browser_navigate",
        data: {
          scene_surface: "website",
          url: "https://example.org",
        },
      }),
    ]);
    expect(commit?.tab).toBe("browser");
    expect(commit?.sourceUrl).toBe("https://example.org");
  });

  it("commits from ui_commit metadata on mixed legacy streams", () => {
    const commit = deriveSurfaceCommit([
      makeEvent({
        eventType: "tool_progress",
        data: {
          ui_target: "browser",
          ui_commit: {
            surface: "browser",
            commit: "navigate",
            url: "https://example.org/committed",
          },
        },
      }),
    ]);
    expect(commit?.tab).toBe("browser");
    expect(commit?.sourceUrl).toBe("https://example.org/committed");
  });

  it("commits document when spreadsheet URL is emitted", () => {
    const commit = deriveSurfaceCommit([
      makeEvent({
        eventType: "sheets.update",
        data: {
          scene_surface: "google_sheets",
          spreadsheet_url: "https://docs.google.com/spreadsheets/d/abc123/edit",
        },
      }),
    ]);
    expect(commit?.tab).toBe("document");
    expect(commit?.subtype).toBe("google_sheets");
  });

  it("does not commit surface from planning-only URL text without surface signals", () => {
    const commit = deriveSurfaceCommit([
      makeEvent({
        eventType: "plan_ready",
        data: {
          source_url: "https://example.org",
        },
      }),
    ]);
    expect(commit).toBeNull();
  });

  it("commits email when ui_target indicates email on generic event", () => {
    const commit = deriveSurfaceCommit([
      makeEvent({
        eventType: "tool_progress",
        data: {
          ui_target: "email",
          ui_commit: {
            surface: "email",
            commit: "email_set_subject",
          },
        },
      }),
    ]);
    expect(commit?.tab).toBe("email");
  });

  it("does not let team chat override an earlier browser surface commit", () => {
    const commit = deriveSurfaceCommit([
      makeEvent({
        eventType: "browser_navigate",
        data: {
          scene_surface: "website",
          url: "https://www.itransition.com/machine-learning/statistics",
        },
      }),
      makeEvent({
        eventType: "team_chat_message",
        data: {
          scene_surface: "team_chat",
          scene_family: "chat",
        },
        metadata: {
          scene_surface: "team_chat",
          scene_family: "chat",
        },
      }),
    ]);
    expect(commit?.tab).toBe("browser");
    expect(commit?.sourceUrl).toBe("https://www.itransition.com/machine-learning/statistics");
  });
});
