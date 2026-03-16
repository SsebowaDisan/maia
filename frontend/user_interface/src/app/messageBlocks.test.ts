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

  it("renders escaped display delimiters \\[ ... \\] into display-mode katex html", () => {
    const rendered = renderMathInMarkdown(
      "Thin lens:\n\\[\n\\frac{1}{f}=\\frac{1}{d_o}+\\frac{1}{d_i}\n\\]",
    );
    expect(rendered).toContain('data-math-rendered="true"');
    expect(rendered).toContain("katex-display");
  });

  it("renders escaped inline delimiters \\( ... \\) into inline katex html", () => {
    const rendered = renderMathInMarkdown("Given \\(F = ma\\), solve for mass.");
    expect(rendered).toContain('data-math-rendered="true"');
    expect(rendered).toContain("katex");
    expect(rendered).not.toContain("\\(F = ma\\)");
  });

  it("strips citation anchor artifacts from latex before rendering", () => {
    const rendered = renderMathInMarkdown(
      "$$\\frac{1<a class='citation' data-citation-number='1'>1</a>}{f}=\\frac{1}{d_o}$$",
    );
    expect(rendered).toContain("katex-display");
    expect(rendered).not.toContain("class='citation'");
  });

  it("normalizes double-escaped latex commands", () => {
    const rendered = renderMathInMarkdown("$$\\\\frac{1}{f}=\\\\frac{1}{d_o}+\\\\frac{1}{d_i}$$");
    expect(rendered).toContain("katex-display");
    expect(rendered).not.toContain("\\\\frac");
  });

  it("normalizes shorthand fractions emitted by models", () => {
    const rendered = renderMathInMarkdown("$\\frac12 = \\frac3$");
    expect(rendered).toContain("katex");
    expect(rendered).not.toContain("data-math-fallback");
  });

  it("normalizes escaped-dollar inline math delimiters emitted by models", () => {
    const rendered = renderMathInMarkdown("\\$\\frac{1}{2}=\\frac{2}{4}\\$");
    expect(rendered).toContain("katex");
    expect(rendered).not.toContain("\\$\\frac");
  });

  it("normalizes standalone latex lines into display math", () => {
    const rendered = renderMathInMarkdown("Now substituting:\n\\frac{1}{d_i}=\\frac{1}{3}-\\frac{1}{1}=\\frac{1}{4}");
    expect(rendered).toContain("katex-display");
  });

  it("keeps escaped-dollar non-math text unchanged", () => {
    const source = "Budget marker: \\$internal\\$ remains literal.";
    expect(renderMathInMarkdown(source)).toBe(source);
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

  it("normalizes chart blocks from nested chart payload", () => {
    const blocks = normalizeMessageBlocks([
      {
        type: "chart",
        chart: {
          title: "Revenue by quarter",
          labels: ["Q1", "Q2"],
          values: [12, 19],
        },
      },
    ]);
    expect(blocks).toHaveLength(1);
    expect(blocks[0]).toEqual({
      type: "chart",
      plot: {
        kind: "chart",
        title: "Revenue by quarter",
        labels: ["Q1", "Q2"],
        values: [12, 19],
      },
    });
  });

  it("normalizes chart blocks from direct payload fields", () => {
    const blocks = normalizeMessageBlocks([
      {
        type: "chart",
        title: "Tasks complete",
        series: [3, 5, 8],
      },
    ]);
    expect(blocks).toHaveLength(1);
    expect(blocks[0]).toEqual({
      type: "chart",
      plot: {
        kind: "chart",
        title: "Tasks complete",
        series: [3, 5, 8],
      },
    });
  });

  it("drops malformed image blocks and falls back to assistant markdown", () => {
    expect(
      normalizeMessageBlocks(
        [{ type: "image", src: "   " }],
        "Fallback image description",
      ),
    ).toEqual([{ type: "markdown", markdown: "Fallback image description" }]);
  });

  it("defaults invalid notice levels to info", () => {
    expect(
      normalizeMessageBlocks([
        {
          type: "notice",
          level: "urgent",
          text: "Heads up",
        },
      ]),
    ).toEqual([
      {
        type: "notice",
        level: "info",
        text: "Heads up",
      },
    ]);
  });

  it("normalizes table rows into string arrays", () => {
    expect(
      normalizeMessageBlocks([
        {
          type: "table",
          columns: ["Name", "Count"],
          rows: [["A", 1], ["B", null]],
        },
      ]),
    ).toEqual([
      {
        type: "table",
        columns: ["Name", "Count"],
        rows: [["A", "1"], ["B"]],
      },
    ]);
  });
});
