import { describe, expect, it } from "vitest";

import { normalizeMindmapPayloadForViewer } from "./viewerNormalize";

describe("normalizeMindmapPayloadForViewer", () => {
  it("groups flat structure-map sources into semantic first-level topic branches", () => {
    const payload = normalizeMindmapPayloadForViewer(
      {
        map_type: "structure",
        title: "What is machine learning?",
        root_id: "root",
        nodes: [
          { id: "root", title: "What is machine learning?", node_type: "root" },
          { id: "web-1", title: "src_a", node_type: "source", source_name: "src_a" },
          { id: "web-2", title: "src_b", node_type: "source", source_name: "src_b" },
          { id: "doc-1", title: "src_c", node_type: "source", source_name: "src_c" },
          { id: "doc-2", title: "src_d", node_type: "source", source_name: "src_d" },
          { id: "src-1", title: "src_e", node_type: "source", source_name: "src_e" },
          { id: "src-2", title: "src_f", node_type: "source", source_name: "src_f" },
          { id: "topic-1", title: "Applications of machine learning", node_type: "section" },
          { id: "topic-2", title: "Applications of machine learning", node_type: "section" },
          { id: "topic-3", title: "What is machine learning?", node_type: "section" },
          { id: "topic-4", title: "What is machine learning?", node_type: "section" },
          { id: "topic-5", title: "Deep learning vs machine learning", node_type: "section" },
          { id: "topic-6", title: "Deep learning vs machine learning", node_type: "section" },
        ],
        edges: [
          { source: "root", target: "web-1", type: "hierarchy" },
          { source: "root", target: "web-2", type: "hierarchy" },
          { source: "root", target: "doc-1", type: "hierarchy" },
          { source: "root", target: "doc-2", type: "hierarchy" },
          { source: "root", target: "src-1", type: "hierarchy" },
          { source: "root", target: "src-2", type: "hierarchy" },
          { source: "web-1", target: "topic-1", type: "hierarchy" },
          { source: "web-2", target: "topic-2", type: "hierarchy" },
          { source: "doc-1", target: "topic-3", type: "hierarchy" },
          { source: "doc-2", target: "topic-4", type: "hierarchy" },
          { source: "src-1", target: "topic-5", type: "hierarchy" },
          { source: "src-2", target: "topic-6", type: "hierarchy" },
        ],
      },
      "structure",
    );

    const syntheticGroups = (payload?.nodes || []).filter((node) => node.synthetic);
    expect(syntheticGroups.map((node) => node.title)).toEqual([
      "Fundamentals",
      "Applications",
      "Comparisons",
    ]);

    const rootEdges = (payload?.edges || []).filter((edge) => edge.source === "root" && edge.type === "hierarchy");
    expect(rootEdges).toHaveLength(3);
    expect(rootEdges.map((edge) => edge.target)).toEqual(syntheticGroups.map((node) => node.id));
  });

  it("groups evidence maps into claims and supporting sources", () => {
    const payload = normalizeMindmapPayloadForViewer(
      {
        map_type: "evidence",
        title: "Evidence map",
        root_id: "root",
        nodes: [
          { id: "root", title: "Evidence", node_type: "root" },
          { id: "claim-1", title: "Claim 1", node_type: "claim" },
          { id: "claim-2", title: "Claim 2", node_type: "claim" },
          { id: "source-1", title: "Source A", node_type: "source", source_name: "Source A" },
          { id: "source-2", title: "Source B", node_type: "source", source_name: "Source B" },
          { id: "source-3", title: "Source C", node_type: "source", source_name: "Source C" },
          { id: "evidence-1", title: "Evidence 1", node_type: "evidence" },
        ],
        edges: [
          { source: "root", target: "claim-1", type: "hierarchy" },
          { source: "root", target: "claim-2", type: "hierarchy" },
          { source: "root", target: "source-1", type: "hierarchy" },
          { source: "root", target: "source-2", type: "hierarchy" },
          { source: "root", target: "source-3", type: "hierarchy" },
          { source: "root", target: "evidence-1", type: "hierarchy" },
        ],
      },
      "evidence",
    );

    const syntheticGroups = (payload?.nodes || []).filter((node) => node.synthetic);
    expect(syntheticGroups.map((node) => node.title)).toEqual(["Claims", "Supporting evidence", "Supporting sources"]);
  });

  it("keeps structure-map root semantic even when source titles are unique", () => {
    const payload = normalizeMindmapPayloadForViewer(
      {
        map_type: "structure",
        title: "what is machine learning?",
        root_id: "root",
        nodes: [
          { id: "root", title: "what is machine learning?", node_type: "root" },
          { id: "src-1", title: "The Machine Learning Algorithm Guide", node_type: "source", source_name: "The Machine Learning Algorithm Guide" },
          { id: "src-2", title: "Applications of Machine Learning", node_type: "source", source_name: "Applications of Machine Learning" },
          { id: "src-3", title: "Deep Learning vs Machine Learning", node_type: "source", source_name: "Deep Learning vs Machine Learning" },
          { id: "src-4", title: "Top Projected Trends in Machine Learning", node_type: "source", source_name: "Top Projected Trends in Machine Learning" },
          { id: "src-5", title: "Machine Learning Case Studies", node_type: "source", source_name: "Machine Learning Case Studies" },
          { id: "src-6", title: "Top Machine Learning Tools", node_type: "source", source_name: "Top Machine Learning Tools" },
          { id: "topic-1", title: "What is machine learning?", node_type: "section" },
          { id: "topic-2", title: "Applications in industry", node_type: "section" },
          { id: "topic-3", title: "Difference between ML and DL", node_type: "section" },
          { id: "topic-4", title: "Future trends 2026", node_type: "section" },
          { id: "topic-5", title: "Case study examples", node_type: "section" },
          { id: "topic-6", title: "Tools and frameworks", node_type: "section" },
        ],
        edges: [
          { source: "root", target: "src-1", type: "hierarchy" },
          { source: "root", target: "src-2", type: "hierarchy" },
          { source: "root", target: "src-3", type: "hierarchy" },
          { source: "root", target: "src-4", type: "hierarchy" },
          { source: "root", target: "src-5", type: "hierarchy" },
          { source: "root", target: "src-6", type: "hierarchy" },
          { source: "src-1", target: "topic-1", type: "hierarchy" },
          { source: "src-2", target: "topic-2", type: "hierarchy" },
          { source: "src-3", target: "topic-3", type: "hierarchy" },
          { source: "src-4", target: "topic-4", type: "hierarchy" },
          { source: "src-5", target: "topic-5", type: "hierarchy" },
          { source: "src-6", target: "topic-6", type: "hierarchy" },
        ],
      },
      "structure",
    );

    const syntheticGroups = (payload?.nodes || []).filter((node) => node.synthetic);
    const syntheticTitles = syntheticGroups.map((node) => node.title);
    expect(syntheticTitles).not.toContain("More branches");
    expect(syntheticTitles).toEqual(
      expect.arrayContaining([
        "Fundamentals",
        "Applications",
        "Comparisons",
        "Trends & impact",
        "Case studies",
        "Tools & systems",
      ]),
    );

    const rootHierarchyEdges = (payload?.edges || []).filter(
      (edge) => edge.type === "hierarchy" && edge.source === "root",
    );
    expect(rootHierarchyEdges.length).toBe(syntheticGroups.length);
    rootHierarchyEdges.forEach((edge) => {
      const node = (payload?.nodes || []).find((row) => row.id === edge.target);
      expect(node?.synthetic).toBe(true);
    });
  });
});
