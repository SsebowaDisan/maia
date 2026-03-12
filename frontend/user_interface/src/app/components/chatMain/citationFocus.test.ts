import { describe, expect, it } from "vitest";
import type { EvidenceCard } from "../../utils/infoInsights";
import {
  parseEvidenceRefId,
  resolveCitationAnchorInteractionPolicy,
  resolveCitationFocusFromAnchor,
  shouldOpenCitationSourceUrlForPointerEvent,
} from "./citationFocus";

function makeAnchor(attributes: Record<string, string>, textContent: string): HTMLAnchorElement {
  const host = {
    textContent: `Claim sentence with support ${textContent}`,
  } as Element;
  const node = {
    getAttribute: (key: string) => attributes[key] ?? null,
    hasAttribute: (key: string) => Object.prototype.hasOwnProperty.call(attributes, key),
    textContent,
    closest: () => host,
    parentElement: host,
  };
  return node as unknown as HTMLAnchorElement;
}

describe("citationFocus", () => {
  it("parses evidence ref id from citation attributes", () => {
    const anchor = makeAnchor({ "data-evidence-id": "evidence-12" }, "[12]");
    expect(parseEvidenceRefId(anchor)).toBe("evidence-12");
  });

  it("resolves citation focus from anchor and evidence card metadata", () => {
    const cards: EvidenceCard[] = [
      {
        id: "evidence-1",
        title: "Source A",
        source: "https://example.com/report",
        sourceUrl: "https://example.com/report",
        extract: "Quarterly revenue increased by 11 percent.",
        page: "3",
        selector: "article p:nth-of-type(1)",
        strengthTier: 3,
        matchQuality: "exact",
      },
    ];
    const anchor = makeAnchor(
      {
        "data-evidence-id": "evidence-1",
        "data-source-url": "https://example.com/report",
        "data-selector": "article p:nth-of-type(4)",
        "data-citation-number": "1",
      },
      "[1]",
    );
    const resolved = resolveCitationFocusFromAnchor({
      turn: { user: "u", assistant: "a", info: "i", attachments: [] },
      citationAnchor: anchor,
      evidenceCards: cards,
    });
    expect(resolved.focus.evidenceId).toBe("evidence-1");
    expect(resolved.focus.sourceUrl).toBe("https://example.com/report");
    expect(resolved.focus.selector).toBe("article p:nth-of-type(4)");
    expect(resolved.focus.extract.toLowerCase()).toContain("revenue");
    expect(resolved.strengthTierResolved).toBe(3);
  });

  it("marks web-only citations for direct primary open", () => {
    const anchor = makeAnchor(
      {
        "data-source-url": "https://example.com/report",
      },
      "[1]",
    );
    const policy = resolveCitationAnchorInteractionPolicy(anchor);
    expect(policy.sourceUrl).toBe("https://example.com/report");
    expect(policy.directOpenUrl).toBe("https://example.com/report");
    expect(policy.hasUsableFileId).toBe(false);
    expect(policy.openDirectOnPrimaryClick).toBe(true);
  });

  it("opens internal viewer urls directly even when a file id is present", () => {
    const anchor = makeAnchor(
      {
        "data-file-id": "file_123",
        "data-viewer-url": "/api/uploads/files/file_123/raw#page=4",
      },
      "[2]",
    );
    const policy = resolveCitationAnchorInteractionPolicy(anchor);
    expect(policy.viewerUrl).toBe("/api/uploads/files/file_123/raw#page=4");
    expect(policy.directOpenUrl).toBe("/api/uploads/files/file_123/raw#page=4");
    expect(policy.openDirectOnPrimaryClick).toBe(true);
    expect(shouldOpenCitationSourceUrlForPointerEvent({ button: 0, ctrlKey: true, metaKey: false }, policy)).toBe(
      true,
    );
    expect(shouldOpenCitationSourceUrlForPointerEvent({ button: 1, ctrlKey: false, metaKey: false }, policy)).toBe(
      true,
    );
  });

  it("prefers external source url over internal viewer url when both are present", () => {
    const anchor = makeAnchor(
      {
        "data-file-id": "file_123",
        "data-source-url": "https://example.com/report",
        "data-viewer-url": "/api/uploads/files/file_123/raw#page=4",
      },
      "[2]",
    );
    const policy = resolveCitationAnchorInteractionPolicy(anchor);
    expect(policy.sourceUrl).toBe("https://example.com/report");
    expect(policy.viewerUrl).toBe("/api/uploads/files/file_123/raw#page=4");
    expect(policy.directOpenUrl).toBe("https://example.com/report");
    expect(policy.openDirectOnPrimaryClick).toBe(true);
  });

  it("ignores malformed source urls for direct-open policy", () => {
    const anchor = makeAnchor(
      {
        "data-source-url": "not-a-url",
      },
      "[3]",
    );
    const policy = resolveCitationAnchorInteractionPolicy(anchor);
    expect(policy.sourceUrl).toBe("");
    expect(policy.openDirectOnPrimaryClick).toBe(false);
    expect(shouldOpenCitationSourceUrlForPointerEvent({ button: 1, ctrlKey: false, metaKey: false }, policy)).toBe(
      false,
    );
  });

  it("ignores malformed viewer urls for direct-open policy", () => {
    const anchor = makeAnchor(
      {
        "data-viewer-url": "javascript:alert(1)",
      },
      "[4]",
    );
    const policy = resolveCitationAnchorInteractionPolicy(anchor);
    expect(policy.viewerUrl).toBe("");
    expect(policy.directOpenUrl).toBe("");
    expect(policy.openDirectOnPrimaryClick).toBe(false);
  });
});
