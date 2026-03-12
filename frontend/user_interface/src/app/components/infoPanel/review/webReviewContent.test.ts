import { describe, expect, it } from "vitest";

import type { EvidenceCard } from "../../../../utils/infoInsights";
import {
  findBestParagraphIndex,
  parseWebReviewSourceMap,
  resolveWebReviewSource,
  sanitizeReadableHtmlToParagraphs,
} from "./webReviewContent";

describe("webReviewContent", () => {
  it("sanitizes readable html into safe text paragraphs", () => {
    const paragraphs = sanitizeReadableHtmlToParagraphs(
      "<article><h1>Title</h1><p>Safe paragraph.</p><script>alert('x')</script><p>Another one.</p></article>",
    );
    expect(paragraphs.length).toBeGreaterThanOrEqual(2);
    expect(paragraphs.join(" ")).toContain("Safe paragraph.");
    expect(paragraphs.join(" ")).not.toContain("alert");
  });

  it("parses web review source map from typed info panel payload", () => {
    const sourceMap = parseWebReviewSourceMap({
      web_review_content: {
        version: "web_review.v1",
        sources: [
          {
            source_id: "url:https://axongroup.com/about-axon",
            source_url: "https://axongroup.com/about-axon",
            title: "Axon Group | About",
            domain: "axongroup.com",
            readable_text: "Axon Group overview.",
            evidence_ids: ["evidence-1"],
          },
        ],
      },
    });
    const source = sourceMap["url:https://axongroup.com/about-axon"];
    expect(source).toBeDefined();
    expect(source?.title).toBe("Axon Group | About");
    expect(source?.domain).toBe("axongroup.com");
    expect(source?.evidenceIds).toEqual(["evidence-1"]);
  });

  it("ignores placeholder test sources in typed web review payloads", () => {
    const sourceMap = parseWebReviewSourceMap({
      web_review_content: {
        version: "web_review.v1",
        sources: [
          {
            source_id: "url:https://example.com/?maia_gap_test_media=1",
            source_url: "https://example.com/?maia_gap_test_media=1",
            title: "Example Domain",
            readable_text: "This should not render.",
          },
          {
            source_id: "url:https://axongroup.com/about-axon",
            source_url: "https://axongroup.com/about-axon",
            title: "Axon Group | About",
            readable_text: "Axon Group overview.",
          },
        ],
      },
    });
    expect(sourceMap["url:https://example.com/?maia_gap_test_media=1"]).toBeUndefined();
    expect(sourceMap["url:https://axongroup.com/about-axon"]?.title).toBe("Axon Group | About");
  });

  it("falls back to evidence extracts when no web review payload exists", () => {
    const evidenceCards: EvidenceCard[] = [
      {
        id: "evidence-1",
        title: "Evidence [1]",
        source: "Axon Group",
        sourceType: "web",
        sourceUrl: "https://axongroup.com/about-axon",
        extract: "Axon Group is family-owned.",
      },
      {
        id: "evidence-2",
        title: "Evidence [2]",
        source: "Axon Group",
        sourceType: "web",
        sourceUrl: "https://axongroup.com/about-axon",
        extract: "The company has more than 50 years of experience.",
      },
    ];
    const resolved = resolveWebReviewSource({
      sourceMap: {},
      sourceId: "url:https://axongroup.com/about-axon",
      sourceUrl: "https://axongroup.com/about-axon",
      sourceTitle: "Axon Group",
      evidenceCards,
    });
    expect(resolved).toBeTruthy();
    expect(resolved?.domain).toBe("axongroup.com");
    expect(String(resolved?.readableText || "")).toContain("family-owned");
  });

  it("does not build a fallback review for placeholder test urls", () => {
    const evidenceCards: EvidenceCard[] = [
      {
        id: "evidence-1",
        title: "Evidence [1]",
        source: "Example Domain",
        sourceType: "web",
        sourceUrl: "https://example.com/?maia_gap_test_media=1",
        extract: "This should never appear.",
      },
    ];
    const resolved = resolveWebReviewSource({
      sourceMap: {},
      sourceId: "url:https://example.com/?maia_gap_test_media=1",
      sourceUrl: "https://example.com/?maia_gap_test_media=1",
      sourceTitle: "Example Domain",
      evidenceCards,
    });
    expect(resolved).toBeNull();
  });

  it("matches focus text to the most relevant paragraph index", () => {
    const paragraphs = [
      "Machine learning is a subset of artificial intelligence.",
      "Supervised learning uses labeled data for prediction tasks.",
      "Reinforcement learning optimizes decisions through reward signals.",
    ];
    const index = findBestParagraphIndex(paragraphs, "labeled data for prediction");
    expect(index).toBe(1);
  });
});
