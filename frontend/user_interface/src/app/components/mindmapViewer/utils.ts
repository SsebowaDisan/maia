import type { Edge, Node } from "@xyflow/react";

export type CanvasState = {
  collapsedNodeIds: string[];
  showReasoningMap: boolean;
  layoutMode: "vertical" | "horizontal";
  nodePositions: Record<string, { x: number; y: number }>;
};

export type MindNodeData = {
  title: string;
  subtitle?: string;
  hasChildren: boolean;
  collapsed: boolean;
  onToggle: (nodeId: string) => void;
  onAsk?: (nodeId: string) => void;
};

export const STORAGE_PREFIX = "maia.mindmap.viewer.v1";

export function hashText(value: string): string {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash >>> 0).toString(36);
}

export function storageKey(
  payload: { title?: string; root_id?: string } | null,
  conversationId?: string | null,
): string {
  const title = String(payload?.title || payload?.root_id || "mindmap");
  const conv = String(conversationId || "global");
  return `${STORAGE_PREFIX}:${conv}:${hashText(title)}`;
}

export function parseCanvasState(value: string | null): CanvasState | null {
  if (!value) {
    return null;
  }
  try {
    const parsed = JSON.parse(value) as Partial<CanvasState>;
    return {
      collapsedNodeIds: Array.isArray(parsed.collapsedNodeIds)
        ? parsed.collapsedNodeIds.filter((row): row is string => typeof row === "string")
        : [],
      showReasoningMap: Boolean(parsed.showReasoningMap),
      layoutMode: parsed.layoutMode === "horizontal" ? "horizontal" : "vertical",
      nodePositions:
        parsed.nodePositions && typeof parsed.nodePositions === "object"
          ? (parsed.nodePositions as Record<string, { x: number; y: number }>)
          : {},
    };
  } catch {
    return null;
  }
}

export function computeDepths(
  rootId: string,
  edges: Array<{ source: string; target: string; type?: string }>,
): Record<string, number> {
  const childrenByParent = new Map<string, string[]>();
  for (const edge of edges) {
    if (edge.type && edge.type !== "hierarchy") {
      continue;
    }
    const list = childrenByParent.get(edge.source) || [];
    list.push(edge.target);
    childrenByParent.set(edge.source, list);
  }
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
  const minX = Math.min(...xValues) - 120;
  const minY = Math.min(...yValues) - 80;
  const maxX = Math.max(...xValues) + 320;
  const maxY = Math.max(...yValues) + 200;
  const width = Math.max(800, Math.round(maxX - minX));
  const height = Math.max(500, Math.round(maxY - minY));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    return;
  }
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);
  const byId = new Map(nodes.map((node) => [node.id, node]));
  ctx.strokeStyle = "#d2d2d7";
  ctx.lineWidth = 1.2;
  for (const edge of edges) {
    const source = byId.get(edge.source);
    const target = byId.get(edge.target);
    if (!source || !target) {
      continue;
    }
    const sx = source.position.x - minX + 150;
    const sy = source.position.y - minY + 22;
    const tx = target.position.x - minX;
    const ty = target.position.y - minY + 22;
    ctx.beginPath();
    ctx.moveTo(sx, sy);
    ctx.lineTo(tx, ty);
    ctx.stroke();
  }
  for (const node of nodes) {
    const x = node.position.x - minX;
    const y = node.position.y - minY;
    ctx.fillStyle = "#ffffff";
    ctx.strokeStyle = "#d2d2d7";
    ctx.lineWidth = 1;
    ctx.fillRect(x, y, 150, 44);
    ctx.strokeRect(x, y, 150, 44);
    ctx.fillStyle = "#1d1d1f";
    ctx.font = "12px sans-serif";
    ctx.fillText(String(node.data.title || "").slice(0, 24), x + 8, y + 18);
    const subtitle = String(node.data.subtitle || "");
    if (subtitle) {
      ctx.fillStyle = "#6e6e73";
      ctx.font = "10px sans-serif";
      ctx.fillText(subtitle.slice(0, 28), x + 8, y + 34);
    }
  }
  const link = document.createElement("a");
  link.href = canvas.toDataURL("image/png");
  link.download = `${title || "mindmap"}.png`;
  link.click();
}

