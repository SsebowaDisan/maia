import type { WorkGraphEdge, WorkGraphNode } from "./work_graph_types";

type WorkGraphSearchFilters = {
  query: string;
  agentRole: string;
  status: string;
  confidence: "all" | "low" | "medium_high";
  focusMode: boolean;
  edgeFamily: string;
};

function normalizeText(value: unknown): string {
  return String(value || "").trim().toLowerCase();
}

function fuzzyMatch(text: string, query: string): boolean {
  const source = normalizeText(text);
  const target = normalizeText(query);
  if (!target) {
    return true;
  }
  if (source.includes(target)) {
    return true;
  }
  let cursor = 0;
  for (const char of source) {
    if (char === target[cursor]) {
      cursor += 1;
      if (cursor >= target.length) {
        return true;
      }
    }
  }
  return false;
}

function nodeMatchesFilters(node: WorkGraphNode, filters: WorkGraphSearchFilters): boolean {
  const status = normalizeText(node.status);
  const role = normalizeText(node.agent_role || "system");
  const confidence = Number(node.confidence);

  if (filters.focusMode && status === "completed") {
    return false;
  }
  if (filters.status !== "all" && status !== normalizeText(filters.status)) {
    return false;
  }
  if (filters.agentRole !== "all" && role !== normalizeText(filters.agentRole)) {
    return false;
  }
  if (filters.confidence === "low") {
    if (!(Number.isFinite(confidence) && confidence >= 0 && confidence < 0.6)) {
      return false;
    }
  }
  if (filters.confidence === "medium_high") {
    if (!(Number.isFinite(confidence) && confidence >= 0.6)) {
      return false;
    }
  }

  const query = filters.query;
  if (!query) {
    return true;
  }
  const metadataText = JSON.stringify(node.metadata || {});
  const searchableText = `${node.id} ${node.title || ""} ${node.detail || ""} ${role} ${status} ${metadataText}`;
  return fuzzyMatch(searchableText, query);
}

function filterWorkGraphNodes(nodes: WorkGraphNode[], filters: WorkGraphSearchFilters): WorkGraphNode[] {
  return nodes.filter((node) => nodeMatchesFilters(node, filters));
}

function filterWorkGraphEdges(
  edges: WorkGraphEdge[],
  visibleNodeIds: Set<string>,
  edgeFamily: string,
): WorkGraphEdge[] {
  const family = normalizeText(edgeFamily);
  return edges.filter((edge) => {
    if (!visibleNodeIds.has(edge.source) || !visibleNodeIds.has(edge.target)) {
      return false;
    }
    if (family === "all") {
      return true;
    }
    return normalizeText(edge.edge_family) === family;
  });
}

function hiddenNodeIdsForCollapsed(
  nodes: WorkGraphNode[],
  edges: WorkGraphEdge[],
  collapsedNodeIds: string[],
): Set<string> {
  const visibleNodes = new Set(nodes.map((node) => node.id));
  const adjacency = new Map<string, string[]>();
  for (const edge of edges) {
    if (edge.edge_family !== "hierarchy") {
      continue;
    }
    if (!visibleNodes.has(edge.source) || !visibleNodes.has(edge.target)) {
      continue;
    }
    const current = adjacency.get(edge.source) || [];
    current.push(edge.target);
    adjacency.set(edge.source, current);
  }

  const hidden = new Set<string>();
  const stack = [...collapsedNodeIds];
  while (stack.length > 0) {
    const current = stack.pop() || "";
    const children = adjacency.get(current) || [];
    for (const child of children) {
      if (hidden.has(child)) {
        continue;
      }
      hidden.add(child);
      stack.push(child);
    }
  }
  return hidden;
}

function toggleCollapsedNodeIds(collapsedNodeIds: string[], nodeId: string): string[] {
  const normalizedNodeId = String(nodeId || "").trim();
  if (!normalizedNodeId) {
    return collapsedNodeIds;
  }
  if (collapsedNodeIds.includes(normalizedNodeId)) {
    return collapsedNodeIds.filter((id) => id !== normalizedNodeId);
  }
  return [...collapsedNodeIds, normalizedNodeId];
}

export {
  filterWorkGraphEdges,
  filterWorkGraphNodes,
  fuzzyMatch,
  hiddenNodeIdsForCollapsed,
  toggleCollapsedNodeIds,
};
export type { WorkGraphSearchFilters };
