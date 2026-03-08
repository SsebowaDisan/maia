import { describe, expect, it } from "vitest";

import type { EvidenceCard } from "../../utils/infoInsights";
import { resolveCitationOpenUrl, toCitationFromEvidence } from "./verificationHelpers";

describe("verificationHelpers", () => {
  it("maps evidence card to citation focus with page and highlight metadata", () => {
    const card: EvidenceCard = {
      id: "evidence-3",
      title: "Evidence [3]",
      source: "Axon Group | About",
      sourceType: "web",
      sourceUrl: "https://axongroup.com/about-axon",
      page: "3",
      extract: "Axon Group is family-owned.",
      highlightBoxes: [{ x: 0.1, y: 0.2, width: 0.3, height: 0.1 }],
      strengthScore: 0.77,
      strengthTier: 3,
      matchQuality: "exact",
      unitId: "u-3",
      selector: "article p:nth-of-type(2)",
      charStart: 8,
      charEnd: 32,
    };

    const citation = toCitationFromEvidence(card, 0);
    expect(citation.evidenceId).toBe("evidence-3");
    expect(citation.sourceType).toBe("website");
    expect(citation.page).toBe("3");
    expect(citation.highlightBoxes?.length).toBe(1);
    expect(citation.strengthTier).toBe(3);
    expect(citation.matchQuality).toBe("exact");
    expect(citation.unitId).toBe("u-3");
    expect(citation.selector).toBe("article p:nth-of-type(2)");
    expect(citation.charStart).toBe(8);
    expect(citation.charEnd).toBe(32);
  });

  it("resolves PDF preview from file source with index context", () => {
    const citation = {
      sourceName: "Quarterly Report.pdf",
      extract: "Revenue increased.",
      sourceType: "file" as const,
      fileId: "file-22",
      page: "7",
      evidenceId: "evidence-1",
    };
    const result = resolveCitationOpenUrl({
      citation,
      evidenceCards: [],
      indexId: 42,
    });
    expect(result.citationUsesWebsite).toBe(false);
    expect(result.citationIsPdf).toBe(true);
    expect(result.citationRawUrl).toContain("/api/uploads/files/file-22/raw");
    expect(result.citationRawUrl).toContain("index_id=42");
  });

  it("resolves website citation when only web URL is available", () => {
    const citation = {
      sourceName: "Axon Group",
      extract: "Company profile",
      sourceType: "website" as const,
      sourceUrl: "https://axongroup.com/about-axon",
      evidenceId: "evidence-2",
    };
    const result = resolveCitationOpenUrl({
      citation,
      evidenceCards: [],
      indexId: null,
    });
    expect(result.citationUsesWebsite).toBe(true);
    expect(result.citationIsPdf).toBe(false);
    expect(result.citationOpenUrl).toBe("https://axongroup.com/about-axon");
  });
});
