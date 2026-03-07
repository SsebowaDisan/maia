import { beforeEach, describe, expect, it } from "vitest";

import { buildWorkGraphMindmapPayload, useWorkGraphStore } from "./useWorkGraphStore";

describe("useWorkGraphStore", () => {
  beforeEach(() => {
    useWorkGraphStore.getState().reset();
  });

  it("hydrates run payload and replay state", () => {
    useWorkGraphStore.getState().hydrateFromPayload({
      run_id: "run-1",
      title: "Work graph",
      root_id: "run:run-1:root",
      schema: "work_graph.v2",
      nodes: [
        { id: "run:run-1:root", title: "Root", node_type: "task", status: "running" },
        {
          id: "node.plan",
          title: "Plan",
          node_type: "plan_step",
          status: "completed",
          event_refs: ["evt-1"],
          event_index_start: 1,
          event_index_end: 1,
        },
      ],
      edges: [
        {
          id: "hierarchy:root->plan",
          source: "run:run-1:root",
          target: "node.plan",
          edge_family: "hierarchy",
        },
      ],
      filters: {},
    });
    useWorkGraphStore.getState().hydrateFromReplayState({
      run_id: "run-1",
      latest_event_index: 4,
      work_graph: {
        run_id: "run-1",
        active_node_ids: ["node.plan"],
      },
    });

    const state = useWorkGraphStore.getState();
    expect(state.runId).toBe("run-1");
    expect(state.rootId).toBe("run:run-1:root");
    expect(state.latestEventIndex).toBe(4);
    expect(state.activeNodeIds).toEqual(["node.plan"]);
  });

  it("applies live activity events to create provisional graph nodes", () => {
    useWorkGraphStore.getState().hydrateFromPayload({
      run_id: "run-2",
      title: "Work graph",
      root_id: "run:run-2:root",
      schema: "work_graph.v2",
      nodes: [{ id: "run:run-2:root", title: "Root", node_type: "task", status: "running" }],
      edges: [],
      filters: {},
    });
    useWorkGraphStore.getState().applyActivityEvent({
      event_id: "evt-2",
      run_id: "run-2",
      event_type: "browser_extract",
      title: "Collect evidence",
      detail: "Collected source snippets",
      timestamp: "2026-03-07T12:00:00Z",
      seq: 2,
      status: "in_progress",
      data: {
        event_family: "browser",
        graph_node_id: "node.research",
        event_index: 2,
        scene_ref: "scene.browser.main",
      },
      metadata: {},
    });

    const state = useWorkGraphStore.getState();
    const node = state.nodes.find((row) => row.id === "node.research");
    expect(node?.title).toBe("Collect evidence");
    expect(node?.status).toBe("running");
    expect(state.activeNodeIds).toEqual(["node.research"]);
    expect(state.latestEventIndex).toBe(2);
    expect(node?.event_refs).toEqual(["evt-2"]);
  });

  it("builds a mindmap-compatible work graph payload", () => {
    useWorkGraphStore.getState().hydrateFromPayload({
      run_id: "run-3",
      title: "Work graph",
      root_id: "run:run-3:root",
      schema: "work_graph.v2",
      nodes: [
        { id: "run:run-3:root", title: "Root", node_type: "task", status: "running" },
        { id: "node.verify", title: "Verify", node_type: "verification", status: "completed" },
      ],
      edges: [
        {
          id: "verify-edge",
          source: "run:run-3:root",
          target: "node.verify",
          edge_family: "verification",
        },
      ],
      filters: { status: "completed" },
    });
    const payload = buildWorkGraphMindmapPayload(useWorkGraphStore.getState());
    expect(payload?.map_type).toBe("work_graph");
    expect(payload?.nodes.length).toBe(2);
    expect(payload?.edges[0]?.type).toBe("dependency");
    expect(payload?.filters.status).toBe("completed");
  });
});

