import { describe, expect, it } from "vitest";
import type { AgentActivityEvent } from "../../types";
import { resolveBrowserUrl } from "./contentDerivation";

function makeEvent({
  eventType,
  title,
  detail,
  data = {},
  metadata = {},
}: {
  eventType: string;
  title: string;
  detail: string;
  data?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}): AgentActivityEvent {
  return {
    event_id: `evt-${eventType}`,
    run_id: "run-1",
    event_type: eventType,
    title,
    detail,
    timestamp: "2026-03-10T12:00:00Z",
    data,
    metadata,
  };
}

describe("resolveBrowserUrl", () => {
  it("reads URL from nested action_target in browser policy events", () => {
    const events = [
      makeEvent({
        eventType: "browser_interaction_policy",
        title: "Review browser interaction safety",
        detail: "No explicit click/fill actions requested.",
        data: {
          scene_surface: "website",
          action_target: {
            url: "https://axongroup.com/",
          },
        },
      }),
    ];
    expect(resolveBrowserUrl(events)).toBe("https://axongroup.com/");
  });

  it("reads URL from top_urls payload rows when direct url is absent", () => {
    const events = [
      makeEvent({
        eventType: "brave.search.results",
        title: "Brave results",
        detail: "Captured URL rows",
        data: {
          scene_surface: "website",
          top_urls: [
            "https://example.org/one",
            "https://example.org/two",
          ],
        },
      }),
    ];
    expect(resolveBrowserUrl(events)).toBe("https://example.org/two");
  });

  it("extracts URL from detail text for browser-like events", () => {
    const events = [
      makeEvent({
        eventType: "tool_started",
        title: "Inspect website",
        detail: "Opening https://axongroup.com/overview for inspection",
        metadata: {
          scene_surface: "website",
          tool_id: "browser.playwright.inspect",
        },
      }),
    ];
    expect(resolveBrowserUrl(events)).toBe("https://axongroup.com/overview");
  });

  it("falls back to a website URL when browser scene tagging is missing", () => {
    const events = [
      makeEvent({
        eventType: "tool_completed",
        title: "Workspace logging",
        detail: "Updated document",
        data: {
          source_url: "https://docs.google.com/document/d/abc123/edit",
          scene_surface: "google_docs",
        },
      }),
      makeEvent({
        eventType: "tool_started",
        title: "Planning execution",
        detail: "Primary source https://axongroup.com/company",
        data: {
          source_url: "https://axongroup.com/company",
        },
      }),
    ];
    expect(resolveBrowserUrl(events)).toBe("https://axongroup.com/company");
  });
});
