import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BaseEdge,
  Position,
  ReactFlow,
  getBezierPath,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeMouseHandler,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { MindNodeCard } from "./MindNodeCard";
import type { MindMapViewerProps, MindmapMapType, MindmapPayload } from "./types";
import {
  computeDepths,
  isDescendant,
  parseCanvasState,
  storageKey,
  type CanvasState,
  type MindNodeData,
} from "./utils";
import {
  computeInitialCollapsedFromPayload,
  computeNotebookLayout,
  DEPTH_GAP,
  LEAF_GAP,
  looksLikePromptTitle,
  looksNoisyTitle,
  ROOT_X,
  toMindmapPayload,
  TOP_PADDING,
} from "./viewerHelpers";

const nodeTypes = { mind: MindNodeCard };

function CurvedMindEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
}: EdgeProps) {
  const [path] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    curvature: 0.42,
  });
  return <BaseEdge id={id} path={path} style={style} />;
}

const edgeTypes = { mindCurve: CurvedMindEdge };

function normalizeMapType(raw: unknown): MindmapMapType {
  const value = String(raw || "").trim().toLowerCase();
  if (value === "work_graph") {
    return "work_graph";
  }
  if (value === "evidence") {
    return "evidence";
  }
  return "structure";
}

function detectDefaultMapType(payload: MindmapPayload | null): MindmapMapType {
  if (!payload) {
    return "structure";
  }
  const direct = normalizeMapType(payload.map_type);
  if (direct === "work_graph" || String(payload.kind || "").trim().toLowerCase() === "work_graph") {
    return "work_graph";
  }
  const variants = payload.variants;
  if (variants && typeof variants === "object" && Object.prototype.hasOwnProperty.call(variants, "work_graph")) {
    return "work_graph";
  }
  return direct;
}

function _compactNodeValue(raw: unknown): string {
  const text = String(raw || "").trim();
  if (!text) {
    return "";
  }
  if (text.length <= 40) {
    return text;
  }
  return `${text.slice(0, 37).trimEnd()}...`;
}

function payloadSupportsMapType(payload: MindmapPayload | null, mapType: MindmapMapType): boolean {
  if (!payload) {
    return false;
  }
  if (normalizeMapType(payload.map_type) === mapType) {
    return true;
  }
  const variants = payload.variants;
  if (!variants || typeof variants !== "object") {
    return false;
  }
  return Object.prototype.hasOwnProperty.call(variants, mapType);
}

export function MindMapViewer({
  payload: rawPayload,
  conversationId = null,
  maxDepth = 4,
  viewerHeight = 520,
  onAskNode,
}: MindMapViewerProps) {
  const effectiveViewerHeight = Math.max(260, Math.min(1200, Math.round(Number(viewerHeight) || 520)));
  const basePayload = useMemo(() => toMindmapPayload(rawPayload), [rawPayload]);
  const [collapsedNodeIds, setCollapsedNodeIds] = useState<string[]>([]);
  const [activeMapType, setActiveMapType] = useState<MindmapMapType>("structure");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [lastFitKey, setLastFitKey] = useState("");
  const flowRef = useRef<ReactFlowInstance<Node<MindNodeData>, Edge> | null>(null);

  useEffect(() => {
    const detected = detectDefaultMapType(basePayload);
    setActiveMapType(detected);
  }, [basePayload]);

  const payload = useMemo(() => {
    if (!basePayload) {
      return null;
    }
    const detected = detectDefaultMapType(basePayload);
    if (activeMapType === detected) {
      return basePayload;
    }
    const variants = basePayload.variants;
    if (!variants || typeof variants !== "object") {
      return basePayload;
    }
    const variant = variants[activeMapType];
    if (!variant || typeof variant !== "object") {
      return basePayload;
    }
    return variant as MindmapPayload;
  }, [activeMapType, basePayload]);

  useEffect(() => {
    const key = storageKey(payload, conversationId);
    const saved = parseCanvasState(window.localStorage.getItem(key));
    if (!saved) {
      setCollapsedNodeIds(computeInitialCollapsedFromPayload(payload, maxDepth));
      setSelectedNodeId(null);
      return;
    }
    setCollapsedNodeIds(saved.collapsedNodeIds);
    setActiveMapType(
      payloadSupportsMapType(payload, saved.activeMapType)
        ? saved.activeMapType
        : detectDefaultMapType(payload),
    );
    setSelectedNodeId(saved.focusedNodeId);
  }, [conversationId, maxDepth, payload]);

  useEffect(() => {
    const key = storageKey(payload, conversationId);
    const state: CanvasState = {
      collapsedNodeIds,
      showReasoningMap: false,
      layoutMode: "balanced",
      nodePositions: {},
      activeMapType,
      focusedNodeId: selectedNodeId,
    };
    window.localStorage.setItem(key, JSON.stringify(state));
  }, [activeMapType, collapsedNodeIds, conversationId, payload, selectedNodeId]);

  const parsedNodes = useMemo(() => payload?.nodes || [], [payload]);
  const parsedEdges = useMemo(() => payload?.edges || [], [payload]);
  const hierarchyEdges = useMemo(
    () => parsedEdges.filter((edge) => !edge.type || edge.type === "hierarchy"),
    [parsedEdges],
  );
  const nodeById = useMemo(() => new Map(parsedNodes.map((node) => [node.id, node])), [parsedNodes]);

  const childrenByParent = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const edge of hierarchyEdges) {
      const rows = map.get(edge.source) || [];
      rows.push(edge.target);
      map.set(edge.source, rows);
    }
    return map;
  }, [hierarchyEdges]);

  const parentCount = useMemo(() => {
    const map = new Map<string, number>();
    for (const edge of hierarchyEdges) {
      map.set(edge.target, (map.get(edge.target) || 0) + 1);
    }
    return map;
  }, [hierarchyEdges]);

  const rootId = useMemo(() => {
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
      if ((childType === "source" || childType === "web_source") && childVisibleChildren > 8) {
        return candidate;
      }
      return childId;
    }
    return candidate;
  }, [childrenByParent, nodeById, parentCount, parsedNodes, payload]);

  const depthMap = useMemo(() => computeDepths(rootId, hierarchyEdges), [hierarchyEdges, rootId]);

  const nodeOrder = useMemo(() => {
    const order = new Map<string, number>();
    parsedNodes.forEach((node, index) => {
      const pageRaw = String(node.page_ref || node.page || "");
      const pageMatch = pageRaw.match(/\d+/)?.[0];
      const pageNumber = pageMatch ? Number.parseInt(pageMatch, 10) : Number.NaN;
      const rank = Number.isFinite(pageNumber) ? pageNumber * 1000 : (depthMap[node.id] ?? 99) * 1000 + index;
      order.set(node.id, rank + index / 1000);
    });
    return order;
  }, [depthMap, parsedNodes]);

  const hiddenIds = useMemo(() => {
    const result = new Set<string>();
    for (const collapsedId of collapsedNodeIds) {
      for (const node of parsedNodes) {
        if (isDescendant(node.id, collapsedId, childrenByParent)) {
          result.add(node.id);
        }
      }
    }
    return result;
  }, [childrenByParent, collapsedNodeIds, parsedNodes]);

  const visibleBaseNodes = useMemo(
    () =>
      parsedNodes
        .filter((node) => !hiddenIds.has(node.id))
        .filter((node) => typeof depthMap[node.id] === "number")
        .filter((node) => (depthMap[node.id] ?? 0) <= maxDepth),
    [depthMap, hiddenIds, maxDepth, parsedNodes],
  );

  const allNodeIds = useMemo(() => new Set(parsedNodes.map((node) => node.id)), [parsedNodes]);

  const visibleIds = useMemo(() => new Set(visibleBaseNodes.map((node) => node.id)), [visibleBaseNodes]);

  const layout = useMemo(
    () =>
      computeNotebookLayout({
        rootId,
        nodeIds: visibleIds,
        childrenByParent,
        depthMap,
        collapsedSet: new Set(collapsedNodeIds),
        maxDepth,
        nodeOrder,
      }),
    [childrenByParent, collapsedNodeIds, depthMap, maxDepth, nodeOrder, rootId, visibleIds],
  );

  const handleAsk = useCallback(
    (nodeId: string) => {
      setSelectedNodeId(nodeId);
      if (!onAskNode) {
        return;
      }
      const selected = parsedNodes.find((row) => row.id === nodeId);
      if (!selected) {
        return;
      }
      onAskNode({
        nodeId: selected.id,
        title: selected.title || "",
        text: selected.text || "",
        pageRef: selected.page_ref || selected.page || undefined,
        sourceId: selected.source_id,
        sourceName: selected.source_name,
      });
    },
    [onAskNode, parsedNodes],
  );

  const flowNodes = useMemo(
    () =>
      visibleBaseNodes.map((node, index): Node<MindNodeData> => {
        const depth = depthMap[node.id] ?? 0;
        const hasChildren = (childrenByParent.get(node.id) || []).some(
          (child) => allNodeIds.has(child) && (depthMap[child] ?? Number.MAX_SAFE_INTEGER) <= maxDepth,
        );
        const nodeTitle = String(node.title || node.id || "").trim();
        let displayTitle = nodeTitle || node.id;
        if (looksNoisyTitle(nodeTitle)) {
          const promotedTitle = (childrenByParent.get(node.id) || [])
            .map((childId) => String(nodeById.get(childId)?.title || "").trim())
            .find((candidate) => candidate && !looksNoisyTitle(candidate));
          if (promotedTitle) {
            displayTitle = promotedTitle;
          }
        }
        if (looksNoisyTitle(displayTitle)) {
          const pageValue = String(node.page_ref || node.page || "").trim();
          displayTitle = pageValue || String(node.id || "");
        }

        return {
          id: node.id,
          type: "mind",
          draggable: false,
          sourcePosition: Position.Right,
          targetPosition: Position.Left,
          position:
            layout[node.id] || {
              x: ROOT_X + depth * DEPTH_GAP,
              y: TOP_PADDING + index * LEAF_GAP,
            },
          data: {
            title: displayTitle,
            subtitle:
              activeMapType === "work_graph"
                ? [
                    _compactNodeValue((node as Record<string, unknown>)["status"]),
                    _compactNodeValue((node as Record<string, unknown>)["tool_id"]),
                  ]
                    .filter((row) => row.length > 0)
                    .join(" • ") || undefined
                : undefined,
            hasChildren,
            collapsed: collapsedNodeIds.includes(node.id),
            nodeType: String(node.type || node.node_type || ""),
            isRoot: node.id === rootId,
            depth,
            isSelected: selectedNodeId === node.id,
            onToggle: (targetNodeId: string) =>
              setCollapsedNodeIds((prev) =>
                prev.includes(targetNodeId)
                  ? prev.filter((entry) => entry !== targetNodeId)
                  : [...prev, targetNodeId],
              ),
            onAsk: onAskNode ? handleAsk : undefined,
          },
        };
      }),
    [
      childrenByParent,
      collapsedNodeIds,
      depthMap,
      allNodeIds,
      handleAsk,
      layout,
      nodeById,
      onAskNode,
      rootId,
      selectedNodeId,
      visibleBaseNodes,
      visibleIds,
    ],
  );

  const flowEdges = useMemo(
    () =>
      hierarchyEdges
        .filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target))
        .map((edge): Edge => {
          const sourceDepth = depthMap[edge.source] ?? 0;
          return {
            id: edge.id || `${edge.source}->${edge.target}`,
            source: edge.source,
            target: edge.target,
            type: "mindCurve",
            style: {
              stroke: sourceDepth <= 1 ? "#7ea6ff" : "#72a5f6",
              strokeWidth: sourceDepth === 0 ? 3.1 : sourceDepth === 1 ? 2.3 : 1.8,
              opacity: selectedNodeId && edge.source !== selectedNodeId && edge.target !== selectedNodeId ? 0.72 : 0.98,
              strokeLinecap: "round",
            },
          };
        }),
    [depthMap, hierarchyEdges, selectedNodeId, visibleIds],
  );

  const fitView = useCallback(() => {
    flowRef.current?.fitView({ padding: 0.24, maxZoom: 1.05, minZoom: 0.2, duration: 220 });
  }, []);

  useEffect(() => {
    if (!flowRef.current || !flowNodes.length) {
      return;
    }
    const key = `${activeMapType}:${collapsedNodeIds.join(",")}:${flowNodes.length}:${maxDepth}`;
    if (key === lastFitKey) {
      return;
    }
    const timer = window.setTimeout(() => {
      fitView();
      setLastFitKey(key);
    }, 60);
    return () => window.clearTimeout(timer);
  }, [activeMapType, collapsedNodeIds, fitView, flowNodes, lastFitKey, maxDepth]);

  if (!payload || !parsedNodes.length) {
    return (
      <div className="rounded-xl border border-black/[0.08] bg-white p-4 text-[12px] text-[#6e6e73]">
        Mind-map is not available for this answer.
      </div>
    );
  }

  const handleNodeClick: NodeMouseHandler<Node<MindNodeData>> = (_event, node) => {
    if (!node.data.onAsk) {
      setSelectedNodeId(node.id);
      return;
    }
    handleAsk(node.id);
  };

  return (
    <div className="overflow-hidden rounded-2xl border border-[#1f2a41] bg-[#01040a] shadow-[0_18px_54px_-30px_rgba(0,0,0,0.8)]">
      <div className="w-full" style={{ height: `${effectiveViewerHeight}px` }}>
        <ReactFlow
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          nodes={flowNodes}
          edges={flowEdges}
          onInit={(instance) => {
            flowRef.current = instance;
            window.setTimeout(() => fitView(), 50);
          }}
          onNodeClick={handleNodeClick}
          fitView
          fitViewOptions={{ padding: 0.24, maxZoom: 1.05 }}
          minZoom={0.2}
          maxZoom={1.7}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          zoomOnDoubleClick={false}
          panOnDrag
          zoomOnPinch
          zoomOnScroll
          proOptions={{ hideAttribution: true }}
          className="bg-[#01040a]"
        />
      </div>
    </div>
  );
}
