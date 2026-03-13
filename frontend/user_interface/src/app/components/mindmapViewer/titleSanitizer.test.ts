import { describe, expect, it } from "vitest";

import { resolveProfessionalNodeTitle, sanitizeMindmapTitle } from "./titleSanitizer";

describe("mindmap title sanitizer", () => {
  it("does not return generic page/detail labels", () => {
    const pageTitle = resolveProfessionalNodeTitle({
      id: "page_1",
      title: "Page",
      node_type: "page",
      page: "2",
      source_name: "Machine Learning Overview PDF",
    });

    const detailTitle = resolveProfessionalNodeTitle({
      id: "leaf_1",
      title: "Detail",
      node_type: "excerpt",
      source_name: "Machine Learning Overview PDF",
    });

    expect(pageTitle.toLowerCase()).not.toBe("page");
    expect(detailTitle.toLowerCase()).not.toBe("detail");
    expect(pageTitle).toMatch(/machine learning overview pdf|p\.2/i);
    expect(detailTitle).toMatch(/machine learning overview pdf|excerpt/i);
  });

  it("promotes summary text when title is machine-like", () => {
    const title = resolveProfessionalNodeTitle({
      id: "src_92eb6dfa7b7763",
      title: "src_92eb6dfa7b7763",
      summary: "Understanding machine learning from theory to practical algorithms.",
      node_type: "section",
    });

    expect(title).toMatch(/understanding machine learning/i);
    expect(title).not.toMatch(/^src_/i);
  });

  it("clips long titles without trailing ellipsis artifacts", () => {
    const longValue = "Machine learning ".repeat(30);
    const sanitized = sanitizeMindmapTitle(longValue, 30);

    expect(sanitized.endsWith("...")).toBe(false);
    expect(sanitized.endsWith("…")).toBe(false);
    expect(sanitized.length).toBeLessThanOrEqual(30);
  });
});
