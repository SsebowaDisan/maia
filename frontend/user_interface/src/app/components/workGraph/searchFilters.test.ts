import { describe, expect, it } from "vitest";

import type { WorkGraphEdge, WorkGraphNode } from "./work_graph_types";
import {
  filterWorkGraphEdges,
  filterWorkGraphNodes,
  fuzzyMatch,
  hiddenNodeIdsForCollapsed,
  toggleCollapsedNodeIds,
} from "./searchFilters";

describe("work graph search and filters", () => {
  it("supports fuzzy query matching", () => {
    expect(fuzzyMatch("Collect machine learning evidence", "ml ev")).toBe(true);
    expect(fuzzyMatch("Collect machine learning evidence", "zzz")).toBe(false);
  });

  it("filters nodes by role, status, confidence, and focus mode", () => {
    const nodes: WorkGraphNode[] = [
      { id: "n1", title: "Plan", agent_role: "planner", status: "completed", confidence: 0.9 },
      { id: "n2", title: "Research", agent_role: "research", status: "running", confidence: 0.55 },
      { id: "n3", title: "Verify", agent_role: "verifier", status: "blocked", confidence: 0.45 },
    ];

    const lowConfidence = filterWorkGraphNodes(nodes, {
      query: "",
      agentRole: "all",
      status: "all",
      confidence: "low",
      focusMode: false,
      edgeFamily: "all",
    });
    expect(lowConfidence.map((node) => node.id)).toEqual(["n2", "n3"]);

    const focusMode = filterWorkGraphNodes(nodes, {
      query: "",
      agentRole: "all",
      status: "all",
      confidence: "all",
      focusMode: true,
      edgeFamily: "all",
    });
    expect(focusMode.map((node) => node.id)).toEqual(["n2", "n3"]);
  });

  it("hides descendants for collapsed hierarchy nodes", () => {
    const nodes: WorkGraphNode[] = [
      { id: "root", title: "Root" },
      { id: "child", title: "Child" },
      { id: "grandchild", title: "Grandchild" },
    ];
    const edges: WorkGraphEdge[] = [
      { id: "e1", source: "root", target: "child", edge_family: "hierarchy" },
      { id: "e2", source: "child", target: "grandchild", edge_family: "hierarchy" },
    ];

    const hidden = hiddenNodeIdsForCollapsed(nodes, edges, ["root"]);
    expect(hidden.has("child")).toBe(true);
    expect(hidden.has("grandchild")).toBe(true);
  });

  it("filters edges by visible nodes and edge family", () => {
    const edges: WorkGraphEdge[] = [
      { id: "h", source: "a", target: "b", edge_family: "hierarchy" },
      { id: "e", source: "a", target: "c", edge_family: "evidence" },
    ];

    const filtered = filterWorkGraphEdges(edges, new Set(["a", "c"]), "evidence");
    expect(filtered.map((edge) => edge.id)).toEqual(["e"]);
  });

  it("toggles collapsed node ids", () => {
    const expanded = toggleCollapsedNodeIds([], "node-1");
    expect(expanded).toEqual(["node-1"]);
    const collapsed = toggleCollapsedNodeIds(expanded, "node-1");
    expect(collapsed).toEqual([]);
  });
});
