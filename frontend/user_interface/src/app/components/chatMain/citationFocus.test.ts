import { describe, expect, it } from "vitest";
import type { EvidenceCard } from "../../utils/infoInsights";
import {
  parseEvidenceRefId,
  resolveCitationFocusFromAnchor,
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
});
