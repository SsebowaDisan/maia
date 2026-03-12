import type { FocusNodePayload, MindmapEdge, MindmapNode, MindmapPayload } from "./types";
import { looksLikePromptTitle } from "./viewerHelpers";

export function toFocusPayload(node: MindmapNode | null): FocusNodePayload | null {
  if (!node || node.synthetic) {
    return null;
  }
  return {
    nodeId: node.id,
    title: node.title || "",
    text: node.text || node.summary || "",
    pageRef: node.page_ref || node.page || undefined,
    sourceId: node.source_id,
    sourceName: node.source_name,
  };
}

export function buildChildrenByParent(edges: MindmapEdge[]): Map<string, string[]> {
  const map = new Map<string, string[]>();
  for (const edge of edges) {
    const rows = map.get(edge.source) || [];
    rows.push(edge.target);
    map.set(edge.source, rows);
  }
  return map;
}

export function buildParentCount(edges: MindmapEdge[]): Map<string, number> {
  const map = new Map<string, number>();
  for (const edge of edges) {
    map.set(edge.target, (map.get(edge.target) || 0) + 1);
  }
  return map;
}

export function resolveRootId(
  payload: MindmapPayload | null,
  parsedNodes: MindmapNode[],
  nodeById: Map<string, MindmapNode>,
  parentCount: Map<string, number>,
  childrenByParent: Map<string, string[]>,
): string {
  let candidate = String(payload?.root_id || "");
  if (!candidate || !nodeById.has(candidate)) {
    const topLevel = parsedNodes
      .filter((node) => (parentCount.get(node.id) || 0) === 0)
      .sort(
        (left, right) =>
          (childrenByParent.get(right.id)?.length || 0) - (childrenByParent.get(left.id)?.length || 0),
      );
    candidate = topLevel[0]?.id || parsedNodes[0]?.id || "";
  }
  if (!candidate || !nodeById.has(candidate)) {
    return "";
  }
  const candidateNode = nodeById.get(candidate);
  const childRows = (childrenByParent.get(candidate) || []).filter((nodeId) => nodeById.has(nodeId));
  if (candidateNode && childRows.length === 1 && looksLikePromptTitle(String(candidateNode.title || ""))) {
    const childId = childRows[0];
    const childNode = nodeById.get(childId);
    const childType = String(childNode?.node_type || childNode?.type || "").toLowerCase();
    const childVisibleChildren = (childrenByParent.get(childId) || []).length;
    if ((childType === "source" || childType === "web_source") && childVisibleChildren <= 8) {
      return childId;
    }
  }
  return candidate;
}

export function buildBranchColorIndexMap(
  childrenByParent: Map<string, string[]>,
  nodeById: Map<string, MindmapNode>,
  rootId: string,
): Map<string, number> {
  const map = new Map<string, number>();
  const topLevelChildren = (childrenByParent.get(rootId) || []).filter((id) => nodeById.has(id));
  topLevelChildren.forEach((childId, branchIndex) => {
    const queue = [childId];
    while (queue.length) {
      const id = queue.shift()!;
      if (map.has(id)) {
        continue;
      }
      map.set(id, branchIndex);
      (childrenByParent.get(id) || []).forEach((childIdEntry) => queue.push(childIdEntry));
    }
  });
  return map;
}

export function buildNodeOrder(parsedNodes: MindmapNode[], depthMap: Record<string, number>): Map<string, number> {
  const order = new Map<string, number>();
  parsedNodes.forEach((node, index) => {
    const pageRaw = String(node.page_ref || node.page || "");
    const pageMatch = pageRaw.match(/\d+/)?.[0];
    const pageNumber = pageMatch ? Number.parseInt(pageMatch, 10) : Number.NaN;
    const rank = Number.isFinite(pageNumber) ? pageNumber * 1000 : (depthMap[node.id] ?? 99) * 1000 + index;
    order.set(node.id, rank + index / 1000);
  });
  return order;
}
