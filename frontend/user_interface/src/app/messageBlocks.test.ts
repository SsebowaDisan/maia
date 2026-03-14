import { describe, expect, it } from "vitest";

import {
  fallbackAssistantBlocks,
  normalizeCanvasDocuments,
  normalizeMessageBlocks,
} from "./messageBlocks";
import { renderMathInMarkdown } from "./utils/richText";

describe("messageBlocks", () => {
  it("falls back to a markdown block when no structured blocks are provided", () => {
    expect(normalizeMessageBlocks(undefined, "Hello world")).toEqual([
      { type: "markdown", markdown: "Hello world" },
    ]);
  });

  it("keeps valid widget blocks", () => {
    expect(
      normalizeMessageBlocks([
        {
          type: "widget",
          widget: {
            kind: "lens_equation",
            props: { focalLength: 10, objectDistance: 30 },
          },
        },
      ]),
    ).toEqual([
      {
        type: "widget",
        widget: {
          kind: "lens_equation",
          props: { focalLength: 10, objectDistance: 30 },
        },
      },
    ]);
  });

  it("drops malformed document actions and falls back to assistant markdown", () => {
    expect(
      normalizeMessageBlocks(
        [
          {
            type: "document_action",
            action: { kind: "open_canvas", title: "Draft" },
          },
        ],
        "Fallback answer",
      ),
    ).toEqual([{ type: "markdown", markdown: "Fallback answer" }]);
  });

  it("filters invalid canvas documents", () => {
    expect(
      normalizeCanvasDocuments([
        { id: "doc_1", title: "Report", content: "# Draft" },
        { id: "", title: "Broken" },
      ]),
    ).toEqual([{ id: "doc_1", title: "Report", content: "# Draft" }]);
  });

  it("returns an empty list for blank fallback assistant text", () => {
    expect(fallbackAssistantBlocks("   ")).toEqual([]);
  });

  it("renders inline markdown math into katex html", () => {
    const rendered = renderMathInMarkdown("Einstein says $E = mc^2$.");
    expect(rendered).toContain('data-math-rendered="true"');
    expect(rendered).toContain("katex");
    expect(rendered).not.toContain("$E = mc^2$");
  });

  it("renders display markdown math into display-mode katex html", () => {
    const rendered = renderMathInMarkdown(
      "Optics: $$\\frac{1}{f}=\\frac{1}{d_o}+\\frac{1}{d_i}$$",
    );
    expect(rendered).toContain('data-math-rendered="true"');
    expect(rendered).toContain("katex-display");
  });

  it("preserves currency values that start with dollar and digit", () => {
    const source = "Price is $5.00 today.";
    expect(renderMathInMarkdown(source)).toBe(source);
  });

  it("returns identical text when there is no math", () => {
    const source = "No equations here, just plain markdown text.";
    expect(renderMathInMarkdown(source)).toBe(source);
  });

  it("keeps markdown content intact through normalizeMessageBlocks round-trip", () => {
    const markdown = "Formula is $F = ma$ in context.";
    expect(
      normalizeMessageBlocks([
        {
          type: "markdown",
          markdown,
        },
      ]),
    ).toEqual([
      {
        type: "markdown",
        markdown,
      },
    ]);
  });
});
