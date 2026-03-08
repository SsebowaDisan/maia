import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BaseEdge,
  Position,
  ReactFlow,
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
  computeRadialLayout,
  NODE_HALF_H,
  NODE_HALF_W,
  looksLikePromptTitle,
  looksNoisyTitle,
  toMindmapPayload,
} from "./viewerHelpers";

/**
 * Returns the point on the boundary of a node at (cx, cy) facing toward (ox, oy).
 * hw/hh are the half-width and half-height of the node (rectangular approximation).
 */
function trimEdge(
  cx: number, cy: number,
  ox: number, oy: number,
  hw: number, hh: number,
): { x: number; y: number } {
  const dx = ox - cx;
  const dy = oy - cy;
  const len = Math.sqrt(dx * dx + dy * dy);
  if (len < 1) return { x: cx, y: cy };
  const abscos = Math.abs(dx / len);
  const abssin = Math.abs(dy / len);
  const d = abscos > 0 && abssin > 0
    ? Math.min(hw / abscos, hh / abssin)
    : abscos > 0 ? hw : hh;
  return { x: cx + (dx / len) * d, y: cy + (dy / len) * d };
}

const nodeTypes = { mind: MindNodeCard };

// Six branch color families — matches MindNodeCard's BRANCH_PALETTES
const BRANCH_EDGE_COLORS = [
  "#F97316", // orange
  "#06B6D4", // cyan
  "#8B5CF6", // purple
  "#22C55E", // green
  "#F59E0B", // amber
  "#EC4899", // pink
];

function CurvedMindEdge({ id, data, style }: EdgeProps) {
  const d = (data ?? {}) as { sx?: number; sy?: number; tx?: number; ty?: number };
  const srcX = Number(d.sx ?? 0);
  const srcY = Number(d.sy ?? 0);
  const tgtX = Number(d.tx ?? 0);
  const tgtY = Number(d.ty ?? 0);

  // Root is at (0,0) — use larger bounds for trimming
  const isRoot = srcX * srcX + srcY * srcY < 25;
  const start = trimEdge(srcX, srcY, tgtX, tgtY, isRoot ? 92 : NODE_HALF_W, isRoot ? 22 : NODE_HALF_H);
  const end   = trimEdge(tgtX, tgtY, srcX, srcY, NODE_HALF_W, NODE_HALF_H);

  // Bezier control point: midpoint bowed gently toward the radial center (origin)
  const mx = (start.x + end.x) / 2;
  const my = (start.y + end.y) / 2;
  const midLen = Math.sqrt(mx * mx + my * my) || 1;
  const edgeLen = Math.sqrt((end.x - start.x) ** 2 + (end.y - start.y) ** 2);
  const bow = Math.min(32, edgeLen * 0.12);
  const cpx = mx - (mx / midLen) * bow;
  const cpy = my - (my / midLen) * bow;

  return (
    <BaseEdge
      id={id}
      path={`M ${start.x} ${start.y} Q ${cpx} ${cpy} ${end.x} ${end.y}`}
      style={style}
    />
  );
}

const edgeTypes = { mindCurve: CurvedMindEdge };

function normalizeMapType(raw: unknown): MindmapMapType {
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

function detectDefaultMapType(payload: MindmapPayload | null): MindmapMapType {
  if (!payload) {
    return "structure";
  }
  const direct = normalizeMapType(payload.map_type);
  if (direct === "context_mindmap" || String(payload.kind || "").trim().toLowerCase() === "context_mindmap") {
    return "context_mindmap";
  }
  if (direct === "work_graph" || String(payload.kind || "").trim().toLowerCase() === "work_graph") {
    return "work_graph";
  }
  const variants = payload.variants;
  if (variants && typeof variants === "object" && Object.prototype.hasOwnProperty.call(variants, "context_mindmap")) {
    return "context_mindmap";
  }
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
  onFocusNode,
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

  // Assign each node a branch color index based on which top-level child it descends from
  const branchColorIndexMap = useMemo(() => {
    const map = new Map<string, number>();
    const topLevelChildren = (childrenByParent.get(rootId) || []).filter((id) => nodeById.has(id));
    topLevelChildren.forEach((childId, branchIndex) => {
      const queue = [childId];
      while (queue.length) {
        const id = queue.shift()!;
        if (!map.has(id)) {
          map.set(id, branchIndex);
          (childrenByParent.get(id) || []).forEach((c) => queue.push(c));
        }
      }
    });
    return map;
  }, [childrenByParent, nodeById, rootId]);

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

  // Radial layout — returns CENTER positions for each node.
  // Root is at (0, 0); branches radiate outward proportionally by leaf count.
  const layout = useMemo(
    () =>
      computeRadialLayout({
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

  const resolveNodePayload = useCallback(
    (nodeId: string) => {
      const selected = parsedNodes.find((row) => row.id === nodeId);
      if (!selected) {
        return null;
      }
      return {
        nodeId: selected.id,
        title: selected.title || "",
        text: selected.text || "",
        pageRef: selected.page_ref || selected.page || undefined,
        sourceId: selected.source_id,
        sourceName: selected.source_name,
      };
    },
    [parsedNodes],
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
          // layout returns CENTER positions; ReactFlow needs top-left corner
          position: (() => {
            const center = layout[node.id];
            if (!center) return { x: depth * 200, y: index * 54 };
            const hw = node.id === rootId ? 92 : NODE_HALF_W;
            const hh = node.id === rootId ? 22 : NODE_HALF_H;
            return { x: center.x - hw, y: center.y - hh };
          })(),
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
            branchColorIndex: branchColorIndexMap.get(node.id) ?? -1,
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
      activeMapType,
      branchColorIndexMap,
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
          const colorIndex = branchColorIndexMap.get(edge.target) ?? branchColorIndexMap.get(edge.source) ?? -1;
          const branchColor = colorIndex >= 0 ? BRANCH_EDGE_COLORS[colorIndex % BRANCH_EDGE_COLORS.length] : "#A3A3A3";
          const isHighlighted = !selectedNodeId || edge.source === selectedNodeId || edge.target === selectedNodeId;
          // Pass radial CENTER positions so CurvedMindEdge can draw node-boundary-to-boundary paths
          const srcCenter = layout[edge.source] ?? { x: 0, y: 0 };
          const tgtCenter = layout[edge.target] ?? { x: 0, y: 0 };
          return {
            id: edge.id || `${edge.source}->${edge.target}`,
            source: edge.source,
            target: edge.target,
            type: "mindCurve",
            data: { sx: srcCenter.x, sy: srcCenter.y, tx: tgtCenter.x, ty: tgtCenter.y },
            style: {
              stroke: branchColor,
              strokeWidth: sourceDepth === 0 ? 2.8 : sourceDepth === 1 ? 2.2 : 1.6,
              opacity: isHighlighted ? 0.85 : 0.35,
              strokeLinecap: "round",
            },
          };
        }),
    [branchColorIndexMap, depthMap, hierarchyEdges, layout, selectedNodeId, visibleIds],
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
    const focusPayload = resolveNodePayload(node.id);
    if (focusPayload && onFocusNode) {
      onFocusNode(focusPayload);
    }
    setSelectedNodeId(node.id);
  };

  return (
    <div className="overflow-hidden rounded-2xl border border-[#e5e5ea] bg-white shadow-sm">
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
          className="bg-white"
        />
      </div>
    </div>
  );
}
