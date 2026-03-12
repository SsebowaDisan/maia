import { describe, expect, it } from "vitest";

import { parseCanvasState } from "./utils";

describe("mindmap viewer canvas state", () => {
  it("preserves work_graph as the active map type", () => {
    const parsed = parseCanvasState(
      JSON.stringify({
        collapsedNodeIds: ["node-1"],
        activeMapType: "work_graph",
      }),
    );
    expect(parsed?.activeMapType).toBe("work_graph");
  });

  it("preserves context_mindmap as the active map type", () => {
    const parsed = parseCanvasState(
      JSON.stringify({
        collapsedNodeIds: ["node-2"],
        activeMapType: "context_mindmap",
      }),
    );
    expect(parsed?.activeMapType).toBe("context_mindmap");
  });

  it("falls back to structure for unknown map types", () => {
    const parsed = parseCanvasState(
      JSON.stringify({
        collapsedNodeIds: [],
        activeMapType: "unknown_map",
      }),
    );
    expect(parsed?.activeMapType).toBe("structure");
  });

  it("preserves focus state, reasoning toggle, and clamps max depth", () => {
    const parsed = parseCanvasState(
      JSON.stringify({
        collapsedNodeIds: ["node-3"],
        activeMapType: "evidence",
        focusedNodeId: "node-3",
        focusNodeId: "node-7",
        showReasoningMap: true,
        layoutMode: "balanced",
        maxDepth: 99,
      }),
    );
    expect(parsed?.focusedNodeId).toBe("node-3");
    expect(parsed?.focusNodeId).toBe("node-7");
    expect(parsed?.showReasoningMap).toBe(true);
    expect(parsed?.maxDepth).toBe(8);
    expect(parsed?.layoutMode).toBe("horizontal");
  });
});
