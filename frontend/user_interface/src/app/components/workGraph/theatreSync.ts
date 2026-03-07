import type { AgentActivityEvent } from "../../types";
import type { WorkGraphNode } from "./work_graph_types";

const WORK_GRAPH_JUMP_EVENT = "maia:work_graph_jump_target";
const fallbackJumpListeners = new Set<(jumpTarget: WorkGraphJumpTarget) => void>();

type WorkGraphJumpTarget = {
  graphNodeIds: string[];
  sceneRefs: string[];
  eventRefs: string[];
  eventIndexStart: number | null;
  eventIndexEnd: number | null;
  nonce: string;
};

function readRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object") {
    return value as Record<string, unknown>;
  }
  return {};
}

function normalizeTokenList(values: unknown, limit = 48): string[] {
  const parsed: string[] = [];
  if (Array.isArray(values)) {
    for (const value of values) {
      const token = String(value || "").trim();
      if (token) {
        parsed.push(token);
      }
    }
  } else {
    const token = String(values || "").trim();
    if (token) {
      parsed.push(token);
    }
  }
  return Array.from(new Set(parsed)).slice(0, Math.max(1, limit));
}

function normalizeTokenListLower(values: unknown, limit = 48): string[] {
  return normalizeTokenList(values, limit).map((value) => value.toLowerCase());
}

function readActivityEventIndex(event: AgentActivityEvent): number {
  const data = readRecord(event.data || event.metadata);
  const direct = Number(event.event_index);
  if (Number.isFinite(direct) && direct > 0) {
    return direct;
  }
  const nested = Number(data["event_index"]);
  if (Number.isFinite(nested) && nested > 0) {
    return nested;
  }
  const seq = Number(event.seq);
  if (Number.isFinite(seq) && seq > 0) {
    return seq;
  }
  return 0;
}

function findTimelineIndexForJumpTarget(events: AgentActivityEvent[], jumpTarget: WorkGraphJumpTarget): number {
  if (!events.length) {
    return -1;
  }
  const targetGraphNodeIds = normalizeTokenListLower(jumpTarget.graphNodeIds);
  const targetSceneRefs = normalizeTokenListLower(jumpTarget.sceneRefs);
  const targetEventRefs = normalizeTokenListLower(jumpTarget.eventRefs);

  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    const data = readRecord(event.data || event.metadata);
    const eventId = String(event.event_id || "").trim().toLowerCase();
    const graphNodeId = String(event.graph_node_id || data["graph_node_id"] || "").trim().toLowerCase();
    const sceneRef = String(event.scene_ref || data["scene_ref"] || "").trim().toLowerCase();
    const eventRefs = normalizeTokenListLower(data["event_refs"]);
    const graphNodeIds = normalizeTokenListLower(data["graph_node_ids"]);
    const sceneRefs = normalizeTokenListLower(data["scene_refs"]);

    const byEventRef = targetEventRefs.some((ref) => ref === eventId || eventRefs.includes(ref));
    const byGraphNode =
      targetGraphNodeIds.some((ref) => ref === graphNodeId) ||
      targetGraphNodeIds.some((ref) => graphNodeIds.includes(ref));
    const bySceneRef =
      targetSceneRefs.some((ref) => ref === sceneRef) ||
      targetSceneRefs.some((ref) => sceneRefs.includes(ref));
    if (byEventRef || byGraphNode || bySceneRef) {
      return index;
    }
  }

  const rangeStart = Number(jumpTarget.eventIndexStart);
  const rangeEnd = Number(jumpTarget.eventIndexEnd || rangeStart);
  if (Number.isFinite(rangeStart) && rangeStart > 0) {
    for (let index = 0; index < events.length; index += 1) {
      const eventIndex = readActivityEventIndex(events[index]);
      if (!eventIndex) {
        continue;
      }
      if (eventIndex >= rangeStart && eventIndex <= Math.max(rangeStart, rangeEnd || rangeStart)) {
        return index;
      }
    }
    return Math.max(0, Math.min(events.length - 1, Math.round(rangeStart) - 1));
  }

  return -1;
}

function buildWorkGraphJumpTarget(node: WorkGraphNode): WorkGraphJumpTarget {
  const eventIndexStart = Number(node.event_index_start || 0);
  const eventIndexEnd = Number(node.event_index_end || eventIndexStart);
  return {
    graphNodeIds: normalizeTokenList([node.id]),
    sceneRefs: normalizeTokenList(node.scene_refs),
    eventRefs: normalizeTokenList(node.event_refs),
    eventIndexStart: Number.isFinite(eventIndexStart) && eventIndexStart > 0 ? eventIndexStart : null,
    eventIndexEnd: Number.isFinite(eventIndexEnd) && eventIndexEnd > 0 ? eventIndexEnd : null,
    nonce: `${node.id}:${Date.now()}`,
  };
}

function deriveActiveNodeIdsForEvent(nodes: WorkGraphNode[], event: AgentActivityEvent): string[] {
  if (!nodes.length) {
    return [];
  }
  const data = readRecord(event.data || event.metadata);
  const eventIndex = readActivityEventIndex(event);
  const targetGraphNodeIds = normalizeTokenListLower([event.graph_node_id, data["graph_node_id"], data["graph_node_ids"]]);
  const targetSceneRefs = normalizeTokenListLower([event.scene_ref, data["scene_ref"], data["scene_refs"]]);
  const targetEventRefs = normalizeTokenListLower([event.event_id, data["event_refs"]]);

  const matches: string[] = [];
  for (const node of nodes) {
    const nodeId = String(node.id || "").trim();
    if (!nodeId) {
      continue;
    }
    const normalizedNodeId = nodeId.toLowerCase();
    if (targetGraphNodeIds.includes(normalizedNodeId)) {
      matches.push(nodeId);
      continue;
    }
    const nodeEventRefs = normalizeTokenListLower(node.event_refs);
    if (targetEventRefs.some((ref) => nodeEventRefs.includes(ref))) {
      matches.push(nodeId);
      continue;
    }
    const nodeSceneRefs = normalizeTokenListLower(node.scene_refs);
    if (targetSceneRefs.some((ref) => nodeSceneRefs.includes(ref))) {
      matches.push(nodeId);
      continue;
    }
    const rangeStart = Number(node.event_index_start || 0);
    const rangeEnd = Number(node.event_index_end || rangeStart);
    if (
      Number.isFinite(eventIndex) &&
      eventIndex > 0 &&
      Number.isFinite(rangeStart) &&
      rangeStart > 0 &&
      eventIndex >= rangeStart &&
      eventIndex <= Math.max(rangeStart, rangeEnd || rangeStart)
    ) {
      matches.push(nodeId);
    }
  }

  return Array.from(new Set(matches));
}

function emitWorkGraphJumpTarget(jumpTarget: WorkGraphJumpTarget): void {
  if (typeof window === "undefined") {
    for (const listener of fallbackJumpListeners) {
      listener(jumpTarget);
    }
    return;
  }
  window.dispatchEvent(new CustomEvent(WORK_GRAPH_JUMP_EVENT, { detail: jumpTarget }));
}

function subscribeWorkGraphJumpTarget(listener: (jumpTarget: WorkGraphJumpTarget) => void): () => void {
  if (typeof window === "undefined") {
    fallbackJumpListeners.add(listener);
    return () => {
      fallbackJumpListeners.delete(listener);
    };
  }
  const handler = (event: Event) => {
    const customEvent = event as CustomEvent<WorkGraphJumpTarget>;
    const payload = customEvent?.detail;
    if (!payload) {
      return;
    }
    listener({
      graphNodeIds: normalizeTokenList(payload.graphNodeIds),
      sceneRefs: normalizeTokenList(payload.sceneRefs),
      eventRefs: normalizeTokenList(payload.eventRefs),
      eventIndexStart:
        Number.isFinite(Number(payload.eventIndexStart)) && Number(payload.eventIndexStart) > 0
          ? Number(payload.eventIndexStart)
          : null,
      eventIndexEnd:
        Number.isFinite(Number(payload.eventIndexEnd)) && Number(payload.eventIndexEnd) > 0
          ? Number(payload.eventIndexEnd)
          : null,
      nonce: String(payload.nonce || `${Date.now()}`),
    });
  };
  window.addEventListener(WORK_GRAPH_JUMP_EVENT, handler as EventListener);
  return () => {
    window.removeEventListener(WORK_GRAPH_JUMP_EVENT, handler as EventListener);
  };
}

export {
  buildWorkGraphJumpTarget,
  deriveActiveNodeIdsForEvent,
  emitWorkGraphJumpTarget,
  findTimelineIndexForJumpTarget,
  readActivityEventIndex,
  subscribeWorkGraphJumpTarget,
};
export type { WorkGraphJumpTarget };
