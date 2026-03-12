import type { MindmapMapType, MindmapPayload } from "./types";

export type ViewerLayoutMode = "balanced" | "horizontal";

export type MindmapPresentation = {
  eyebrow: string;
  label: string;
  summary: string;
  layoutLabel: string;
  preferredLayout: ViewerLayoutMode;
};

export type MindmapArtifactSummary = {
  title: string;
  activeMapType: MindmapMapType;
  presentation: MindmapPresentation;
  availableMapTypes: MindmapMapType[];
  nodeCount: number;
  sourceCount: number | null;
  actionCount: number | null;
};

const MAP_TYPE_ORDER: MindmapMapType[] = [
  "context_mindmap",
  "structure",
  "evidence",
  "work_graph",
];

export function normalizeMindmapMapType(raw: unknown): MindmapMapType {
  const value = String(raw || "").trim().toLowerCase();
  if (value === "context_mindmap") {
    return "context_mindmap";
  }
  if (value === "work_graph") {
    return "work_graph";
  }
  if (value === "evidence") {
    return "evidence";
  }
  return "structure";
}

export function preferredLayoutForMapType(mapType: MindmapMapType): ViewerLayoutMode {
  return "horizontal";
}

export function preferredLayoutForPayload(
  payload: MindmapPayload | null,
  fallbackMapType: MindmapMapType,
): ViewerLayoutMode {
  const hint = String(payload?.view_hint || "").trim().toLowerCase();
  if (hint === "tree" || hint === "horizontal") {
    return "horizontal";
  }
  if (hint === "radial" || hint === "balanced") {
    return "balanced";
  }
  return preferredLayoutForMapType(fallbackMapType);
}

export function describeMindmapMapType(mapType: MindmapMapType): MindmapPresentation {
  switch (mapType) {
    case "context_mindmap":
      return {
        eyebrow: "Research artifact",
        label: "Source map",
        summary: "Browse the answer context as a calmer source tree grouped around the research surface.",
        layoutLabel: "Tree first",
        preferredLayout: "horizontal",
      };
    case "evidence":
      return {
        eyebrow: "Research artifact",
        label: "Evidence map",
        summary: "Trace which claims connect to pages, sources, and supporting evidence without losing the answer flow.",
        layoutLabel: "Tree first",
        preferredLayout: "horizontal",
      };
    case "work_graph":
      return {
        eyebrow: "Runtime artifact",
        label: "Execution map",
        summary: "Review the agent path as a clean execution tree with phases, actions, and evidence branches.",
        layoutLabel: "Tree first",
        preferredLayout: "horizontal",
      };
    default:
      return {
        eyebrow: "Research artifact",
        label: "Concept map",
        summary: "Understand the answer as a concept map with high-level branches before diving into supporting detail.",
        layoutLabel: "Tree first",
        preferredLayout: "horizontal",
      };
  }
}

export function detectMindmapMapType(payload: MindmapPayload | null): MindmapMapType {
  if (!payload) {
    return "structure";
  }
  const direct = normalizeMindmapMapType(payload.map_type);
  if (direct === "context_mindmap" || String(payload.kind || "").trim().toLowerCase() === "context_mindmap") {
    return "context_mindmap";
  }
  if (direct === "work_graph" || String(payload.kind || "").trim().toLowerCase() === "work_graph") {
    return "work_graph";
  }
  return direct;
}

export function collectAvailableMindmapTypes(payload: MindmapPayload | null): MindmapMapType[] {
  const types = new Set<MindmapMapType>();
  if (!payload) {
    return [];
  }
  const explicitTypes = Array.isArray(payload.available_map_types)
    ? payload.available_map_types
    : [];
  explicitTypes.forEach((entry) => types.add(normalizeMindmapMapType(entry)));
  types.add(normalizeMindmapMapType(payload.map_type));
  const variants = payload.variants;
  if (variants && typeof variants === "object") {
    for (const key of Object.keys(variants)) {
      types.add(normalizeMindmapMapType(key));
    }
  }
  return MAP_TYPE_ORDER.filter((type) => types.has(type));
}

function readGraphCount(payload: MindmapPayload | null, key: "source_count" | "action_count"): number | null {
  const graph = payload?.graph;
  if (!graph || typeof graph !== "object") {
    return null;
  }
  const value = Number((graph as Record<string, unknown>)[key]);
  return Number.isFinite(value) && value >= 0 ? Math.floor(value) : null;
}

export function buildMindmapArtifactSummary(payload: MindmapPayload | null): MindmapArtifactSummary | null {
  if (!payload) {
    return null;
  }
  const activeMapType = detectMindmapMapType(payload);
  const presentation = describeMindmapMapType(activeMapType);
  return {
    title: String(payload.title || "Knowledge map"),
    activeMapType,
    presentation: {
      ...presentation,
      summary: String(payload.artifact_summary || payload.subtitle || presentation.summary),
    },
    availableMapTypes: collectAvailableMindmapTypes(payload),
    nodeCount: Array.isArray(payload.nodes) ? payload.nodes.length : 0,
    sourceCount: readGraphCount(payload, "source_count"),
    actionCount: readGraphCount(payload, "action_count"),
  };
}
