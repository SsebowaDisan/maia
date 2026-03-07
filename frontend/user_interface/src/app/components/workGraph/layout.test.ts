import { describe, expect, it } from "vitest";

import { computeWorkGraphLaneLayout, computeWorkGraphLayout } from "./layout";
import type { WorkGraphEdge, WorkGraphNode } from "./work_graph_types";

describe("work graph layout", () => {
  it("is deterministic for fallback layout", () => {
    const nodes: WorkGraphNode[] = [
      { id: "root", title: "Root", agent_role: "system" },
      { id: "plan", title: "Plan", agent_role: "planner", event_index_start: 1 },
      { id: "write", title: "Write", agent_role: "writer", event_index_start: 2 },
    ];
    const edges: WorkGraphEdge[] = [
      { id: "e1", source: "root", target: "plan", edge_family: "hierarchy" },
      { id: "e2", source: "plan", target: "write", edge_family: "hierarchy" },
    ];

    const first = computeWorkGraphLayout(nodes, edges, "root");
    const second = computeWorkGraphLayout(nodes, edges, "root");
    expect(first).toEqual(second);
  });

  it("separates swimlanes by role when role metadata exists", async () => {
    const nodes: WorkGraphNode[] = [
      { id: "root", title: "Root", agent_role: "system" },
      { id: "plan", title: "Plan", agent_role: "planner", event_index_start: 1 },
      { id: "research", title: "Research", agent_role: "research", event_index_start: 2 },
      { id: "verify", title: "Verify", agent_role: "verifier", event_index_start: 3 },
    ];
    const edges: WorkGraphEdge[] = [
      { id: "e1", source: "root", target: "plan", edge_family: "hierarchy" },
      { id: "e2", source: "plan", target: "research", edge_family: "hierarchy" },
      { id: "e3", source: "research", target: "verify", edge_family: "hierarchy" },
    ];

    const layout = await computeWorkGraphLaneLayout(nodes, edges, "root", { preferElk: false });
    expect(layout.plan.y).toBeLessThan(layout.research.y);
    expect(layout.research.y).toBeLessThan(layout.verify.y);
  });
});

