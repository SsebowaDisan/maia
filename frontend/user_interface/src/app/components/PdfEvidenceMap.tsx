import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Panel,
  ReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { ChevronsDownUp, ChevronsUpDown, LocateFixed, MoreHorizontal, RotateCcw, WandSparkles } from "lucide-react";
import { pdfjs } from "react-pdf";
import type { CitationFocus } from "../types";
import type { EvidenceCard } from "../utils/infoInsights";
import { buildGraph } from "./pdfEvidenceMap/buildGraph";
import { edgeTypes } from "./pdfEvidenceMap/edgeTypes";
import { nodeTypes } from "./pdfEvidenceMap/GraphNode";
import {
  buildCanvasStorageKey,
  createEmptyPositionState,
  isUserInteractionEvent,
  parsePersistedCanvasState,
  toCitationFromEvidence,
  toCitationFromPage,
  type EvidenceRow,
  type GraphNodeData,
  type LayoutMode,
  type PositionMap,
} from "./pdfEvidenceMap/graphTypes";
import {
  evidenceRefFromId,
  loadPdfOutline,
  parseClaimTraces,
  type OutlineEntry,
} from "./pdfEvidenceMap/helpers";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

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
  const [nodePositionsByLayout, setNodePositionsByLayout] = useState<Record<LayoutMode, PositionMap>>(createEmptyPositionState);
  const [displayNodes, setDisplayNodes] = useState<Array<Node<GraphNodeData>>>([]);
  const [displayEdges, setDisplayEdges] = useState<Edge[]>([]);
  const [isAnimatingLayout, setIsAnimatingLayout] = useState(false);
  const [draggingNodeId, setDraggingNodeId] = useState<string | null>(null);
  const [pinnedNodeIds, setPinnedNodeIds] = useState<Set<string>>(new Set());
  const [hasUserViewportInteraction, setHasUserViewportInteraction] = useState(false);
  const [autoFitAppliedForKey, setAutoFitAppliedForKey] = useState("");
  const [showMapMenu, setShowMapMenu] = useState(false);
  const displayNodesRef = useRef<Array<Node<GraphNodeData>>>(displayNodes);

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
    window.localStorage.setItem(
      canvasStorageKey,
      JSON.stringify({
        layoutMode,
        collapsedNodeIds: Array.from(collapsedNodeIds),
        nodePositionsByLayout,
      }),
    );
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

  const handleNodeDragStart = useCallback((_event: unknown, node: Node<GraphNodeData>) => {
    setHasUserViewportInteraction(true);
    setDraggingNodeId(node.id);
  }, []);

  const handleNodeDragStop = useCallback((_event: unknown, node: Node<GraphNodeData>) => {
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
      next[layoutMode][node.id] = { x: Number(x.toFixed(2)), y: Number(y.toFixed(2)) };
      return next;
    });
    setDraggingNodeId(null);
  }, [layoutMode]);

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
    flowInstance?.fitView({ padding: 0.22, maxZoom: 1.05, minZoom: 0.2, duration: 260 });
  }, [flowInstance]);

  const claimTraces = useMemo(() => parseClaimTraces(assistantHtml), [assistantHtml]);
  const evidenceRows = useMemo(
    () =>
      evidenceCards
        .map((row) => ({ ...row, ref: evidenceRefFromId(row.id) }))
        .filter((row) => (!fileId || !row.fileId ? true : row.fileId === fileId))
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
        evidenceRows: evidenceRows as EvidenceRow[],
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

  const handleExpandAll = useCallback(() => setCollapsedNodeIds(new Set()), []);
  const handleCollapseAll = useCallback(() => setCollapsedNodeIds(new Set(graph.collapsibleNodeIds)), [graph.collapsibleNodeIds]);
  const allCollapsibleNodesCollapsed = useMemo(
    () => graph.collapsibleNodeIds.length > 0 && graph.collapsibleNodeIds.every((nodeId) => collapsedNodeIds.has(nodeId)),
    [collapsedNodeIds, graph.collapsibleNodeIds],
  );

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
        if (!previous || pinnedNodeIds.has(target.id)) {
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
    if (!flowInstance || !displayNodes.length || hasUserViewportInteraction || autoFitAppliedForKey === openedMapKey) {
      return;
    }
    let frame = 0;
    frame = window.requestAnimationFrame(() => {
      flowInstance.fitView({ padding: 0.22, maxZoom: 1.05, minZoom: 0.2, duration: 260 });
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
        onNavigateCitation(toCitationFromEvidence({ row: match, fileId, sourceName, citationFocus }));
        return;
      }
    }
    if (data.page) {
      onNavigateCitation(toCitationFromPage({ page: data.page, title: data.title, fileId, sourceName, citationFocus }));
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
          edges={displayEdges.map((edge) => ({ ...edge, type: "mindCurve" }))}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
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
                  onClick={() => (allCollapsibleNodesCollapsed ? handleExpandAll() : handleCollapseAll())}
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
