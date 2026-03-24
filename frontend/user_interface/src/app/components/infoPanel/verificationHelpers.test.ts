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
    expect(result.citationRawUrl).not.toContain("index_id=");
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

  it("maps web-sourced PDF evidence card with fileId as file type", () => {
    const card: EvidenceCard = {
      id: "evidence-5",
      title: "Evidence [5]",
      source: "SEC Filing Q3 2023",
      sourceType: "pdf",
      sourceUrl: "https://sec.gov/filings/q3-2023.pdf",
      fileId: "file-99",
      page: "4",
      extract: "Revenue reached $12B in Q3.",
    };
    const citation = toCitationFromEvidence(card, 0);
    // fileId present → must be "file", not "website"
    expect(citation.sourceType).toBe("file");
    expect(citation.fileId).toBe("file-99");
  });

  it("resolves open URL to source website for stored PDF with web origin", () => {
    const result = resolveCitationOpenUrl({
      citation: {
        sourceName: "SEC Filing Q3 2023",
        extract: "Revenue reached $12B.",
        sourceType: "file" as const,
        fileId: "file-99",
        sourceUrl: "https://sec.gov/filings/q3-2023.pdf",
        evidenceId: "evidence-5",
      },
      evidenceCards: [],
      indexId: null,
    });
    // Raw file URL exists (fileId set) + website URL also exists
    // → PDF viewer shows, "Open" goes to the original source URL
    expect(result.citationIsPdf).toBe(true);
    expect(result.citationUsesWebsite).toBe(false);
    expect(result.citationOpenUrl).toBe("https://sec.gov/filings/q3-2023.pdf");
  });

  it("rejects malformed file ids instead of emitting broken raw urls", () => {
    const result = resolveCitationOpenUrl({
      citation: {
        sourceName: "Broken PDF",
        extract: "Citation extract",
        sourceType: "file" as const,
        fileId: "not a real id / ???",
        evidenceId: "evidence-9",
      },
      evidenceCards: [],
      indexId: 42,
    });
    expect(result.citationRawUrl).toBeNull();
    expect(result.citationIsPdf).toBe(false);
  });

  it("maps pure web source without fileId as website type", () => {
    const card: EvidenceCard = {
      id: "evidence-6",
      title: "Evidence [6]",
      source: "Reuters",
      sourceType: "web",
      sourceUrl: "https://reuters.com/article/abc",
      extract: "Market cap grew 20%.",
    };
    const citation = toCitationFromEvidence(card, 0);
    // No fileId → infer from sourceUrl → "website"
    expect(citation.sourceType).toBe("website");
  });
});
