// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import { renderRichText } from "./richText";

describe("richText evidence anchors", () => {
  it("wraps evidence list items with evidence ids under the evidence citations section", () => {
    const html = renderRichText(`
## Evidence Citations

- [1] https://example.com/one
- [2] https://example.com/two
`);

    const doc = new DOMParser().parseFromString(html, "text/html");
    const first = doc.querySelector("li > #evidence-1");
    const second = doc.querySelector("li > #evidence-2");

    expect(first).not.toBeNull();
    expect(second).not.toBeNull();
  });

  it("does not inject evidence wrappers for unrelated lists", () => {
    const html = renderRichText(`
## Summary

- First point
- Second point
`);

    const doc = new DOMParser().parseFromString(html, "text/html");
    expect(doc.querySelector("#evidence-1")).toBeNull();
  });

  it("preserves data-viewer-url on citation anchors", () => {
    const html = renderRichText(
      `<a class="citation" data-file-id="file_123" data-viewer-url="/api/uploads/files/file_123/raw#page=2">[1]</a>`,
    );

    const doc = new DOMParser().parseFromString(html, "text/html");
    const anchor = doc.querySelector("a.citation");

    expect(anchor?.getAttribute("data-viewer-url")).toBe("/api/uploads/files/file_123/raw#page=2");
  });

  it("does not leak citation sentinel text when markdown and citation anchors are mixed", () => {
    const html = renderRichText(
      `## Summary

Claim with evidence <a class="citation" href="#evidence-1" id="citation-1">[1]</a>.`,
    );

    expect(html).toContain('class="citation"');
    expect(html).not.toContain("MAIA_CITATION_SENTINEL");
  });
});
