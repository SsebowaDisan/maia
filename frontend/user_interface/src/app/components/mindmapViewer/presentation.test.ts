import { describe, expect, it } from "vitest";

import { buildMindmapArtifactSummary, collectAvailableMindmapTypes, preferredLayoutForMapType } from "./presentation";

describe("mindmap presentation", () => {
  it("prefers available_map_types from the payload", () => {
    const types = collectAvailableMindmapTypes({
      map_type: "structure",
      available_map_types: ["context_mindmap", "structure", "evidence"],
    });
    expect(types).toEqual(["context_mindmap", "structure", "evidence"]);
  });

  it("uses backend artifact summary metadata when present", () => {
    const summary = buildMindmapArtifactSummary({
      map_type: "structure",
      title: "Research map",
      artifact_summary: "Generated from answer claims and evidence.",
      nodes: [{ id: "root", title: "Root" }],
    });
    expect(summary?.presentation.summary).toBe("Generated from answer claims and evidence.");
  });

  it("defaults structure maps to horizontal layout", () => {
    expect(preferredLayoutForMapType("structure")).toBe("horizontal");
    expect(preferredLayoutForMapType("evidence")).toBe("horizontal");
  });
});
