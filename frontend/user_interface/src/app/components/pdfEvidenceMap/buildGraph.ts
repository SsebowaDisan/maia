import type { Edge, Node } from "@xyflow/react";
import { evidenceRefFromId, truncate, type ClaimTrace, type OutlineEntry } from "./helpers";
import {
  branchColorAt,
  isEvidenceActive,
  normalizeEvidenceId,
  toCitationFromEvidence,
  toCitationFromPage,
  toPageNumber,
  type EvidenceRow,
  type GraphNodeData,
  type LayoutMode,
  type MindmapTreeNode,
  type PositionMap,
} from "./graphTypes";
import { renderGraphTree } from "./buildGraphRender";
import type { CitationFocus } from "../../types";

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

  const uniqueEvidenceRows = evidenceRows.filter(
    (row, index, rows) => rows.findIndex((candidate) => candidate.id === row.id) === index,
  );

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
    const previous = [...orderedSectionsWithPages]
      .reverse()
      .find((entry) => (entry.pageNumber || 0) <= targetPage);
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

  const renderedGraph = renderGraphTree({
    treeRoot,
    layoutMode,
    collapsedNodeIds,
    positionOverrides,
    onToggleCollapse,
  });

  return {
    nodes: renderedGraph.nodes,
    edges: renderedGraph.edges,
    branchCount: rootBranches.length,
    collapsibleNodeIds: renderedGraph.collapsibleNodeIds,
    sectionCount: totalSectionCount,
    tracedClaimCount,
    tracedEvidenceCount,
  };
}

export { buildGraph };
