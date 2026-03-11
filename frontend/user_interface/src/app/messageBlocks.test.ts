import { describe, expect, it } from "vitest";

import {
  fallbackAssistantBlocks,
  normalizeCanvasDocuments,
  normalizeMessageBlocks,
} from "./messageBlocks";

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
});
