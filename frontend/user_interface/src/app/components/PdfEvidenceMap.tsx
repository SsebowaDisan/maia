import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Handle,
  Panel,
  Position,
  ReactFlow,
  type ReactFlowInstance,
  type Edge,
  type Node,
  type NodeMouseHandler,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { ChevronsDownUp, ChevronsUpDown, LocateFixed, MoreHorizontal, RotateCcw, WandSparkles } from "lucide-react";
import { pdfjs } from "react-pdf";
import type { CitationFocus } from "../types";
import type { EvidenceCard } from "../utils/infoInsights";
import {
  evidenceRefFromId,
  loadPdfOutline,
  parseClaimTraces,
  truncate,
  type ClaimTrace,
  type OutlineEntry,
} from "./pdfEvidenceMap/helpers";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

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

type PdfEvidenceMapProps = {
  fileUrl: string;
  conversationId?: string;
  fileId?: string;
  sourceName: string;
  citationFocus: CitationFocus;
  assistantHtml?: string;
  evidenceCards: EvidenceCard[];
  onNavigateCitation: (citation: CitationFocus) => void;
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
  "#0ea5e9",
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

function buildGraph(params: {
  sourceName: string;
  citationFocus: CitationFocus;
  fileId?: string;
  outlineRows: OutlineEntry[];
  claimTraces: ClaimTrace[];
  evidenceRows: EvidenceRow[];
  layoutMode: LayoutMode;
  collapsedNodeIds: Set<string>;
  positionOverrides: PositionMap;
  onToggleCollapse: (nodeId: string) => void;
}): {
  nodes: Array<Node<GraphNodeData>>;
  edges: Edge[];
  branchCount: number;
  collapsibleNodeIds: string[];
  sectionCount: number;
  tracedClaimCount: number;
  tracedEvidenceCount: number;
} {
  const {
    sourceName,
    citationFocus,
    fileId,
    outlineRows,
    claimTraces,
    evidenceRows,
    layoutMode,
    collapsedNodeIds,
    positionOverrides,
    onToggleCollapse,
  } = params;

  const evidenceByRef = new Map<number, EvidenceRow>();
  for (const row of evidenceRows) {
    if (typeof row.ref === "number" && Number.isFinite(row.ref) && !evidenceByRef.has(row.ref)) {
      evidenceByRef.set(row.ref, row);
    }
  }

  const evidenceById = new Map<string, EvidenceRow>();
  for (const row of evidenceRows) {
    const normalizedId = normalizeEvidenceId(row.id);
    if (normalizedId && !evidenceById.has(normalizedId)) {
      evidenceById.set(normalizedId, row);
    }
  }

  const uniqueEvidenceRows = evidenceRows.filter((row, index, rows) => rows.findIndex((candidate) => candidate.id === row.id) === index);

  let normalizedOutline = outlineRows
    .slice(0, 40)
    .map((row) => ({
      ...row,
      depth: Math.max(0, Math.min(4, Number(row.depth || 0))),
    }));

  if (!normalizedOutline.length) {
    const pagePool = new Set<number>();
    for (const row of uniqueEvidenceRows) {
      const pageNumber = toPageNumber(row.page);
      if (pageNumber) {
        pagePool.add(pageNumber);
      }
    }
    const citationPage = toPageNumber(citationFocus.page);
    if (citationPage) {
      pagePool.add(citationPage);
    }
    const fallbackPages = Array.from(pagePool).sort((a, b) => a - b).slice(0, 16);
    normalizedOutline = fallbackPages.map((page, index) => ({
      id: `pseudo-page-${index + 1}`,
      title: `Page ${page}`,
      page: String(page),
      depth: 0,
    }));
  }

  const rootBranches: MindmapTreeNode[] = [];
  const sectionNodeById = new Map<string, MindmapTreeNode>();
  const sectionParentById = new Map<string, string | null>();
  const sectionOrder: Array<{ id: string; order: number; pageNumber: number | null }> = [];
  const sectionClaimCount = new Map<string, number>();
  const sectionEvidenceCount = new Map<string, number>();
  const usedSections = new Set<string>();

  const outlineTopicColor = branchColorAt(0);
  let outlineRoot: MindmapTreeNode | null = null;
  if (normalizedOutline.length) {
    outlineRoot = {
      id: "topic-outline",
      data: {
        kind: "topic",
        title: "PDF layout",
        subtitle: `${normalizedOutline.length} sections`,
        branchColor: outlineTopicColor,
      },
      children: [],
    };

    type OutlineStackRow = { depth: number; node: MindmapTreeNode; sectionId: string | null };
    const stack: OutlineStackRow[] = [{ depth: -1, node: outlineRoot, sectionId: null }];
    let topLevelBranchIndex = -1;

    normalizedOutline.forEach((row, orderIndex) => {
      const depth = Math.max(0, Math.min(4, Number(row.depth || 0)));
      while (stack.length && stack[stack.length - 1].depth >= depth) {
        stack.pop();
      }
      const parent = stack[stack.length - 1] || { depth: -1, node: outlineRoot, sectionId: null };
      if (depth === 0) {
        topLevelBranchIndex += 1;
      }
      const branchColor = depth === 0 ? branchColorAt(topLevelBranchIndex) : parent.node.data.branchColor;
      const sectionId = `section-${row.id}`;
      const sectionNode: MindmapTreeNode = {
        id: sectionId,
        data: {
          kind: "section",
          title: truncate(row.title, 72),
          subtitle: row.page ? `p. ${row.page}` : "section",
          page: row.page,
          active: Boolean(row.page && citationFocus.page && String(row.page) === String(citationFocus.page)),
          branchColor,
          citation: toCitationFromPage({
            page: row.page,
            title: row.title,
            fileId,
            sourceName,
            citationFocus,
          }),
        },
        children: [],
      };
      parent.node.children.push(sectionNode);
      sectionNodeById.set(sectionId, sectionNode);
      sectionParentById.set(sectionId, parent.sectionId);
      sectionOrder.push({
        id: sectionId,
        order: orderIndex,
        pageNumber: toPageNumber(row.page),
      });
      stack.push({
        depth,
        node: sectionNode,
        sectionId,
      });
    });

    if (outlineRoot.children.length) {
      rootBranches.push(outlineRoot);
    }
  }

  const orderedSectionsWithPages = sectionOrder
    .filter((entry) => Number.isFinite(entry.pageNumber))
    .sort((left, right) => (left.pageNumber || 0) - (right.pageNumber || 0) || left.order - right.order);

  const findBestSectionIdForPage = (pageNumber: number | null): string | null => {
    if (!sectionOrder.length) {
      return null;
    }
    const targetPage = pageNumber || toPageNumber(citationFocus.page);
    if (!targetPage) {
      return sectionOrder[0]?.id || null;
    }
    if (!orderedSectionsWithPages.length) {
      return sectionOrder[0]?.id || null;
    }
    const previous = [...orderedSectionsWithPages].reverse().find((entry) => (entry.pageNumber || 0) <= targetPage);
    if (previous) {
      return previous.id;
    }
    const nearest = orderedSectionsWithPages.reduce((best, entry) => {
      if (!best) {
        return entry;
      }
      const bestDelta = Math.abs((best.pageNumber || 0) - targetPage);
      const entryDelta = Math.abs((entry.pageNumber || 0) - targetPage);
      return entryDelta < bestDelta ? entry : best;
    }, orderedSectionsWithPages[0]);
    return nearest?.id || sectionOrder[0]?.id || null;
  };

  const addUsageToSectionTree = (sectionId: string | null, claimIncrement: number, evidenceIncrement: number) => {
    let cursor = sectionId;
    while (cursor) {
      usedSections.add(cursor);
      sectionClaimCount.set(cursor, (sectionClaimCount.get(cursor) || 0) + claimIncrement);
      sectionEvidenceCount.set(cursor, (sectionEvidenceCount.get(cursor) || 0) + evidenceIncrement);
      cursor = sectionParentById.get(cursor) || null;
    }
  };

  const fallbackRef = evidenceRefFromId(citationFocus.evidenceId || "");
  const fallbackClaimText = String(citationFocus.claimText || citationFocus.extract || "").trim();
  const normalizedClaims = claimTraces.length
    ? claimTraces.slice(0, 14)
    : fallbackClaimText
      ? [{ id: "claim-fallback", text: fallbackClaimText, evidenceRefs: fallbackRef ? [fallbackRef] : [] }]
      : [];

  const orphanClaimNodes: MindmapTreeNode[] = [];
  let tracedClaimCount = 0;
  let tracedEvidenceCount = 0;

  normalizedClaims.forEach((claim, claimIndex) => {
    const evidenceRefs = Array.from(new Set(claim.evidenceRefs || []))
      .filter((ref) => Number.isFinite(ref))
      .slice(0, 6);
    const claimEvidenceRows: EvidenceRow[] = [];
    const seenEvidenceIds = new Set<string>();

    evidenceRefs.forEach((ref) => {
      const match = evidenceByRef.get(ref);
      if (!match) {
        return;
      }
      if (seenEvidenceIds.has(match.id)) {
        return;
      }
      seenEvidenceIds.add(match.id);
      claimEvidenceRows.push(match);
    });

    if (!claimEvidenceRows.length) {
      const focusEvidence = evidenceById.get(normalizeEvidenceId(citationFocus.evidenceId));
      if (focusEvidence && !seenEvidenceIds.has(focusEvidence.id)) {
        seenEvidenceIds.add(focusEvidence.id);
        claimEvidenceRows.push(focusEvidence);
      }
    }
    if (!claimEvidenceRows.length && uniqueEvidenceRows.length) {
      const citationPage = toPageNumber(citationFocus.page);
      const samePageEvidence = citationPage
        ? uniqueEvidenceRows.find((row) => toPageNumber(row.page) === citationPage)
        : null;
      const fallbackEvidence = samePageEvidence || uniqueEvidenceRows[0];
      if (fallbackEvidence && !seenEvidenceIds.has(fallbackEvidence.id)) {
        claimEvidenceRows.push(fallbackEvidence);
      }
    }

    const pageNumbers = claimEvidenceRows
      .map((row) => toPageNumber(row.page))
      .filter((value): value is number => Number.isFinite(value) && value > 0);
    const primaryPage = pageNumbers.length ? pageNumbers[0] : toPageNumber(citationFocus.page);
    const targetSectionId = findBestSectionIdForPage(primaryPage);
    const targetSectionNode = targetSectionId ? sectionNodeById.get(targetSectionId) || null : null;
    const claimColor = targetSectionNode?.data.branchColor || branchColorAt(claimIndex + 1);

    const claimEvidenceNodes: MindmapTreeNode[] = claimEvidenceRows.slice(0, 6).map((row, rowIndex) => ({
      id: `evidence-${claim.id}-${row.id}-${rowIndex}`,
      data: {
        kind: "evidence",
        title: row.ref
          ? `[${row.ref}] ${truncate(row.title || row.source || "Evidence", 68)}`
          : truncate(row.title || row.source || "Evidence", 68),
        subtitle: row.page ? `p. ${row.page}` : "citation evidence",
        page: row.page,
        evidenceId: normalizeEvidenceId(row.id),
        active: isEvidenceActive(row, citationFocus),
        branchColor: claimColor,
        citation: toCitationFromEvidence({
          row,
          fileId,
          sourceName,
          citationFocus,
          claimText: claim.text,
        }),
      },
      children: [],
    }));

    const claimSubtitleParts: string[] = [];
    if (evidenceRefs.length) {
      claimSubtitleParts.push(evidenceRefs.slice(0, 4).map((ref) => `[${ref}]`).join(" "));
    }
    if (primaryPage) {
      claimSubtitleParts.push(`p. ${primaryPage}`);
    }
    const claimNode: MindmapTreeNode = {
      id: `claim-${claim.id}-${claimIndex + 1}`,
      data: {
        kind: "claim",
        title: truncate(claim.text, 92),
        subtitle: claimSubtitleParts.join(" · ") || "answer claim",
        active: claimEvidenceNodes.some((node) => Boolean(node.data.active)),
        evidenceRefIds: evidenceRefs,
        branchColor: claimColor,
        citation:
          claimEvidenceNodes[0]?.data.citation ||
          (primaryPage
            ? toCitationFromPage({
                page: String(primaryPage),
                title: claim.text,
                fileId,
                sourceName,
                citationFocus,
                claimText: claim.text,
              })
            : undefined),
      },
      children: claimEvidenceNodes,
    };

    if (targetSectionNode) {
      targetSectionNode.children.push(claimNode);
      tracedClaimCount += 1;
      tracedEvidenceCount += claimEvidenceNodes.length;
      addUsageToSectionTree(targetSectionId, 1, claimEvidenceNodes.length);
      return;
    }

    orphanClaimNodes.push(claimNode);
  });

  if (orphanClaimNodes.length) {
    rootBranches.push({
      id: "topic-answer-traces",
      data: {
        kind: "topic",
        title: "Answer evidence traces",
        subtitle: `${orphanClaimNodes.length} claims`,
        branchColor: branchColorAt(Math.max(1, rootBranches.length)),
        usageClaimCount: orphanClaimNodes.length,
      },
      children: orphanClaimNodes,
    });
  }

  sectionOrder.forEach((entry) => {
    const sectionNode = sectionNodeById.get(entry.id);
    if (!sectionNode) {
      return;
    }
    const claims = sectionClaimCount.get(entry.id) || 0;
    const evidences = sectionEvidenceCount.get(entry.id) || 0;
    const subtitleParts: string[] = [];
    if (sectionNode.data.page) {
      subtitleParts.push(`p. ${sectionNode.data.page}`);
    }
    if (claims > 0) {
      subtitleParts.push(`${claims} claim${claims > 1 ? "s" : ""}`);
    }
    if (evidences > 0) {
      subtitleParts.push(`${evidences} cite${evidences > 1 ? "s" : ""}`);
    }
    sectionNode.data.subtitle = subtitleParts.join(" · ") || "section";
    sectionNode.data.usageClaimCount = claims || undefined;
    sectionNode.data.usageEvidenceCount = evidences || undefined;
    sectionNode.data.active =
      usedSections.has(entry.id) ||
      Boolean(sectionNode.data.page && citationFocus.page && String(sectionNode.data.page) === String(citationFocus.page));
  });

  const totalSectionCount = sectionOrder.length;
  if (outlineRoot) {
    outlineRoot.data.subtitle = `${totalSectionCount} sections · ${tracedClaimCount} traced claims`;
    outlineRoot.data.usageClaimCount = tracedClaimCount || undefined;
    outlineRoot.data.usageEvidenceCount = tracedEvidenceCount || undefined;
    outlineRoot.data.active = tracedClaimCount > 0;
  }

  if (!rootBranches.length) {
    const color = branchColorAt(0);
    rootBranches.push({
      id: "topic-fallback",
      data: {
        kind: "placeholder",
        title: "No PDF layout available yet",
        subtitle: "Upload and cite a document to build a structure map",
        branchColor: color,
      },
      children: [],
    });
  }

  const treeRoot: MindmapTreeNode = {
    id: "document-root",
    data: {
      kind: "root",
      title: truncate(sourceName || "Document map", 54),
      subtitle:
        totalSectionCount > 0
          ? `${totalSectionCount} sections · ${tracedClaimCount} claims traced`
          : "Document map",
      branchColor: "#1d1d1f",
      usageClaimCount: tracedClaimCount || undefined,
      usageEvidenceCount: tracedEvidenceCount || undefined,
    },
    children: rootBranches,
  };

  const sideById = new Map<string, BranchSide>();
  sideById.set(treeRoot.id, "right");

  const assignSides = (node: MindmapTreeNode, side: BranchSide) => {
    sideById.set(node.id, side);
    node.children.forEach((child) => assignSides(child, side));
  };

  treeRoot.children.forEach((child, index) => {
    assignSides(child, sideForRootBranch(layoutMode, index));
  });

  const visibleChildren = (node: MindmapTreeNode): MindmapTreeNode[] => {
    if (collapsedNodeIds.has(node.id)) {
      return [];
    }
    return node.children;
  };

  const layoutById = new Map<string, { x: number; y: number }>();
  const topPadding = 24;
  const depthGap = 212;
  const leafGap = 74;
  const rootX = layoutMode === "left" ? 48 : layoutMode === "right" ? 892 : 472;
  let leafCursor = topPadding;

  const assignLayout = (node: MindmapTreeNode, depth: number): number => {
    const nodeSide = sideById.get(node.id) || "right";
    const x = node.id === treeRoot.id
      ? rootX
      : rootX + depth * depthGap * (nodeSide === "right" ? 1 : -1);

    const children = visibleChildren(node);
    if (!children.length) {
      const y = leafCursor;
      leafCursor += leafGap;
      layoutById.set(node.id, { x, y });
      return y;
    }

    const childYs = children.map((child) => assignLayout(child, depth + 1));
    const y = (Math.min(...childYs) + Math.max(...childYs)) / 2;
    layoutById.set(node.id, { x, y });
    return y;
  };

  assignLayout(treeRoot, 0);

  const nodes: Array<Node<GraphNodeData>> = [];
  const edges: Edge[] = [];
  const collapsibleNodeIds: string[] = [];

  const collectCollapsibleNodeIds = (node: MindmapTreeNode) => {
    if (node.id !== treeRoot.id && node.children.length > 0) {
      collapsibleNodeIds.push(node.id);
    }
    node.children.forEach((child) => collectCollapsibleNodeIds(child));
  };
  collectCollapsibleNodeIds(treeRoot);

  const pushNode = (node: MindmapTreeNode) => {
    const position = positionOverrides[node.id] || layoutById.get(node.id) || { x: 0, y: 0 };
    const side = sideById.get(node.id) || "right";
    const collapsed = collapsedNodeIds.has(node.id);
    const children = visibleChildren(node);
    const hiddenChildrenCount = collapsed ? node.children.length : 0;

    nodes.push({
      id: node.id,
      type: "graphNode",
      position,
      data: {
        ...node.data,
        nodeId: node.id,
        side,
        collapsible: node.id !== treeRoot.id && node.children.length > 0,
        collapsed,
        hiddenChildrenCount,
        onToggleCollapse,
      },
    });

    children.forEach((child) => {
      const childSide = sideById.get(child.id) || "right";
      const childIsTraceNode =
        child.data.kind === "claim" ||
        child.data.kind === "evidence" ||
        Boolean(child.data.active) ||
        Number(child.data.usageClaimCount || 0) > 0;
      edges.push({
        id: `edge-${node.id}-${child.id}`,
        source: node.id,
        sourceHandle: childSide === "right" ? "source-right" : "source-left",
        target: child.id,
        targetHandle: childSide === "right" ? "target-left" : "target-right",
        type: "smoothstep",
        pathOptions: { borderRadius: 34, offset: 12 },
        style: {
          stroke: child.data.branchColor,
          strokeWidth: child.data.kind === "evidence" ? (childIsTraceNode ? 1.9 : 1.4) : (childIsTraceNode ? 2.2 : 1.5),
          opacity: childIsTraceNode ? 0.84 : 0.3,
          strokeLinecap: "round",
        },
      });
      pushNode(child);
    });
  };

  pushNode(treeRoot);

  return {
    nodes,
    edges,
    branchCount: rootBranches.length,
    collapsibleNodeIds,
    sectionCount: totalSectionCount,
    tracedClaimCount,
    tracedEvidenceCount,
  };
}

function GraphNode({ data }: NodeProps<Node<GraphNodeData>>) {
  const isRoot = data.kind === "root";
  const isSection = data.kind === "section";
  const isClaim = data.kind === "claim";
  const isEvidence = data.kind === "evidence";
  const isPlaceholder = data.kind === "placeholder";
  const usageClaimCount = Number(data.usageClaimCount || 0);
  const usageEvidenceCount = Number(data.usageEvidenceCount || 0);
  const hasUsageMeta = usageClaimCount > 0 || usageEvidenceCount > 0;
  const isUsed = Boolean(data.active) || hasUsageMeta;
  const borderColor = isRoot
    ? "rgba(17, 17, 19, 1)"
    : isUsed
      ? "rgba(17, 17, 19, 0.26)"
      : isSection
        ? "rgba(0, 0, 0, 0.08)"
        : "transparent";
  const dotColor = data.branchColor || "#7a7a86";
  const bgColor = isRoot
    ? "#111113"
    : isSection
      ? "rgba(255, 255, 255, 0.9)"
      : isUsed
        ? "rgba(255, 246, 202, 0.52)"
      : isClaim
        ? "rgba(255, 255, 255, 0.7)"
        : "transparent";
  const textColor = isRoot ? "#ffffff" : "#1d1d1f";

  const showTargetLeft = !isRoot && data.side === "right";
  const showTargetRight = !isRoot && data.side === "left";
  const showSourceLeft = isRoot || data.side === "left";
  const showSourceRight = isRoot || data.side === "right";
  const collapseLabel = data.collapsed ? `+${Math.max(1, data.hiddenChildrenCount)}` : "-";

  return (
    <div
      className={`${isRoot ? "min-w-[188px] max-w-[320px] rounded-2xl border px-3 py-2.5 shadow-[0_12px_32px_rgba(0,0,0,0.24)]" : isSection ? "min-w-[180px] max-w-[360px] rounded-xl border px-2 py-1.5 shadow-[0_1px_6px_rgba(0,0,0,0.05)]" : "min-w-[150px] max-w-[350px] rounded-lg border px-1.5 py-1"} transition-colors`}
      style={{
        borderColor,
        background: bgColor,
      }}
    >
      <Handle
        type="target"
        id="target-left"
        position={Position.Left}
        className="!h-2 !w-2 !border-0 !bg-transparent !shadow-none"
        style={{ opacity: 0, pointerEvents: "none", display: showTargetLeft ? "block" : "none" }}
      />
      <Handle
        type="target"
        id="target-right"
        position={Position.Right}
        className="!h-2 !w-2 !border-0 !bg-transparent !shadow-none"
        style={{ opacity: 0, pointerEvents: "none", display: showTargetRight ? "block" : "none" }}
      />
      <Handle
        type="source"
        id="source-left"
        position={Position.Left}
        className="!h-2 !w-2 !border-0 !bg-transparent !shadow-none"
        style={{ opacity: 0, pointerEvents: "none", display: showSourceLeft ? "block" : "none" }}
      />
      <Handle
        type="source"
        id="source-right"
        position={Position.Right}
        className="!h-2 !w-2 !border-0 !bg-transparent !shadow-none"
        style={{ opacity: 0, pointerEvents: "none", display: showSourceRight ? "block" : "none" }}
      />

      <div className="flex items-start gap-2" style={{ color: textColor }}>
        {!isRoot ? (
          <span
            className="mt-[6px] h-2.5 w-2.5 shrink-0 rounded-full border border-white/90 shadow-[0_0_0_1px_rgba(0,0,0,0.08)]"
            style={{ background: dotColor }}
          />
        ) : null}
        <div className="min-w-0 flex-1">
          <p className={`${isRoot ? "text-[12px] font-semibold tracking-[0.01em]" : isSection ? "text-[13px] font-semibold" : isEvidence ? "text-[12px] font-medium" : "text-[12.5px] font-medium"} truncate`}>
            {data.title}
          </p>
          {data.subtitle ? (
            <p className="mt-0.5 text-[11px] leading-tight" style={{ color: isRoot ? "rgba(255,255,255,0.72)" : "#6e6e73" }}>
              {data.subtitle}
            </p>
          ) : null}
          {hasUsageMeta && !isRoot ? (
            <p className="mt-1 text-[10px] text-[#6e6e73]">
              {usageClaimCount > 0 ? `${usageClaimCount} claim${usageClaimCount > 1 ? "s" : ""}` : "0 claims"}
              {" | "}
              {usageEvidenceCount} cite{usageEvidenceCount > 1 ? "s" : ""}
            </p>
          ) : null}
        </div>

        {data.collapsible ? (
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              data.onToggleCollapse?.(data.nodeId);
            }}
            className={`${isRoot ? "border-white/25 bg-white/10 text-white hover:bg-white/20" : "border-black/[0.14] bg-white/85 text-[#3a3a3c] hover:bg-white"} mt-[1px] inline-flex h-5 min-w-[20px] items-center justify-center rounded-full border px-1.5 text-[10px] font-semibold`}
            title={data.collapsed ? "Expand branch" : "Collapse branch"}
          >
            {collapseLabel}
          </button>
        ) : null}
      </div>

      {!isRoot ? (
        <div
          className="mt-1 h-[1.5px] rounded-full"
          style={{
            background: dotColor,
            opacity: isEvidence ? 0.54 : isUsed ? 0.58 : 0.22,
          }}
        />
      ) : null}

      {isPlaceholder ? <div className="mt-1.5 text-[10px] text-[#6e6e73]">Run a cited answer to populate this branch.</div> : null}
    </div>
  );
}

const nodeTypes = { graphNode: GraphNode };

export function PdfEvidenceMap({
  fileUrl,
  conversationId,
  fileId,
  sourceName,
  citationFocus,
  assistantHtml = "",
  evidenceCards,
  onNavigateCitation,
}: PdfEvidenceMapProps) {
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance<Node<GraphNodeData>, Edge> | null>(null);
  const [outlineRows, setOutlineRows] = useState<OutlineEntry[]>([]);
  const [outlineLoading, setOutlineLoading] = useState(false);
  const [layoutMode, setLayoutMode] = useState<LayoutMode>("left");
  const [collapsedNodeIds, setCollapsedNodeIds] = useState<Set<string>>(new Set());
  const [nodePositionsByLayout, setNodePositionsByLayout] = useState<Record<LayoutMode, PositionMap>>(
    createEmptyPositionState,
  );
  const canvasStorageKey = useMemo(
    () => buildCanvasStorageKey({ conversationId, fileId, sourceName }),
    [conversationId, fileId, sourceName],
  );
  const openedMapKey = useMemo(() => `${canvasStorageKey}:${fileUrl}`, [canvasStorageKey, fileUrl]);

  useEffect(() => {
    let cancelled = false;
    const loadOutline = async () => {
      setOutlineLoading(true);
      try {
        const rows = await loadPdfOutline(fileUrl);
        if (!cancelled) {
          setOutlineRows(rows);
        }
      } catch {
        if (!cancelled) {
          setOutlineRows([]);
        }
      } finally {
        if (!cancelled) {
          setOutlineLoading(false);
        }
      }
    };
    void loadOutline();
    return () => {
      cancelled = true;
    };
  }, [fileUrl]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const stored = parsePersistedCanvasState(window.localStorage.getItem(canvasStorageKey));
    if (!stored) {
      setLayoutMode("left");
      setCollapsedNodeIds(new Set());
      setNodePositionsByLayout(createEmptyPositionState());
      return;
    }
    setLayoutMode("left");
    setCollapsedNodeIds(new Set(stored.collapsedNodeIds));
    setNodePositionsByLayout(stored.nodePositionsByLayout);
  }, [canvasStorageKey]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const payload: PersistedCanvasState = {
      layoutMode,
      collapsedNodeIds: Array.from(collapsedNodeIds),
      nodePositionsByLayout,
    };
    window.localStorage.setItem(canvasStorageKey, JSON.stringify(payload));
  }, [canvasStorageKey, collapsedNodeIds, layoutMode, nodePositionsByLayout]);

  useEffect(() => {
    setHasUserViewportInteraction(false);
    setAutoFitAppliedForKey("");
    setShowMapMenu(false);
  }, [openedMapKey]);

  const handleToggleCollapse = useCallback((nodeId: string) => {
    setCollapsedNodeIds((previous) => {
      const next = new Set(previous);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  }, []);

  const handleNodeDragStop = useCallback(
    (_event: unknown, node: Node<GraphNodeData>) => {
      const x = Number(node.position.x);
      const y = Number(node.position.y);
      if (!Number.isFinite(x) || !Number.isFinite(y)) {
        setDraggingNodeId(null);
        return;
      }
      setPinnedNodeIds((previous) => {
        if (previous.has(node.id)) {
          return previous;
        }
        const next = new Set(previous);
        next.add(node.id);
        return next;
      });
      setNodePositionsByLayout((previous) => {
        const next = {
          left: { ...(previous.left || {}) },
          center: { ...(previous.center || {}) },
          right: { ...(previous.right || {}) },
        };
        next[layoutMode][node.id] = {
          x: Number(x.toFixed(2)),
          y: Number(y.toFixed(2)),
        };
        return next;
      });
      setDraggingNodeId(null);
    },
    [layoutMode],
  );

  const handleNodeDragStart = useCallback((_event: unknown, node: Node<GraphNodeData>) => {
    setHasUserViewportInteraction(true);
    setDraggingNodeId(node.id);
  }, []);

  const handleViewportMoveStart = useCallback((event: unknown) => {
    if (!isUserInteractionEvent(event)) {
      return;
    }
    setHasUserViewportInteraction(true);
  }, []);

  const handleResetCanvasLayout = useCallback(() => {
    setCollapsedNodeIds(new Set());
    setNodePositionsByLayout(createEmptyPositionState());
    setPinnedNodeIds(new Set());
  }, []);

  const handleAutoTidyLayout = useCallback(() => {
    setNodePositionsByLayout((previous) => {
      const next = {
        left: { ...(previous.left || {}) },
        center: { ...(previous.center || {}) },
        right: { ...(previous.right || {}) },
      };
      next[layoutMode] = {};
      return next;
    });
    setPinnedNodeIds(new Set());
  }, [layoutMode]);

  const handleFitView = useCallback(() => {
    flowInstance?.fitView({
      padding: 0.22,
      maxZoom: 1.05,
      minZoom: 0.2,
      duration: 260,
    });
  }, [flowInstance]);

  const claimTraces = useMemo(() => parseClaimTraces(assistantHtml), [assistantHtml]);
  const evidenceRows = useMemo(
    () =>
      evidenceCards
        .map((row) => ({ ...row, ref: evidenceRefFromId(row.id) }))
        .filter((row) => {
          if (!fileId || !row.fileId) {
            return true;
          }
          return row.fileId === fileId;
        })
        .slice(0, 12),
    [evidenceCards, fileId],
  );

  const graph = useMemo(
    () =>
      buildGraph({
        sourceName,
        citationFocus,
        fileId,
        outlineRows,
        claimTraces,
        evidenceRows,
        layoutMode,
        collapsedNodeIds,
        positionOverrides: nodePositionsByLayout[layoutMode] || {},
        onToggleCollapse: handleToggleCollapse,
      }),
    [
      citationFocus,
      claimTraces,
      collapsedNodeIds,
      evidenceRows,
      fileId,
      handleToggleCollapse,
      layoutMode,
      nodePositionsByLayout,
      outlineRows,
      sourceName,
    ],
  );

  const handleExpandAll = useCallback(() => {
    setCollapsedNodeIds(new Set());
  }, []);

  const handleCollapseAll = useCallback(() => {
    setCollapsedNodeIds(new Set(graph.collapsibleNodeIds));
  }, [graph.collapsibleNodeIds]);
  const allCollapsibleNodesCollapsed = useMemo(() => {
    if (!graph.collapsibleNodeIds.length) {
      return false;
    }
    return graph.collapsibleNodeIds.every((nodeId) => collapsedNodeIds.has(nodeId));
  }, [collapsedNodeIds, graph.collapsibleNodeIds]);

  const [displayNodes, setDisplayNodes] = useState<Array<Node<GraphNodeData>>>(graph.nodes);
  const [displayEdges, setDisplayEdges] = useState<Edge[]>(graph.edges);
  const [isAnimatingLayout, setIsAnimatingLayout] = useState(false);
  const [draggingNodeId, setDraggingNodeId] = useState<string | null>(null);
  const [pinnedNodeIds, setPinnedNodeIds] = useState<Set<string>>(new Set());
  const [hasUserViewportInteraction, setHasUserViewportInteraction] = useState(false);
  const [autoFitAppliedForKey, setAutoFitAppliedForKey] = useState("");
  const [showMapMenu, setShowMapMenu] = useState(false);
  const displayNodesRef = useRef<Array<Node<GraphNodeData>>>(displayNodes);

  useEffect(() => {
    displayNodesRef.current = displayNodes;
  }, [displayNodes]);

  useEffect(() => {
    const previousNodes = displayNodesRef.current;
    const shouldAnimate =
      typeof window !== "undefined" &&
      previousNodes.length > 0 &&
      graph.nodes.length > 0 &&
      graph.nodes.length <= 120 &&
      !draggingNodeId;

    setDisplayEdges(graph.edges);
    if (!shouldAnimate) {
      setDisplayNodes(graph.nodes);
      setIsAnimatingLayout(false);
      return;
    }

    const prevById = new Map(previousNodes.map((node) => [node.id, node]));
    const durationMs = 220;
    let frame = 0;
    setIsAnimatingLayout(true);
    const startTime = performance.now();

    const tick = (now: number) => {
      const progress = Math.min(1, (now - startTime) / durationMs);
      const eased = progress < 0.5 ? 2 * progress * progress : 1 - Math.pow(-2 * progress + 2, 2) / 2;
      const nextNodes = graph.nodes.map((target) => {
        const previous = prevById.get(target.id);
        if (!previous) {
          return target;
        }
        const pinned = pinnedNodeIds.has(target.id);
        if (pinned) {
          return target;
        }
        return {
          ...target,
          position: {
            x: previous.position.x + (target.position.x - previous.position.x) * eased,
            y: previous.position.y + (target.position.y - previous.position.y) * eased,
          },
        };
      });
      setDisplayNodes(nextNodes);
      if (progress < 1) {
        frame = window.requestAnimationFrame(tick);
        return;
      }
      setIsAnimatingLayout(false);
    };

    frame = window.requestAnimationFrame(tick);
    return () => {
      if (frame) {
        window.cancelAnimationFrame(frame);
      }
      setIsAnimatingLayout(false);
    };
  }, [draggingNodeId, graph.edges, graph.nodes, pinnedNodeIds]);

  useEffect(() => {
    if (!flowInstance) {
      return;
    }
    if (!displayNodes.length) {
      return;
    }
    if (hasUserViewportInteraction) {
      return;
    }
    if (autoFitAppliedForKey === openedMapKey) {
      return;
    }
    let frame = 0;
    frame = window.requestAnimationFrame(() => {
      flowInstance.fitView({
        padding: 0.22,
        maxZoom: 1.05,
        minZoom: 0.2,
        duration: 260,
      });
    });
    setAutoFitAppliedForKey(openedMapKey);
    return () => {
      if (frame) {
        window.cancelAnimationFrame(frame);
      }
    };
  }, [autoFitAppliedForKey, displayNodes.length, flowInstance, hasUserViewportInteraction, openedMapKey]);

  const onNodeClick: NodeMouseHandler<Node<GraphNodeData>> = (_event, node) => {
    const data = node.data;
    if (data.citation) {
      onNavigateCitation(data.citation);
      return;
    }

    if (data.kind === "claim" && data.evidenceRefIds?.length) {
      const match = evidenceRows.find((row) => row.ref === data.evidenceRefIds?.[0]);
      if (match) {
        onNavigateCitation(
          toCitationFromEvidence({
            row: match,
            fileId,
            sourceName,
            citationFocus,
          }),
        );
        return;
      }
    }

    if (data.page) {
      onNavigateCitation(
        toCitationFromPage({
          page: data.page,
          title: data.title,
          fileId,
          sourceName,
          citationFocus,
        }),
      );
    }
  };

  const mapStatusLabel = outlineLoading
    ? "Mapping document..."
    : isAnimatingLayout
      ? "Arranging map..."
      : graph.sectionCount > 0
        ? `${graph.sectionCount} sections, ${graph.tracedClaimCount} claims traced, ${graph.tracedEvidenceCount} citations`
        : "Mind map";

  return (
    <div className="mb-3 overflow-hidden rounded-2xl border border-black/[0.08] bg-white">
      <div className="h-[380px] w-full bg-[#fbfbfd]">
        <ReactFlow
          nodes={displayNodes}
          edges={displayEdges}
          nodeTypes={nodeTypes}
          onInit={(instance) => setFlowInstance(instance)}
          onNodeClick={onNodeClick}
          onMoveStart={handleViewportMoveStart}
          onNodeDragStart={handleNodeDragStart}
          onNodeDragStop={handleNodeDragStop}
          fitView
          fitViewOptions={{ padding: 0.22, maxZoom: 1.05 }}
          minZoom={0.2}
          maxZoom={1.8}
          proOptions={{ hideAttribution: true }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          panOnDrag
          zoomOnScroll
          zoomOnPinch
        >
          <Panel position="top-left">
            <div className="rounded-full border border-black/[0.08] bg-white/92 px-2.5 py-1 text-[11px] text-[#5b5b62] shadow-sm backdrop-blur">
              {mapStatusLabel}
            </div>
          </Panel>

          <Panel position="top-right">
            <div className="relative">
              <div className="inline-flex items-center gap-1 rounded-full border border-black/[0.1] bg-white/94 p-1 shadow-sm backdrop-blur">
                <button
                  type="button"
                  onClick={() => {
                    if (allCollapsibleNodesCollapsed) {
                      handleExpandAll();
                    } else {
                      handleCollapseAll();
                    }
                  }}
                  disabled={!graph.collapsibleNodeIds.length}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-full text-[#3a3a3c] transition-colors hover:bg-black/[0.05] disabled:cursor-not-allowed disabled:opacity-40"
                  title={allCollapsibleNodesCollapsed ? "Expand all branches" : "Collapse all branches"}
                >
                  {allCollapsibleNodesCollapsed ? <ChevronsDownUp className="h-3.5 w-3.5" /> : <ChevronsUpDown className="h-3.5 w-3.5" />}
                </button>
                <button
                  type="button"
                  onClick={handleFitView}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-full text-[#3a3a3c] transition-colors hover:bg-black/[0.05]"
                  title="Fit map to view"
                >
                  <LocateFixed className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => setShowMapMenu((previous) => !previous)}
                  className={`inline-flex h-7 w-7 items-center justify-center rounded-full text-[#3a3a3c] transition-colors hover:bg-black/[0.05] ${showMapMenu ? "bg-black/[0.06]" : ""}`}
                  title="More map options"
                >
                  <MoreHorizontal className="h-3.5 w-3.5" />
                </button>
              </div>

              {showMapMenu ? (
                <div className="absolute right-0 mt-1.5 w-[198px] rounded-xl border border-black/[0.1] bg-white p-1.5 shadow-lg">
                  <button
                    type="button"
                    onClick={() => {
                      handleAutoTidyLayout();
                      setShowMapMenu(false);
                    }}
                    className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[12px] text-[#2d2d31] hover:bg-black/[0.04]"
                  >
                    <WandSparkles className="h-3.5 w-3.5 text-[#6e6e73]" />
                    Auto tidy branches
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      handleResetCanvasLayout();
                      setShowMapMenu(false);
                    }}
                    className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[12px] text-[#2d2d31] hover:bg-black/[0.04]"
                  >
                    <RotateCcw className="h-3.5 w-3.5 text-[#6e6e73]" />
                    Reset layout
                  </button>
                  <p className="px-2 pt-1 text-[10px] text-[#8e8e93]">Layout follows PDF structure flow.</p>
                </div>
              ) : null}
            </div>
          </Panel>
        </ReactFlow>
      </div>
    </div>
  );
}
