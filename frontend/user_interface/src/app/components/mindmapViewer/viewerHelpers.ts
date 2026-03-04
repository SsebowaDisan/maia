import type { MindmapPayload } from "./types";
import { computeDepths } from "./utils";

export const ROOT_X = 96;
export const TOP_PADDING = 46;
export const DEPTH_GAP = 312;
export const LEAF_GAP = 84;

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

  const rootNode = nodeById.get(rootId);
  const rootChildren = childrenByParent.get(rootId) || [];
  if (rootNode && rootChildren.length === 1 && looksLikePromptTitle(String(rootNode.title || ""))) {
    rootId = rootChildren[0];
  }

  const depthMap = computeDepths(rootId, hierarchyEdges);
  let parentForInitialView = rootId;
  const children = (childrenByParent.get(rootId) || []).filter(
    (nodeId) => (depthMap[nodeId] ?? Number.MAX_SAFE_INTEGER) <= maxDepth,
  );
  if (children.length === 1) {
    const onlyChild = children[0];
    const onlyNode = nodeById.get(onlyChild);
    const onlyType = String(onlyNode?.node_type || onlyNode?.type || "").toLowerCase();
    const onlyChildVisibleChildren = (childrenByParent.get(onlyChild) || []).filter(
      (nodeId) => (depthMap[nodeId] ?? Number.MAX_SAFE_INTEGER) <= maxDepth,
    ).length;
    const shouldPromoteSourceLayer =
      (onlyType === "source" || onlyType === "web_source") &&
      onlyChildVisibleChildren > 0 &&
      onlyChildVisibleChildren <= 8;
    if (shouldPromoteSourceLayer) {
      parentForInitialView = onlyChild;
    }
  }

  const firstLayer = (childrenByParent.get(parentForInitialView) || []).filter(
    (nodeId) => (depthMap[nodeId] ?? Number.MAX_SAFE_INTEGER) <= maxDepth,
  );

  return firstLayer.filter((nodeId) => {
    const descendants = (childrenByParent.get(nodeId) || []).filter(
      (childId) => (depthMap[childId] ?? Number.MAX_SAFE_INTEGER) <= maxDepth,
    );
    return descendants.length > 0;
  });
}

type NotebookLayoutParams = {
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
