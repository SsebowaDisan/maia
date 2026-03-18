import type { MindmapPayload } from "./types";
import { computeDepths } from "./utils";

export const ROOT_X = 40;
export const TOP_PADDING = 36;
export const DEPTH_GAP = 460;
export const LEAF_GAP = 104;

const GENERIC_PAGE_TITLE_RE = /^(?:page|p)\s*\.?\s*\d+\s*$/i;
const CODEY_TITLE_RE = /(->|=>|::|[{}\[\]|`]|(?:\bconst\b|\blet\b|\bvar\b|\bfunction\b|\breturn\b))/i;

export function looksNoisyTitle(value: string): boolean {
  const text = String(value || "").trim();
  if (!text) {
    return true;
  }
  if (GENERIC_PAGE_TITLE_RE.test(text)) {
    return true;
  }
  if (CODEY_TITLE_RE.test(text)) {
    return true;
  }
  const alphaCount = (text.match(/[A-Za-z]/g) || []).length;
  const symbolCount = (text.match(/[=><{}\[\]|`~$]/g) || []).length;
  if (alphaCount === 0) {
    return true;
  }
  return symbolCount / Math.max(1, text.length) > 0.055;
}

export function looksLikePromptTitle(title: string): boolean {
  const value = title.trim().toLowerCase();
  if (!value) {
    return false;
  }
  if (value.includes("?")) {
    return true;
  }
  return /^(what|why|how|summarize|summary|explain|tell me|give me)\b/.test(value);
}

export function toMindmapPayload(
  raw: Record<string, unknown> | null | undefined,
): MindmapPayload | null {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  return raw as MindmapPayload;
}

export function computeInitialCollapsedFromPayload(
  payload: MindmapPayload | null,
  maxDepth: number,
): string[] {
  if (!payload || !Array.isArray(payload.nodes) || !Array.isArray(payload.edges)) {
    return [];
  }

  const nodes = payload.nodes;
  const hierarchyEdges = payload.edges.filter((edge) => !edge.type || edge.type === "hierarchy");
  if (!nodes.length || !hierarchyEdges.length) {
    return [];
  }

  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const childrenByParent = new Map<string, string[]>();
  const parentCount = new Map<string, number>();
  for (const edge of hierarchyEdges) {
    const rows = childrenByParent.get(edge.source) || [];
    rows.push(edge.target);
    childrenByParent.set(edge.source, rows);
    parentCount.set(edge.target, (parentCount.get(edge.target) || 0) + 1);
  }

  let rootId = String(payload.root_id || nodes[0]?.id || "");
  if (!rootId || !nodeById.has(rootId)) {
    const topLevel = nodes
      .filter((node) => (parentCount.get(node.id) || 0) === 0)
      .sort(
        (left, right) =>
          (childrenByParent.get(right.id)?.length || 0) -
          (childrenByParent.get(left.id)?.length || 0),
      );
    rootId = topLevel[0]?.id || nodes[0]?.id || "";
  }
  if (!rootId || !nodeById.has(rootId)) {
    return [];
  }

  const depthMap = computeDepths(rootId, hierarchyEdges);
  const collapsed = new Set<string>();
  const queue = [...(childrenByParent.get(rootId) || [])].filter(
    (nodeId) => (depthMap[nodeId] ?? Number.MAX_SAFE_INTEGER) <= maxDepth,
  );
  while (queue.length) {
    const nodeId = queue.shift() || "";
    const children = (childrenByParent.get(nodeId) || []).filter(
      (childId) => (depthMap[childId] ?? Number.MAX_SAFE_INTEGER) <= maxDepth,
    );
    if (children.length > 0) {
      collapsed.add(nodeId);
      children.forEach((childId) => queue.push(childId));
    }
  }
  return Array.from(collapsed);
}

export type NotebookLayoutParams = {
  rootId: string;
  nodeIds: Set<string>;
  childrenByParent: Map<string, string[]>;
  depthMap: Record<string, number>;
  collapsedSet: Set<string>;
  maxDepth: number;
  nodeOrder: Map<string, number>;
};

export function computeNotebookLayout(
  params: NotebookLayoutParams,
): Record<string, { x: number; y: number }> {
  const { rootId, nodeIds, childrenByParent, depthMap, collapsedSet, maxDepth, nodeOrder } =
    params;
  const positions: Record<string, { x: number; y: number }> = {};
  const placed = new Set<string>();
  let leafCursor = TOP_PADDING;

  const walk = (nodeId: string, depth: number): number => {
    if (!nodeIds.has(nodeId)) {
      return leafCursor;
    }

    const children = (childrenByParent.get(nodeId) || [])
      .filter(
        (child) => nodeIds.has(child) && (depthMap[child] ?? Number.MAX_SAFE_INTEGER) <= maxDepth,
      )
      .sort((left, right) => (nodeOrder.get(left) || 0) - (nodeOrder.get(right) || 0));

    const x = ROOT_X + depth * DEPTH_GAP;
    if (!children.length || collapsedSet.has(nodeId) || depth >= maxDepth) {
      const y = leafCursor;
      leafCursor += LEAF_GAP;
      positions[nodeId] = { x, y };
      placed.add(nodeId);
      return y;
    }

    const childYs = children.map((child) => walk(child, depth + 1));
    const y = (Math.min(...childYs) + Math.max(...childYs)) / 2;
    positions[nodeId] = { x, y };
    placed.add(nodeId);
    return y;
  };

  if (rootId && nodeIds.has(rootId)) {
    walk(rootId, 0);
  }

  const leftovers = Array.from(nodeIds)
    .filter((id) => !placed.has(id))
    .sort((left, right) => (depthMap[left] ?? 0) - (depthMap[right] ?? 0));

  leftovers.forEach((id, index) => {
    const depth = Math.max(1, depthMap[id] ?? 1);
    positions[id] = {
      x: ROOT_X + depth * DEPTH_GAP,
      y: leafCursor + index * LEAF_GAP,
    };
  });

  return positions;
}

// ─── Radial layout (Google NotebookLM style) ───────────────────────────────

/** Approximate half-width/height of a pill node — used to convert center→top-left position. */
export const NODE_HALF_W = 140;
export const NODE_HALF_H = 42;

/** Radius from root center to depth-1 branch nodes (px). */
export const RADIAL_BASE = 200;

/** Additional radius per depth level (px). */
export const RADIAL_FACTOR = 185;

function countSubtreeLeaves(
  nodeId: string,
  childrenByParent: Map<string, string[]>,
  nodeIds: Set<string>,
  collapsedSet: Set<string>,
  depthMap: Record<string, number>,
  maxDepth: number,
  cache: Map<string, number>,
): number {
  const cached = cache.get(nodeId);
  if (cached !== undefined) return cached;
  const children = (childrenByParent.get(nodeId) || []).filter(
    (c) => nodeIds.has(c) && (depthMap[c] ?? 99) <= maxDepth,
  );
  if (!children.length || collapsedSet.has(nodeId)) {
    cache.set(nodeId, 1);
    return 1;
  }
  const total = children.reduce(
    (sum, c) => sum + countSubtreeLeaves(c, childrenByParent, nodeIds, collapsedSet, depthMap, maxDepth, cache),
    0,
  );
  cache.set(nodeId, total);
  return total;
}

function placeRadialSubtree(
  nodeId: string,
  depth: number,
  centerAngle: number,
  halfSector: number,
  nodeIds: Set<string>,
  childrenByParent: Map<string, string[]>,
  collapsedSet: Set<string>,
  depthMap: Record<string, number>,
  maxDepth: number,
  leafCache: Map<string, number>,
  positions: Record<string, { x: number; y: number }>,
): void {
  if (!nodeIds.has(nodeId)) return;
  const radius = RADIAL_BASE + (depth - 1) * RADIAL_FACTOR;
  positions[nodeId] = {
    x: Math.round(Math.cos(centerAngle) * radius),
    y: Math.round(Math.sin(centerAngle) * radius),
  };
  const children = (childrenByParent.get(nodeId) || []).filter(
    (c) => nodeIds.has(c) && (depthMap[c] ?? 99) <= maxDepth,
  );
  if (!children.length || collapsedSet.has(nodeId) || depth >= maxDepth) return;

  const leafCounts = children.map((c) =>
    countSubtreeLeaves(c, childrenByParent, nodeIds, collapsedSet, depthMap, maxDepth, leafCache),
  );
  const totalLeaves = Math.max(1, leafCounts.reduce((a, b) => a + b, 0));
  // Cap spread so children stay in front of their parent (not wrapping around the root)
  const spread = Math.min(halfSector * 2, Math.PI);
  let childAngle = centerAngle - spread / 2;
  children.forEach((childId, i) => {
    const sector = (leafCounts[i] / totalLeaves) * spread;
    placeRadialSubtree(
      childId, depth + 1, childAngle + sector / 2, sector / 2,
      nodeIds, childrenByParent, collapsedSet, depthMap, maxDepth, leafCache, positions,
    );
    childAngle += sector;
  });
}

/**
 * Computes a radial (NotebookLM-style) layout.
 * Returns CENTER positions keyed by node id.
 * Root is placed at (0, 0); branches radiate outward proportionally by leaf count.
 */
export function computeRadialLayout(params: NotebookLayoutParams): Record<string, { x: number; y: number }> {
  const { rootId, nodeIds, childrenByParent, depthMap, collapsedSet, maxDepth } = params;
  const positions: Record<string, { x: number; y: number }> = {};
  if (!nodeIds.has(rootId)) return positions;

  positions[rootId] = { x: 0, y: 0 };

  const topChildren = (childrenByParent.get(rootId) || []).filter(
    (c) => nodeIds.has(c) && (depthMap[c] ?? 99) <= maxDepth,
  );
  if (!topChildren.length) return positions;

  const leafCache = new Map<string, number>();
  const leafCounts = topChildren.map((c) =>
    countSubtreeLeaves(c, childrenByParent, nodeIds, collapsedSet, depthMap, maxDepth, leafCache),
  );
  const total = Math.max(1, leafCounts.reduce((a, b) => a + b, 0));

  let angle = -Math.PI / 2; // start from top (12 o'clock)
  topChildren.forEach((childId, i) => {
    const sector = (leafCounts[i] / total) * (2 * Math.PI);
    placeRadialSubtree(
      childId, 1, angle + sector / 2, sector / 2,
      nodeIds, childrenByParent, collapsedSet, depthMap, maxDepth, leafCache, positions,
    );
    angle += sector;
  });

  return positions;
}
