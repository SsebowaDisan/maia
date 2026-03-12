import { describe, expect, it } from "vitest";

import { computeInitialCollapsedFromPayload } from "./viewerHelpers";

describe("mindmap viewer initial collapse", () => {
  it("collapses first-layer branches that have deeper children", () => {
    const collapsed = computeInitialCollapsedFromPayload(
      {
        title: "What is machine learning?",
        root_id: "root",
        nodes: [
          { id: "root", title: "What is machine learning?" },
          { id: "planning", title: "Planning" },
          { id: "research", title: "Research" },
          { id: "step-1", title: "Find sources" },
        ],
        edges: [
          { source: "root", target: "planning", type: "hierarchy" },
          { source: "root", target: "research", type: "hierarchy" },
          { source: "planning", target: "step-1", type: "hierarchy" },
        ],
      },
      4,
    );

    expect(collapsed).toEqual(["planning"]);
  });

  it("pre-collapses deeper expandable nodes so each click reveals one level", () => {
    const collapsed = computeInitialCollapsedFromPayload(
      {
        title: "Tree",
        root_id: "root",
        nodes: [
          { id: "root", title: "Root" },
          { id: "a", title: "A" },
          { id: "a1", title: "A1" },
          { id: "a2", title: "A2" },
          { id: "a2i", title: "A2i" },
        ],
        edges: [
          { source: "root", target: "a", type: "hierarchy" },
          { source: "a", target: "a1", type: "hierarchy" },
          { source: "a", target: "a2", type: "hierarchy" },
          { source: "a2", target: "a2i", type: "hierarchy" },
        ],
      },
      5,
    );

    expect(new Set(collapsed)).toEqual(new Set(["a", "a2"]));
  });

  it("returns an empty list when the payload is missing graph data", () => {
    expect(computeInitialCollapsedFromPayload(null, 4)).toEqual([]);
  });
});
