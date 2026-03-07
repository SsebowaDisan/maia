import type { Edge, Node } from "@xyflow/react";

export type MindmapMapType = "structure" | "evidence" | "work_graph";

export type CanvasState = {
  collapsedNodeIds: string[];
  showReasoningMap: boolean;
  layoutMode: "balanced" | "horizontal";
  nodePositions: Record<string, { x: number; y: number }>;
  activeMapType: MindmapMapType;
  focusedNodeId: string | null;
};

export type MindNodeData = {
  title: string;
  subtitle?: string;
  hasChildren: boolean;
  collapsed: boolean;
  nodeType: string;
  isRoot?: boolean;
  depth?: number;
  isSelected?: boolean;
  onToggle: (nodeId: string) => void;
  onAsk?: (nodeId: string) => void;
  onFocus?: (nodeId: string) => void;
};

export type BalancedLayoutParams = {
  rootId: string;
  nodes: Array<{ id: string }>;
  edges: Array<{ source: string; target: string; type?: string }>;
  collapsedNodeIds: string[];
  maxDepth: number;
  centerX?: number;
  centerY?: number;
  depthGap?: number;
  leafGap?: number;
};

export const STORAGE_PREFIX = "maia.mindmap.viewer.v4";

export function hashText(value: string): string {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash >>> 0).toString(36);
}

export function storageKey(
  payload: { title?: string; root_id?: string; nodes?: unknown[]; edges?: unknown[] } | null,
  conversationId?: string | null,
): string {
  const title = String(payload?.title || "mindmap");
  const root = String(payload?.root_id || "");
  const nodeCount = Array.isArray(payload?.nodes) ? payload.nodes.length : 0;
  const edgeCount = Array.isArray(payload?.edges) ? payload.edges.length : 0;
  const conv = String(conversationId || "global");
  const signature = `${title}|${root}|${nodeCount}|${edgeCount}`;
  return `${STORAGE_PREFIX}:${conv}:${hashText(signature)}`;
}

export function parseCanvasState(value: string | null): CanvasState | null {
  if (!value) {
    return null;
  }
  try {
    const parsed = JSON.parse(value) as Partial<CanvasState>;
    const rawMapType = String(parsed.activeMapType || "").trim().toLowerCase();
    return {
      collapsedNodeIds: Array.isArray(parsed.collapsedNodeIds)
        ? parsed.collapsedNodeIds.filter((row): row is string => typeof row === "string")
        : [],
      showReasoningMap: Boolean(parsed.showReasoningMap),
      layoutMode: parsed.layoutMode === "horizontal" ? "horizontal" : "balanced",
      nodePositions:
        parsed.nodePositions && typeof parsed.nodePositions === "object"
          ? (parsed.nodePositions as Record<string, { x: number; y: number }>)
          : {},
      activeMapType:
        rawMapType === "work_graph"
          ? "work_graph"
          : rawMapType === "evidence"
            ? "evidence"
            : "structure",
      focusedNodeId:
        parsed.focusedNodeId && typeof parsed.focusedNodeId === "string"
          ? parsed.focusedNodeId
          : null,
    };
  } catch {
    return null;
  }
}

export function childrenMapFromEdges(
  edges: Array<{ source: string; target: string; type?: string }>,
): Map<string, string[]> {
  const map = new Map<string, string[]>();
  for (const edge of edges) {
    if (edge.type && edge.type !== "hierarchy") {
      continue;
    }
    const list = map.get(edge.source) || [];
    list.push(edge.target);
    map.set(edge.source, list);
  }
  return map;
}

export function computeDepths(
  rootId: string,
  edges: Array<{ source: string; target: string; type?: string }>,
): Record<string, number> {
  const childrenByParent = childrenMapFromEdges(edges);
  const depthMap: Record<string, number> = { [rootId]: 0 };
  const queue: string[] = [rootId];
  while (queue.length) {
    const current = queue.shift() || "";
    const currentDepth = depthMap[current] || 0;
    for (const child of childrenByParent.get(current) || []) {
      if (typeof depthMap[child] === "number") {
        continue;
      }
      depthMap[child] = currentDepth + 1;
      queue.push(child);
    }
  }
  return depthMap;
}

export function isDescendant(
  nodeId: string,
  collapsedId: string,
  childrenByParent: Map<string, string[]>,
): boolean {
  const stack = [...(childrenByParent.get(collapsedId) || [])];
  while (stack.length) {
    const current = stack.pop() || "";
    if (current === nodeId) {
      return true;
    }
    for (const next of childrenByParent.get(current) || []) {
      stack.push(next);
    }
  }
  return false;
}

function countVisibleLeaves(
  nodeId: string,
  params: {
    childrenByParent: Map<string, string[]>;
    collapsedSet: Set<string>;
    depthMap: Record<string, number>;
    maxDepth: number;
  },
): number {
  const { childrenByParent, collapsedSet, depthMap, maxDepth } = params;
  const depth = depthMap[nodeId] ?? 0;
  if (depth >= maxDepth || collapsedSet.has(nodeId)) {
    return 1;
  }
  const children = (childrenByParent.get(nodeId) || []).filter(
    (child) => (depthMap[child] ?? Number.MAX_SAFE_INTEGER) <= maxDepth,
  );
  if (!children.length) {
    return 1;
  }
  return children.reduce(
    (total, child) =>
      total +
      countVisibleLeaves(child, {
        childrenByParent,
        collapsedSet,
        depthMap,
        maxDepth,
      }),
    0,
  );
}

export function computeBalancedLayout({
  rootId,
  nodes,
  edges,
  collapsedNodeIds,
  maxDepth,
  centerX = 0,
  centerY = 0,
  depthGap = 240,
  leafGap = 120,
}: BalancedLayoutParams): Record<string, { x: number; y: number }> {
  const ids = new Set(nodes.map((node) => node.id));
  if (!ids.has(rootId)) {
    return {};
  }
  const childrenByParent = childrenMapFromEdges(edges);
  const depthMap = computeDepths(rootId, edges);
  const collapsedSet = new Set(collapsedNodeIds || []);
  const sideByNode = new Map<string, "left" | "right" | "center">([[rootId, "center"]]);

  const topChildren = (childrenByParent.get(rootId) || []).filter((child) => ids.has(child));
  topChildren.forEach((child, index) => {
    const side = index % 2 === 0 ? "left" : "right";
    sideByNode.set(child, side);
  });

  const sideQueue = [...topChildren];
  while (sideQueue.length) {
    const current = sideQueue.shift() || "";
    const currentSide = sideByNode.get(current) || "right";
    for (const child of childrenByParent.get(current) || []) {
      if (!ids.has(child)) {
        continue;
      }
      sideByNode.set(child, currentSide);
      sideQueue.push(child);
    }
  }

  const leftLeaves = topChildren
    .filter((id) => sideByNode.get(id) === "left")
    .reduce(
      (sum, id) =>
        sum +
        countVisibleLeaves(id, {
          childrenByParent,
          collapsedSet,
          depthMap,
          maxDepth,
        }),
      0,
    );
  const rightLeaves = topChildren
    .filter((id) => sideByNode.get(id) === "right")
    .reduce(
      (sum, id) =>
        sum +
        countVisibleLeaves(id, {
          childrenByParent,
          collapsedSet,
          depthMap,
          maxDepth,
        }),
      0,
    );

  const leafCursor = {
    left: centerY - Math.max(0, (leftLeaves - 1) * leafGap) / 2,
    right: centerY - Math.max(0, (rightLeaves - 1) * leafGap) / 2,
  };
  const positioned = new Map<string, { x: number; y: number }>();
  positioned.set(rootId, { x: centerX, y: centerY });

  const placeNode = (nodeId: string): number => {
    const side = sideByNode.get(nodeId) || "right";
    const depth = depthMap[nodeId] ?? 1;
    const x = centerX + (side === "left" ? -1 : 1) * depth * depthGap;
    const children = (childrenByParent.get(nodeId) || []).filter((child) => {
      const childDepth = depthMap[child] ?? Number.MAX_SAFE_INTEGER;
      return ids.has(child) && childDepth <= maxDepth;
    });

    if (!children.length || collapsedSet.has(nodeId) || depth >= maxDepth) {
      const y = leafCursor[side];
      leafCursor[side] += leafGap;
      positioned.set(nodeId, { x, y });
      return y;
    }

    const childYs = children.map((childId) => placeNode(childId));
    const y = childYs.reduce((sum, value) => sum + value, 0) / Math.max(1, childYs.length);
    positioned.set(nodeId, { x, y });
    return y;
  };

  for (const child of topChildren) {
    const depth = depthMap[child] ?? Number.MAX_SAFE_INTEGER;
    if (depth > maxDepth) {
      continue;
    }
    placeNode(child);
  }

  return Object.fromEntries(positioned.entries());
}

export function focusedBranchIds(
  nodeId: string,
  edges: Array<{ source: string; target: string; type?: string }>,
): Set<string> {
  const result = new Set<string>([nodeId]);
  const childrenByParent = childrenMapFromEdges(edges);
  const parentByChild = new Map<string, string>();
  for (const [parent, children] of childrenByParent.entries()) {
    for (const child of children) {
      parentByChild.set(child, parent);
    }
  }
  const stack = [...(childrenByParent.get(nodeId) || [])];
  while (stack.length) {
    const current = stack.pop() || "";
    if (result.has(current)) {
      continue;
    }
    result.add(current);
    for (const child of childrenByParent.get(current) || []) {
      stack.push(child);
    }
  }
  let cursor = parentByChild.get(nodeId);
  while (cursor) {
    if (result.has(cursor)) {
      break;
    }
    result.add(cursor);
    cursor = parentByChild.get(cursor);
  }
  return result;
}

export function mapPayloadToMarkdown(payload: Record<string, unknown>): string {
  const title = String(payload.title || "Mind-map");
  const lines = [`# ${title}`];
  const tree = payload.tree;
  if (tree && typeof tree === "object") {
    const walk = (node: Record<string, unknown>, depth: number) => {
      const label = String(node.title || node.id || "Node");
      const page = String(node.page || "").trim();
      lines.push(`${"  ".repeat(depth)}- ${page ? `${label} (page ${page})` : label}`);
      const children = Array.isArray(node.children)
        ? (node.children as Record<string, unknown>[])
        : [];
      children.forEach((child) => walk(child, depth + 1));
    };
    lines.push("");
    walk(tree as Record<string, unknown>, 0);
    return lines.join("\n");
  }

  const nodes = Array.isArray(payload.nodes)
    ? (payload.nodes as Record<string, unknown>[])
    : [];
  lines.push("");
  lines.push("## Nodes");
  nodes.forEach((node) => {
    lines.push(`- ${String(node.title || node.id || "Node")}`);
  });
  return lines.join("\n");
}

export function drawPngFromLayout(
  nodes: Node<MindNodeData>[],
  edges: Edge[],
  title: string,
) {
  if (!nodes.length) {
    return;
  }
  const xValues = nodes.map((node) => node.position.x);
  const yValues = nodes.map((node) => node.position.y);
  const minX = Math.min(...xValues) - 140;
  const minY = Math.min(...yValues) - 120;
  const maxX = Math.max(...xValues) + 340;
  const maxY = Math.max(...yValues) + 220;
  const width = Math.max(980, Math.round(maxX - minX));
  const height = Math.max(620, Math.round(maxY - minY));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    return;
  }
  ctx.fillStyle = "#f2f2f7";
  ctx.fillRect(0, 0, width, height);
  const byId = new Map(nodes.map((node) => [node.id, node]));
  ctx.strokeStyle = "#c7c7cc";
  ctx.lineWidth = 1.4;
  for (const edge of edges) {
    const source = byId.get(edge.source);
    const target = byId.get(edge.target);
    if (!source || !target) {
      continue;
    }
    const sx = source.position.x - minX + 156;
    const sy = source.position.y - minY + 24;
    const tx = target.position.x - minX;
    const ty = target.position.y - minY + 24;
    ctx.beginPath();
    ctx.moveTo(sx, sy);
    ctx.lineTo(tx, ty);
    ctx.stroke();
  }
  for (const node of nodes) {
    const x = node.position.x - minX;
    const y = node.position.y - minY;
    ctx.fillStyle = "#ffffff";
    ctx.strokeStyle = "#d1d1d6";
    ctx.lineWidth = 1;
    const radius = 12;
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.lineTo(x + 156 - radius, y);
    ctx.quadraticCurveTo(x + 156, y, x + 156, y + radius);
    ctx.lineTo(x + 156, y + 48 - radius);
    ctx.quadraticCurveTo(x + 156, y + 48, x + 156 - radius, y + 48);
    ctx.lineTo(x + radius, y + 48);
    ctx.quadraticCurveTo(x, y + 48, x, y + 48 - radius);
    ctx.lineTo(x, y + radius);
    ctx.quadraticCurveTo(x, y, x + radius, y);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = "#1d1d1f";
    ctx.font = '600 12px -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Segoe UI", Helvetica, Arial, sans-serif';
    ctx.fillText(String(node.data.title || "").slice(0, 24), x + 10, y + 18);
    const subtitle = String(node.data.subtitle || "");
    if (subtitle) {
      ctx.fillStyle = "#6e6e73";
      ctx.font = '10px -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Segoe UI", Helvetica, Arial, sans-serif';
      ctx.fillText(subtitle.slice(0, 28), x + 10, y + 34);
    }
  }
  const link = document.createElement("a");
  link.href = canvas.toDataURL("image/png");
  link.download = `${title || "mindmap"}.png`;
  link.click();
}
