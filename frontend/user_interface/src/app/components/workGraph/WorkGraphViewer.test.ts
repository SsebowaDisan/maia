import { describe, expect, it } from "vitest";

import { computeWorkGraphLayout } from "./WorkGraphViewer";
import type { WorkGraphEdge, WorkGraphNode } from "./work_graph_types";

describe("computeWorkGraphLayout", () => {
  it("places hierarchy children at deeper x positions", () => {
    const nodes: WorkGraphNode[] = [
      { id: "root", title: "Root", agent_role: "system" },
      { id: "a", title: "A", agent_role: "planner", event_index_start: 1 },
      { id: "b", title: "B", agent_role: "research", event_index_start: 2 },
    ];
    const edges: WorkGraphEdge[] = [
      { id: "e1", source: "root", target: "a", edge_family: "hierarchy" },
      { id: "e2", source: "a", target: "b", edge_family: "hierarchy" },
    ];

    const layout = computeWorkGraphLayout(nodes, edges, "root");
    expect(layout.a.x).toBeGreaterThan(layout.root.x);
    expect(layout.b.x).toBeGreaterThan(layout.a.x);
  });

  it("keeps deterministic lane order by role", () => {
    const nodes: WorkGraphNode[] = [
      { id: "root", title: "Root", agent_role: "system" },
      { id: "planner", title: "Plan", agent_role: "planner", event_index_start: 1 },
      { id: "writer", title: "Write", agent_role: "writer", event_index_start: 2 },
    ];
    const edges: WorkGraphEdge[] = [
      { id: "e1", source: "root", target: "planner", edge_family: "hierarchy" },
      { id: "e2", source: "root", target: "writer", edge_family: "hierarchy" },
    ];
    const layout = computeWorkGraphLayout(nodes, edges, "root");
    expect(layout.planner.y).toBeLessThan(layout.writer.y);
  });
});

