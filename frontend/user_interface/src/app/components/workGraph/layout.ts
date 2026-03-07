import ELK from "elkjs/lib/elk.bundled.js";

import type { WorkGraphEdge, WorkGraphNode } from "./work_graph_types";

type WorkGraphPositionMap = Record<string, { x: number; y: number }>;

function roleKey(node: WorkGraphNode): string {
  return String(node.agent_role || "system").trim().toLowerCase() || "system";
}

function orderedRoles(nodes: WorkGraphNode[]): string[] {
  const preferred = ["planner", "research", "browser", "document_reader", "analyst", "writer", "verifier", "system"];
  const discovered = Array.from(new Set(nodes.map((node) => roleKey(node))));
  const seeded = preferred.filter((row) => discovered.includes(row));
  const remaining = discovered.filter((row) => !seeded.includes(row)).sort((left, right) => left.localeCompare(right));
  return [...seeded, ...remaining];
}

function edgeTargetMap(edges: WorkGraphEdge[]): Map<string, string[]> {
  const children = new Map<string, string[]>();
  for (const edge of edges) {
    if (edge.edge_family !== "hierarchy") {
      continue;
    }
    const rows = children.get(edge.source) || [];
    rows.push(edge.target);
    children.set(edge.source, rows);
  }
  return children;
}

function computeDepthMap(rootId: string, edges: WorkGraphEdge[]): Record<string, number> {
  if (!rootId) {
    return {};
  }
  const children = edgeTargetMap(edges);
  const depthMap: Record<string, number> = { [rootId]: 0 };
  const queue = [rootId];
  while (queue.length) {
    const current = queue.shift() || "";
    const currentDepth = depthMap[current] || 0;
    for (const child of children.get(current) || []) {
      if (typeof depthMap[child] === "number") {
        continue;
      }
      depthMap[child] = currentDepth + 1;
      queue.push(child);
    }
  }
  return depthMap;
}

function computeWorkGraphLayout(nodes: WorkGraphNode[], edges: WorkGraphEdge[], rootId: string): WorkGraphPositionMap {
  if (!nodes.length) {
    return {};
  }
  const depthMap = computeDepthMap(rootId, edges);
  const lanes = orderedRoles(nodes);
  const laneIndex = new Map<string, number>(lanes.map((lane, index) => [lane, index]));
  const laneDepthCursor = new Map<string, number>();
  const ordered = [...nodes].sort((left, right) => {
    const leftDepth = depthMap[left.id] ?? Number.MAX_SAFE_INTEGER;
    const rightDepth = depthMap[right.id] ?? Number.MAX_SAFE_INTEGER;
    if (leftDepth !== rightDepth) {
      return leftDepth - rightDepth;
    }
    const leftEvent = Number(left.event_index_start || 0);
    const rightEvent = Number(right.event_index_start || 0);
    return leftEvent - rightEvent || left.id.localeCompare(right.id);
  });
  const positions: WorkGraphPositionMap = {};
  for (const node of ordered) {
    const lane = laneIndex.get(roleKey(node)) ?? laneIndex.get("system") ?? 0;
    const depth = depthMap[node.id] ?? 1;
    const cursorKey = `${lane}:${depth}`;
    const offset = laneDepthCursor.get(cursorKey) || 0;
    laneDepthCursor.set(cursorKey, offset + 1);
    positions[node.id] = {
      x: 140 + depth * 290,
      y: 80 + lane * 180 + offset * 86,
    };
  }
  return positions;
}

async function computeWorkGraphLaneLayout(
  nodes: WorkGraphNode[],
  edges: WorkGraphEdge[],
  rootId: string,
  options?: { preferElk?: boolean },
): Promise<WorkGraphPositionMap> {
  if (!nodes.length) {
    return {};
  }
  const shouldUseElk = options?.preferElk !== false;
  const fallback = computeWorkGraphLayout(nodes, edges, rootId);
  if (!shouldUseElk) {
    return fallback;
  }
  try {
    const roleOrder = orderedRoles(nodes);
    const roleIndex = new Map<string, number>(roleOrder.map((role, index) => [role, index]));
    const elk = new ELK();
    const sortedNodes = [...nodes].sort((left, right) => left.id.localeCompare(right.id));
    const sortedEdges = [...edges]
      .filter((edge) => edge.source && edge.target)
      .sort((left, right) => left.id.localeCompare(right.id));
    const graph = {
      id: "work_graph",
      layoutOptions: {
        "elk.algorithm": "layered",
        "elk.direction": "RIGHT",
        "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
        "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
        "elk.spacing.nodeNode": "52",
        "elk.layered.spacing.nodeNodeBetweenLayers": "220",
        "elk.partitioning.activate": "true",
      },
      children: sortedNodes.map((node) => ({
        id: node.id,
        width: 250,
        height: 120,
        layoutOptions: {
          "org.eclipse.elk.partitioning.partition": String(roleIndex.get(roleKey(node)) ?? roleIndex.get("system") ?? 0),
        },
      })),
      edges: sortedEdges.map((edge) => ({
        id: edge.id,
        sources: [edge.source],
        targets: [edge.target],
      })),
    };
    const result = await elk.layout(graph as never);
    const children = Array.isArray((result as { children?: unknown[] }).children)
      ? ((result as { children?: Array<{ id?: string; x?: number; y?: number }> }).children || [])
      : [];
    const positioned: WorkGraphPositionMap = {};
    for (const child of children) {
      const nodeId = String(child.id || "").trim();
      if (!nodeId) {
        continue;
      }
      positioned[nodeId] = {
        x: Number(child.x || 0),
        y: Number(child.y || 0),
      };
    }
    if (!Object.keys(positioned).length) {
      return fallback;
    }
    for (const node of nodes) {
      if (!positioned[node.id]) {
        positioned[node.id] = fallback[node.id] || { x: 0, y: 0 };
      }
    }
    return positioned;
  } catch {
    return fallback;
  }
}

export { computeWorkGraphLaneLayout, computeWorkGraphLayout };
export type { WorkGraphPositionMap };

