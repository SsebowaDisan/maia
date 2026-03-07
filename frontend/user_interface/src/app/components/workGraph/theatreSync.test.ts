import { describe, expect, it, vi } from "vitest";

import type { AgentActivityEvent } from "../../types";
import type { WorkGraphNode } from "./work_graph_types";
import {
  buildWorkGraphJumpTarget,
  deriveActiveNodeIdsForEvent,
  emitWorkGraphJumpTarget,
  findTimelineIndexForJumpTarget,
  subscribeWorkGraphJumpTarget,
} from "./theatreSync";

function makeEvent(partial: Partial<AgentActivityEvent>): AgentActivityEvent {
  return {
    event_id: "evt-1",
    run_id: "run-1",
    event_type: "browser_click",
    title: "Click",
    detail: "",
    timestamp: "2026-03-07T00:00:00Z",
    metadata: {},
    ...partial,
  };
}

describe("theatre sync helpers", () => {
  it("builds jump target from node refs and event range", () => {
    const node: WorkGraphNode = {
      id: "node.research",
      title: "Research",
      event_refs: ["evt-1"],
      scene_refs: ["scene.browser.main"],
      event_index_start: 4,
      event_index_end: 7,
    };

    const target = buildWorkGraphJumpTarget(node);
    expect(target.graphNodeIds).toEqual(["node.research"]);
    expect(target.sceneRefs).toEqual(["scene.browser.main"]);
    expect(target.eventRefs).toEqual(["evt-1"]);
    expect(target.eventIndexStart).toBe(4);
    expect(target.eventIndexEnd).toBe(7);
  });

  it("finds timeline event index by event refs and graph node ids", () => {
    const events: AgentActivityEvent[] = [
      makeEvent({
        event_id: "evt-1",
        event_index: 1,
        data: { graph_node_id: "node.plan" },
      }),
      makeEvent({
        event_id: "evt-2",
        event_index: 2,
        data: { graph_node_ids: ["node.research"] },
      }),
      makeEvent({
        event_id: "evt-3",
        event_index: 3,
        data: { scene_refs: ["scene.browser.main"] },
      }),
    ];

    const byEventRef = findTimelineIndexForJumpTarget(events, {
      graphNodeIds: [],
      sceneRefs: [],
      eventRefs: ["evt-2"],
      eventIndexStart: null,
      eventIndexEnd: null,
      nonce: "a",
    });
    expect(byEventRef).toBe(1);

    const byNode = findTimelineIndexForJumpTarget(events, {
      graphNodeIds: ["node.research"],
      sceneRefs: [],
      eventRefs: [],
      eventIndexStart: null,
      eventIndexEnd: null,
      nonce: "b",
    });
    expect(byNode).toBe(1);
  });

  it("derives active node ids from explicit refs and event-index ranges", () => {
    const nodes: WorkGraphNode[] = [
      {
        id: "node.plan",
        title: "Plan",
        event_index_start: 1,
        event_index_end: 2,
      },
      {
        id: "node.research",
        title: "Research",
        event_refs: ["evt-22"],
        event_index_start: 3,
        event_index_end: 4,
      },
    ];
    const event = makeEvent({
      event_id: "evt-22",
      event_index: 3,
      data: { graph_node_id: "node.research" },
    });

    const nodeIds = deriveActiveNodeIdsForEvent(nodes, event);
    expect(nodeIds).toContain("node.research");
    expect(nodeIds).not.toContain("node.plan");
  });

  it("streams jump targets over browser event bus", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeWorkGraphJumpTarget(listener);
    emitWorkGraphJumpTarget({
      graphNodeIds: ["node.verify"],
      sceneRefs: [],
      eventRefs: ["evt-9"],
      eventIndexStart: 9,
      eventIndexEnd: 10,
      nonce: "nonce-1",
    });
    unsubscribe();

    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener.mock.calls[0][0].graphNodeIds).toEqual(["node.verify"]);
    expect(listener.mock.calls[0][0].eventRefs).toEqual(["evt-9"]);
  });
});
