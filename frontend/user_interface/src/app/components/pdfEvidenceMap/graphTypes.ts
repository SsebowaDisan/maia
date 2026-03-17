import type { Node } from "@xyflow/react";
import type { CitationFocus } from "../../types";
import type { EvidenceCard } from "../../utils/infoInsights";

type LayoutMode = "left" | "center" | "right";
type BranchSide = "left" | "right";

type MindmapNodeKind = "root" | "topic" | "section" | "claim" | "evidence" | "placeholder";

type GraphNodeData = {
  nodeId: string;
  kind: MindmapNodeKind;
  title: string;
  subtitle?: string;
  page?: string;
  evidenceId?: string;
  active?: boolean;
  evidenceRefIds?: number[];
  usageClaimCount?: number;
  usageEvidenceCount?: number;
  branchColor: string;
  side: BranchSide;
  citation?: CitationFocus;
  collapsible: boolean;
  collapsed: boolean;
  hiddenChildrenCount: number;
  onToggleCollapse?: (nodeId: string) => void;
};

type EvidenceRow = EvidenceCard & { ref: number | null };

type MindmapTreeNode = {
  id: string;
  data: Omit<GraphNodeData, "nodeId" | "side" | "collapsible" | "collapsed" | "hiddenChildrenCount" | "onToggleCollapse">;
  children: MindmapTreeNode[];
};

type PositionMap = Record<string, { x: number; y: number }>;

type PersistedCanvasState = {
  layoutMode: LayoutMode;
  collapsedNodeIds: string[];
  nodePositionsByLayout: Record<LayoutMode, PositionMap>;
};

const BRANCH_COLORS = [
  "#f97316",
  "#22c55e",
  "#ef4444",
  "#8b5cf6",
  "#8b5cf6",
  "#a16207",
  "#14b8a6",
];

const CANVAS_STORAGE_PREFIX = "maia.mindmap.canvas.v1";

function branchColorAt(index: number): string {
  if (!Number.isFinite(index) || index < 0) {
    return BRANCH_COLORS[0];
  }
  return BRANCH_COLORS[index % BRANCH_COLORS.length];
}

function normalizeEvidenceId(value: string | undefined): string {
  const raw = String(value || "").trim().toLowerCase();
  if (!raw) {
    return "";
  }
  const canonical = raw.match(/evidence-\d+/i)?.[0];
  return String(canonical || raw);
}

function toPageNumber(value: unknown): number | null {
  const raw = String(value ?? "").trim();
  if (!raw) {
    return null;
  }
  const matched = raw.match(/\d+/)?.[0];
  if (!matched) {
    return null;
  }
  const parsed = Number.parseInt(matched, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return parsed;
}

function isEvidenceActive(row: EvidenceRow, citationFocus: CitationFocus): boolean {
  const activeEvidenceId = normalizeEvidenceId(citationFocus.evidenceId);
  const rowEvidenceId = normalizeEvidenceId(row.id);
  if (activeEvidenceId && rowEvidenceId && activeEvidenceId === rowEvidenceId) {
    return true;
  }
  if (citationFocus.page && row.page && String(citationFocus.page) === String(row.page)) {
    return true;
  }
  return false;
}

function toCitationFromEvidence(params: {
  row: EvidenceRow;
  fileId?: string;
  sourceName: string;
  citationFocus: CitationFocus;
  claimText?: string;
}): CitationFocus {
  const { row, fileId, sourceName, citationFocus, claimText } = params;
  return {
    fileId: row.fileId || fileId || citationFocus.fileId,
    sourceUrl: row.sourceUrl || citationFocus.sourceUrl,
    sourceType: row.sourceUrl || citationFocus.sourceUrl ? "website" : "file",
    sourceName: row.source || sourceName || citationFocus.sourceName || "Indexed source",
    page: row.page || citationFocus.page,
    extract: row.extract || citationFocus.extract || row.title || row.source || "Evidence extract unavailable.",
    claimText: claimText || citationFocus.claimText,
    evidenceId: row.id,
    highlightBoxes: row.highlightBoxes || citationFocus.highlightBoxes,
    strengthScore: row.strengthScore ?? citationFocus.strengthScore,
    strengthTier: row.strengthTier ?? citationFocus.strengthTier,
    matchQuality: row.matchQuality || citationFocus.matchQuality,
    unitId: row.unitId || citationFocus.unitId,
    charStart: row.charStart ?? citationFocus.charStart,
    charEnd: row.charEnd ?? citationFocus.charEnd,
    graphNodeIds: row.graphNodeIds || citationFocus.graphNodeIds,
    sceneRefs: row.sceneRefs || citationFocus.sceneRefs,
    eventRefs: row.eventRefs || citationFocus.eventRefs,
  };
}

function toCitationFromPage(params: {
  page?: string;
  title: string;
  fileId?: string;
  sourceName: string;
  citationFocus: CitationFocus;
  claimText?: string;
}): CitationFocus {
  const { page, title, fileId, sourceName, citationFocus, claimText } = params;
  return {
    fileId: fileId || citationFocus.fileId,
    sourceUrl: citationFocus.sourceUrl,
    sourceType: citationFocus.sourceType,
    sourceName: sourceName || citationFocus.sourceName || "Indexed source",
    page: page || citationFocus.page,
    extract: citationFocus.extract || title,
    claimText: claimText || citationFocus.claimText,
    evidenceId: citationFocus.evidenceId,
    highlightBoxes: citationFocus.highlightBoxes,
    strengthScore: citationFocus.strengthScore,
    strengthTier: citationFocus.strengthTier,
    matchQuality: citationFocus.matchQuality,
    unitId: citationFocus.unitId,
    charStart: citationFocus.charStart,
    charEnd: citationFocus.charEnd,
    graphNodeIds: citationFocus.graphNodeIds,
    sceneRefs: citationFocus.sceneRefs,
    eventRefs: citationFocus.eventRefs,
  };
}

function sideForRootBranch(layoutMode: LayoutMode, index: number): BranchSide {
  if (layoutMode === "left") {
    return "right";
  }
  if (layoutMode === "right") {
    return "left";
  }
  return index % 2 === 0 ? "right" : "left";
}

function hashString(value: string): string {
  let hash = 2166136261;
  for (let idx = 0; idx < value.length; idx += 1) {
    hash ^= value.charCodeAt(idx);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash >>> 0).toString(36);
}

function buildCanvasStorageKey(params: { conversationId?: string; fileId?: string; sourceName: string }): string {
  const conversationPart = String(params.conversationId || "global");
  const filePart = String(params.fileId || "").trim() || `source-${hashString(params.sourceName || "document")}`;
  return `${CANVAS_STORAGE_PREFIX}:${conversationPart}:${filePart}`;
}

function createEmptyPositionState(): Record<LayoutMode, PositionMap> {
  return {
    left: {},
    center: {},
    right: {},
  };
}

function parsePersistedCanvasState(raw: string | null): PersistedCanvasState | null {
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as Partial<PersistedCanvasState> | null;
    if (!parsed || typeof parsed !== "object") {
      return null;
    }
    const layoutMode =
      parsed.layoutMode === "left" || parsed.layoutMode === "center" || parsed.layoutMode === "right"
        ? parsed.layoutMode
        : "left";
    const collapsedNodeIds = Array.isArray(parsed.collapsedNodeIds)
      ? parsed.collapsedNodeIds.filter((entry): entry is string => typeof entry === "string")
      : [];
    const byLayout = createEmptyPositionState();
    const sourceByLayout = parsed.nodePositionsByLayout || {};
    for (const mode of ["left", "center", "right"] as LayoutMode[]) {
      const source = sourceByLayout[mode];
      if (!source || typeof source !== "object") {
        continue;
      }
      const next: PositionMap = {};
      for (const [nodeId, value] of Object.entries(source as Record<string, unknown>)) {
        if (!value || typeof value !== "object") {
          continue;
        }
        const point = value as Record<string, unknown>;
        const x = Number(point.x);
        const y = Number(point.y);
        if (!Number.isFinite(x) || !Number.isFinite(y)) {
          continue;
        }
        next[nodeId] = {
          x: Number(x.toFixed(2)),
          y: Number(y.toFixed(2)),
        };
      }
      byLayout[mode] = next;
    }
    return {
      layoutMode,
      collapsedNodeIds,
      nodePositionsByLayout: byLayout,
    };
  } catch {
    return null;
  }
}

function isUserInteractionEvent(event: unknown): boolean {
  if (!event || typeof event !== "object") {
    return false;
  }
  const record = event as { isTrusted?: unknown; type?: unknown };
  if (typeof record.isTrusted === "boolean") {
    return record.isTrusted;
  }
  return typeof record.type === "string";
}

export {
  branchColorAt,
  buildCanvasStorageKey,
  createEmptyPositionState,
  isEvidenceActive,
  isUserInteractionEvent,
  normalizeEvidenceId,
  parsePersistedCanvasState,
  sideForRootBranch,
  toCitationFromEvidence,
  toCitationFromPage,
  toPageNumber,
};
export type {
  BranchSide,
  EvidenceRow,
  GraphNodeData,
  LayoutMode,
  MindmapTreeNode,
  PositionMap,
  PersistedCanvasState,
};
