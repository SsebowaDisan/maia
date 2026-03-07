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

  it("falls back to structure for unknown map types", () => {
    const parsed = parseCanvasState(
      JSON.stringify({
        collapsedNodeIds: [],
        activeMapType: "unknown_map",
      }),
    );
    expect(parsed?.activeMapType).toBe("structure");
  });
});
