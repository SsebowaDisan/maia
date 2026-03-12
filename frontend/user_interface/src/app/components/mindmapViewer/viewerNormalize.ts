import type { MindmapEdge, MindmapMapType, MindmapNode, MindmapPayload } from "./types";
import { looksNoisyTitle } from "./viewerHelpers";

type GroupDescriptor = {
  key: string;
  title: string;
  summary: string;
};

const SYNTHETIC_TITLE_RE = /^(?:src|sec|page|leaf|doc|node|cat)[_:-][a-z0-9]+$/i;

const GROUP_ORDER: Record<MindmapMapType, string[]> = {
  structure: ["topics", "web", "documents", "sources", "evidence", "other"],
  context_mindmap: ["web", "documents", "sources", "other"],
  evidence: ["claims", "evidence", "sources", "other"],
  work_graph: ["planning", "research", "evidence", "verification", "other"],
};

const SEMANTIC_GROUP_ORDER = [
  "fundamentals",
  "applications",
  "comparisons",
  "trends",
  "tools",
  "case_studies",
  "research",
  "sources",
] as const;

function buildChildrenByParent(edges: MindmapEdge[]): Map<string, string[]> {
  const map = new Map<string, string[]>();
  for (const edge of edges) {
    if (edge.type && edge.type !== "hierarchy") {
      continue;
    }
    const rows = map.get(edge.source) || [];
    rows.push(edge.target);
    map.set(edge.source, rows);
  }
  return map;
}

function buildParentCount(edges: MindmapEdge[]): Map<string, number> {
  const map = new Map<string, number>();
  for (const edge of edges) {
    if (edge.type && edge.type !== "hierarchy") {
      continue;
    }
    map.set(edge.target, (map.get(edge.target) || 0) + 1);
  }
  return map;
}

function resolveRootId(payload: MindmapPayload, nodes: MindmapNode[], edges: MindmapEdge[]): string {
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const childrenByParent = buildChildrenByParent(edges);
  const parentCount = buildParentCount(edges);
  const directRoot = String(payload.root_id || "");
  if (directRoot && nodeById.has(directRoot)) {
    return directRoot;
  }
  const topLevel = nodes
    .filter((node) => (parentCount.get(node.id) || 0) === 0)
    .sort(
      (left, right) =>
        (childrenByParent.get(right.id)?.length || 0) - (childrenByParent.get(left.id)?.length || 0),
    );
  return topLevel[0]?.id || nodes[0]?.id || "";
}

function looksDocumentLike(node: MindmapNode): boolean {
  const sourceName = String(node.source_name || node.title || "").trim().toLowerCase();
  const sourceType = String(node.source_type || "").trim().toLowerCase();
  return (
    sourceType.includes("pdf") ||
    sourceType.includes("document") ||
    sourceType.includes("file") ||
    /\.(pdf|docx?|pptx?|xlsx?|csv|txt|md)$/i.test(sourceName)
  );
}

function looksWebLike(node: MindmapNode): boolean {
  const sourceName = String(node.source_name || node.title || "").trim().toLowerCase();
  const nodeType = String(node.node_type || node.type || "").trim().toLowerCase();
  return (
    nodeType === "web_source" ||
    sourceName.startsWith("http://") ||
    sourceName.startsWith("https://")
  );
}

function classifyRootChild(node: MindmapNode, mapType: MindmapMapType): GroupDescriptor {
  const nodeType = String(node.node_type || node.type || "").trim().toLowerCase();

  if (mapType === "evidence") {
    if (nodeType === "claim") {
      return {
        key: "claims",
        title: "Claims",
        summary: "Key answer claims before drilling into supporting detail.",
      };
    }
    if (nodeType === "evidence") {
      return {
        key: "evidence",
        title: "Supporting evidence",
        summary: "Evidence snippets and pages that support the current answer.",
      };
    }
    if (nodeType === "source" || nodeType === "web_source") {
      return {
        key: "sources",
        title: "Supporting sources",
        summary: "Source branches connected to the claims in this answer.",
      };
    }
    return {
      key: "other",
      title: "Other branches",
      summary: "Additional branches that did not fit a primary evidence category.",
    };
  }

  if (mapType === "context_mindmap" || mapType === "structure") {
    if (nodeType === "claim" || nodeType === "evidence") {
      return {
        key: "evidence",
        title: "Evidence",
        summary: "Evidence-led branches connected to the current topic.",
      };
    }
    if (looksWebLike(node)) {
      return {
        key: "web",
        title: "Web research",
        summary: "Web sources grouped together so the map starts with clearer research branches.",
      };
    }
    if (looksDocumentLike(node)) {
      return {
        key: "documents",
        title: "Documents",
        summary: "Document-based branches grouped into a stable document lane.",
      };
    }
    if (nodeType === "source" || nodeType === "web_source" || node.source_name || node.source_id) {
      return {
        key: "sources",
        title: "Other sources",
        summary: "Additional sources that do not fall cleanly into web or document buckets.",
      };
    }
    if ((node.children || []).length > 0 || nodeType === "section" || nodeType === "page") {
      return {
        key: "topics",
        title: "Key branches",
        summary: "Primary topic branches before diving into individual sources or pages.",
      };
    }
    return {
      key: "other",
      title: "Other branches",
      summary: "Remaining branches that do not fit a stronger first-level category.",
    };
  }

  return {
    key: "other",
    title: "Other branches",
    summary: "Remaining branches that do not fit a stronger first-level category.",
  };
}

function cleanTopicTitle(value: string): string {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  const trimmed = text.replace(/\s*[|:/-]\s*[^|:/-]{0,14}$/g, "").trim();
  return (trimmed || text).slice(0, 54).trim();
}

function isUsableTopicTitle(value: string): boolean {
  const text = String(value || "").trim();
  if (!text) {
    return false;
  }
  if (SYNTHETIC_TITLE_RE.test(text)) {
    return false;
  }
  return !looksNoisyTitle(text);
}

function deriveRepresentativeTitle(
  nodeId: string,
  nodeById: Map<string, MindmapNode>,
  childrenByParent: Map<string, string[]>,
): string | null {
  const rootNode = nodeById.get(nodeId);
  const rootNodeType = String(rootNode?.node_type || rootNode?.type || "").trim().toLowerCase();
  const isSourceLikeRoot =
    rootNodeType === "source" ||
    rootNodeType === "web_source" ||
    rootNodeType === "page" ||
    Boolean(rootNode?.source_name || rootNode?.source_id);
  if (!isSourceLikeRoot) {
    const rootCandidates = [String(rootNode?.title || "").trim(), String(rootNode?.source_name || "").trim()];
    const preferredRoot = rootCandidates.find((candidate) => isUsableTopicTitle(candidate));
    if (preferredRoot) {
      return cleanTopicTitle(preferredRoot);
    }
  }

  const queue: Array<{ id: string; depth: number }> = [{ id: nodeId, depth: 0 }];
  const visited = new Set<string>();
  while (queue.length) {
    const current = queue.shift();
    if (!current || visited.has(current.id) || current.depth > 3) {
      continue;
    }
    visited.add(current.id);
    const node = nodeById.get(current.id);
    const nodeType = String(node?.node_type || node?.type || "").trim().toLowerCase();
    const title = String(node?.title || "").trim();
    if (
      isUsableTopicTitle(title) &&
      nodeType !== "source" &&
      nodeType !== "web_source" &&
      nodeType !== "page"
    ) {
      return cleanTopicTitle(title);
    }
    (childrenByParent.get(current.id) || []).forEach((childId) => {
      queue.push({ id: childId, depth: current.depth + 1 });
    });
  }
  return null;
}

function buildSemanticSignal(
  nodeId: string,
  nodeById: Map<string, MindmapNode>,
  childrenByParent: Map<string, string[]>,
): string {
  const segments: string[] = [];
  const queue: Array<{ id: string; depth: number }> = [{ id: nodeId, depth: 0 }];
  const visited = new Set<string>();

  while (queue.length && segments.length < 12) {
    const current = queue.shift();
    if (!current || visited.has(current.id) || current.depth > 2) {
      continue;
    }
    visited.add(current.id);
    const node = nodeById.get(current.id);
    if (!node) {
      continue;
    }
    const title = String(node.title || "").trim();
    if (title) {
      segments.push(title);
    }
    if (current.depth <= 1) {
      const summary = String(node.summary || node.text || "").replace(/\s+/g, " ").trim();
      if (summary) {
        segments.push(summary.slice(0, 140));
      }
    }
    const role = String(node.node_role || "").trim();
    if (role) {
      segments.push(role);
    }
    if (current.depth < 2) {
      (childrenByParent.get(current.id) || []).forEach((childId) => {
        queue.push({ id: childId, depth: current.depth + 1 });
      });
    }
  }

  return segments.join(" ");
}

function classifySemanticCategory(title: string): GroupDescriptor {
  const value = title.toLowerCase();
  if (/\b(what is|overview|introduction|understanding|basics|explained|guide|fundamental|definition)\b/.test(value)) {
    return {
      key: "fundamentals",
      title: "Fundamentals",
      summary: "Core definitions and overview branches that explain the topic at a high level.",
    };
  }
  if (/\b(application|applications|use case|use cases|real world|real-world|industry|industries)\b/.test(value)) {
    return {
      key: "applications",
      title: "Applications",
      summary: "How the topic is applied across products, industries, or practical scenarios.",
    };
  }
  if (/\b(vs|versus|difference|compare|comparison)\b/.test(value)) {
    return {
      key: "comparisons",
      title: "Comparisons",
      summary: "Branches that compare related concepts and clarify the differences between them.",
    };
  }
  if (/\b(trend|trends|future|forecast|projected|202[0-9]|impact|reshaping|market|business)\b/.test(value)) {
    return {
      key: "trends",
      title: "Trends & impact",
      summary: "How the topic is evolving, where it is heading, and what impact it is having.",
    };
  }
  if (/\b(tool|tools|framework|frameworks|platform|platforms|system|systems|design|github|library|stack|engineer|curated)\b/.test(value)) {
    return {
      key: "tools",
      title: "Tools & systems",
      summary: "Branches about tools, frameworks, platforms, and system-level implementations.",
    };
  }
  if (/\b(case study|case studies|example|examples)\b/.test(value)) {
    return {
      key: "case_studies",
      title: "Case studies",
      summary: "Concrete examples and case-study branches that show the topic in practice.",
    };
  }
  if (/\b(research|study|paper|survey|benchmark|evaluation)\b/.test(value)) {
    return {
      key: "research",
      title: "Research",
      summary: "Research-oriented branches including papers, studies, and benchmark material.",
    };
  }
  return {
    key: "sources",
    title: "Other sources",
    summary: "Additional branches that do not fit a stronger category yet.",
  };
}

function buildSemanticCategoryGroups(
  childIds: string[],
  nodeById: Map<string, MindmapNode>,
  childrenByParent: Map<string, string[]>,
): { groupedChildren: Map<string, string[]>; descriptors: Map<string, GroupDescriptor> } | null {
  const groupedChildren = new Map<string, string[]>();
  const descriptors = new Map<string, GroupDescriptor>();

  for (const childId of childIds) {
    const title = deriveRepresentativeTitle(childId, nodeById, childrenByParent);
    const signal = buildSemanticSignal(childId, nodeById, childrenByParent);
    const descriptor = classifySemanticCategory([title || "", signal].filter(Boolean).join(" "));
    const rows = groupedChildren.get(descriptor.key) || [];
    rows.push(childId);
    groupedChildren.set(descriptor.key, rows);
    if (!descriptors.has(descriptor.key)) {
      descriptors.set(descriptor.key, descriptor);
    }
  }

  const orderedGroups = SEMANTIC_GROUP_ORDER.filter((key) => (groupedChildren.get(key) || []).length > 0);
  if (!orderedGroups.length) {
    return null;
  }

  const finalGroupedChildren = new Map<string, string[]>();
  const finalDescriptors = new Map<string, GroupDescriptor>();
  orderedGroups.forEach((key) => {
    finalGroupedChildren.set(key, groupedChildren.get(key) || []);
    const descriptor = descriptors.get(key);
    if (descriptor) {
      finalDescriptors.set(key, descriptor);
    }
  });
  return { groupedChildren: finalGroupedChildren, descriptors: finalDescriptors };
}

function shouldGroup(mapType: MindmapMapType, rootChildren: string[], nodeById: Map<string, MindmapNode>): boolean {
  if (mapType === "work_graph") {
    return false;
  }
  if (rootChildren.length < 3) {
    return false;
  }
  if (mapType === "structure" || mapType === "context_mindmap") {
    return true;
  }
  const sourceLikeCount = rootChildren.reduce((count, nodeId) => {
    const node = nodeById.get(nodeId);
    const nodeType = String(node?.node_type || node?.type || "").trim().toLowerCase();
    if (
      nodeType === "source" ||
      nodeType === "web_source" ||
      nodeType === "claim" ||
      nodeType === "evidence" ||
      Boolean(node?.source_name || node?.source_id)
    ) {
      return count + 1;
    }
    return count;
  }, 0);
  return sourceLikeCount >= Math.ceil(rootChildren.length * 0.5);
}

export function normalizeMindmapPayloadForViewer(
  payload: MindmapPayload | null,
  mapType: MindmapMapType,
): MindmapPayload | null {
  if (!payload || !Array.isArray(payload.nodes) || !Array.isArray(payload.edges)) {
    return payload;
  }

  const rootId = resolveRootId(payload, payload.nodes, payload.edges);
  if (!rootId) {
    return payload;
  }

  const nodeById = new Map(payload.nodes.map((node) => [node.id, { ...node }]));
  const hierarchyEdges = payload.edges.filter((edge) => !edge.type || edge.type === "hierarchy");
  const nonHierarchyEdges = payload.edges.filter((edge) => edge.type && edge.type !== "hierarchy");
  const childrenByParent = buildChildrenByParent(hierarchyEdges);
  const rootChildren = (childrenByParent.get(rootId) || []).filter((nodeId) => nodeById.has(nodeId));

  if (!shouldGroup(mapType, rootChildren, nodeById)) {
    return payload;
  }

  const groupedChildren = new Map<string, string[]>();
  const descriptors = new Map<string, GroupDescriptor>();
  for (const childId of rootChildren) {
    const node = nodeById.get(childId);
    if (!node) {
      continue;
    }
    const descriptor = classifyRootChild(node, mapType);
    descriptors.set(descriptor.key, descriptor);
    const rows = groupedChildren.get(descriptor.key) || [];
    rows.push(childId);
    groupedChildren.set(descriptor.key, rows);
  }

  if (mapType === "structure") {
    const semanticGroups = buildSemanticCategoryGroups(rootChildren, nodeById, childrenByParent);
    if (semanticGroups) {
      groupedChildren.clear();
      descriptors.clear();
      semanticGroups.groupedChildren.forEach((ids, key) => groupedChildren.set(key, ids));
      semanticGroups.descriptors.forEach((descriptor, key) => descriptors.set(key, descriptor));
    }
  }

  if (!groupedChildren.size) {
    return payload;
  }

  const rootNode = nodeById.get(rootId);
  if (!rootNode) {
    return payload;
  }

  const semanticGroupKeys =
    mapType === "structure"
      ? SEMANTIC_GROUP_ORDER.filter((key) => (groupedChildren.get(key) || []).length > 0)
      : [];
  const topicGroupKeys = Array.from(groupedChildren.keys()).filter((key) => key.startsWith("topic:"));
  const orderedGroupKeys = [
    ...semanticGroupKeys,
    ...topicGroupKeys,
    ...GROUP_ORDER[mapType].filter((key) => (groupedChildren.get(key) || []).length > 0),
  ].filter((key, index, rows) => rows.indexOf(key) === index);
  if (!orderedGroupKeys.length) {
    return payload;
  }

  const normalizedNodes: MindmapNode[] = payload.nodes
    .filter((node) => node.id !== rootId)
    .map((node) => {
      const original = nodeById.get(node.id) || node;
      return {
        ...original,
        children: [...(original.children || [])],
      };
    });

  const syntheticGroupNodes: MindmapNode[] = orderedGroupKeys.map((groupKey) => {
    const descriptor = descriptors.get(groupKey)!;
    const childIds = groupedChildren.get(groupKey) || [];
    return {
      id: `${rootId}::group::${groupKey}`,
      title: descriptor.title,
      text: descriptor.summary,
      summary: descriptor.summary,
      synthetic: true,
      node_type: "group",
      type: mapType,
      children: childIds,
      source_count: childIds.length,
      citation_count: null,
    };
  });

  const syntheticIds = new Set(syntheticGroupNodes.map((node) => node.id));
  const rootChildSet = new Set(rootChildren);
  const normalizedHierarchyEdges = hierarchyEdges.filter(
    (edge) => !(edge.source === rootId && rootChildSet.has(edge.target)),
  );

  syntheticGroupNodes.forEach((groupNode) => {
    normalizedHierarchyEdges.push({
      id: `${rootId}->${groupNode.id}`,
      source: rootId,
      target: groupNode.id,
      type: "hierarchy",
    });
    (groupNode.children || []).forEach((childId) => {
      normalizedHierarchyEdges.push({
        id: `${groupNode.id}->${childId}`,
        source: groupNode.id,
        target: childId,
        type: "hierarchy",
      });
    });
  });

  const normalizedRootNode: MindmapNode = {
    ...rootNode,
    children: syntheticGroupNodes.map((node) => node.id),
  };

  return {
    ...payload,
    root_id: rootId,
    nodes: [normalizedRootNode, ...syntheticGroupNodes, ...normalizedNodes.filter((node) => !syntheticIds.has(node.id))],
    edges: [...normalizedHierarchyEdges, ...nonHierarchyEdges],
  };
}
