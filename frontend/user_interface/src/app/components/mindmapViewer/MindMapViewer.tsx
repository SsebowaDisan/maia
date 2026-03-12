import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { MindMapToolbar } from "./MindMapToolbar";
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
  computeRadialLayout,
  NODE_HALF_H,
  NODE_HALF_W,
  looksLikePromptTitle,
  looksNoisyTitle,
  toMindmapPayload,
} from "./viewerHelpers";
import { compactNodeValue, detectDefaultMapType, edgeTypes, nodeTypes, payloadSupportsMapType } from "./viewerGraph";

// Six branch color families — matches MindNodeCard palettes.
const BRANCH_EDGE_COLORS = ["#F97316", "#06B6D4", "#8B5CF6", "#22C55E", "#F59E0B", "#EC4899"];

export function MindMapViewer({
  payload: rawPayload,
  conversationId = null,
  maxDepth = 4,
  viewerHeight = 520,
  onAskNode,
  onFocusNode,
  onSaveMap,
  onShareMap,
}: MindMapViewerProps) {
  const effectiveViewerHeight = Math.max(260, Math.min(1200, Math.round(Number(viewerHeight) || 520)));
  const basePayload = useMemo(() => toMindmapPayload(rawPayload), [rawPayload]);
  const [collapsedNodeIds, setCollapsedNodeIds] = useState<string[]>([]);
  const [activeMapType, setActiveMapType] = useState<MindmapMapType>("structure");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [lastFitKey, setLastFitKey] = useState("");
  const [layoutMode, setLayoutMode] = useState<"balanced" | "horizontal">("balanced");
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
    if (saved.layoutMode === "horizontal" || saved.layoutMode === "balanced") {
      setLayoutMode(saved.layoutMode);
    }
  }, [conversationId, maxDepth, payload]);

  useEffect(() => {
    const key = storageKey(payload, conversationId);
    const state: CanvasState = {
      collapsedNodeIds,
      showReasoningMap: false,
      layoutMode,
      nodePositions: {},
      activeMapType,
      focusedNodeId: selectedNodeId,
    };
    window.localStorage.setItem(key, JSON.stringify(state));
  }, [activeMapType, collapsedNodeIds, conversationId, layoutMode, payload, selectedNodeId]);

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

  const layoutParams = useMemo(
    () => ({
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

  // Switch between radial (balanced) and horizontal (notebook tree) layouts.
  // Radial returns CENTER positions; notebook returns TOP-LEFT positions.
  const layout = useMemo(
    () =>
      layoutMode === "horizontal"
        ? computeNotebookLayout(layoutParams)
        : computeRadialLayout(layoutParams),
    [layoutMode, layoutParams],
  );

  // Returns the CENTER of a node for edge drawing, regardless of layout mode.
  const getCenter = useCallback(
    (nodeId: string): { x: number; y: number } => {
      const pos = layout[nodeId] ?? { x: 0, y: 0 };
      if (layoutMode === "horizontal") {
        const hw = nodeId === rootId ? 92 : NODE_HALF_W;
        const hh = nodeId === rootId ? 22 : NODE_HALF_H;
        return { x: pos.x + hw, y: pos.y + hh };
      }
      return pos;
    },
    [layout, layoutMode, rootId],
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

  const fitView = useCallback(() => {
    flowRef.current?.fitView({ padding: 0.24, maxZoom: 1.05, minZoom: 0.2, duration: 220 });
  }, []);

  // ── Toolbar callbacks ──────────────────────────────────────────────────────

  const handleExpand = useCallback(() => setCollapsedNodeIds([]), []);

  const handleCollapse = useCallback(() => {
    const ids = parsedNodes
      .filter((node) => (childrenByParent.get(node.id) || []).some((child) => allNodeIds.has(child)))
      .map((node) => node.id);
    setCollapsedNodeIds(ids);
  }, [allNodeIds, childrenByParent, parsedNodes]);

  const handleToggleLayout = useCallback(
    () => setLayoutMode((prev) => (prev === "balanced" ? "horizontal" : "balanced")),
    [],
  );

  const handleResetFocus = useCallback(() => setSelectedNodeId(null), []);

  const handleExportJson = useCallback(() => {
    if (!payload) return;
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `mindmap-${activeMapType}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [activeMapType, payload]);

  const handleExportMarkdown = useCallback(() => {
    if (!payload?.nodes?.length) return;
    const lines: string[] = [`# ${payload.title || "Knowledge Map"}\n`];
    const buildLines = (nodeId: string, depth: number) => {
      const node = nodeById.get(nodeId);
      if (!node) return;
      const indent = "  ".repeat(Math.max(0, depth - 1));
      const prefix = depth === 0 ? "" : `${indent}- `;
      lines.push(`${prefix}**${node.title || node.id}**${node.text ? `: ${node.text}` : ""}`);
      for (const childId of childrenByParent.get(nodeId) || []) {
        buildLines(childId, depth + 1);
      }
    };
    if (rootId) buildLines(rootId, 0);
    const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `mindmap-${activeMapType}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }, [activeMapType, childrenByParent, nodeById, payload, rootId]);

  const handleExportPng = useCallback(() => {
    window.print();
  }, []);

  const handleSave = useCallback(() => {
    if (payload && onSaveMap) onSaveMap(payload);
  }, [onSaveMap, payload]);

  const handleShare = useCallback(async () => {
    if (payload && onShareMap) await onShareMap(payload);
  }, [onShareMap, payload]);

  // ── Flow nodes ─────────────────────────────────────────────────────────────

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
          position: (() => {
            const pos = layout[node.id];
            if (!pos) return { x: depth * 200, y: index * 54 };
            // Notebook layout returns top-left directly; radial returns center.
            if (layoutMode === "horizontal") return pos;
            const hw = node.id === rootId ? 92 : NODE_HALF_W;
            const hh = node.id === rootId ? 22 : NODE_HALF_H;
            return { x: pos.x - hw, y: pos.y - hh };
          })(),
          data: {
            title: displayTitle,
            subtitle:
              activeMapType === "work_graph"
                ? [
                    compactNodeValue((node as Record<string, unknown>)["status"]),
                    compactNodeValue((node as Record<string, unknown>)["tool_id"]),
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
      layoutMode,
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
          const srcCenter = getCenter(edge.source);
          const tgtCenter = getCenter(edge.target);
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
    [branchColorIndexMap, depthMap, getCenter, hierarchyEdges, selectedNodeId, visibleIds],
  );

  useEffect(() => {
    if (!flowRef.current || !flowNodes.length) {
      return;
    }
    const key = `${activeMapType}:${layoutMode}:${collapsedNodeIds.join(",")}:${flowNodes.length}:${maxDepth}`;
    if (key === lastFitKey) {
      return;
    }
    const timer = window.setTimeout(() => {
      fitView();
      setLastFitKey(key);
    }, 60);
    return () => window.clearTimeout(timer);
  }, [activeMapType, collapsedNodeIds, fitView, flowNodes, lastFitKey, layoutMode, maxDepth]);

  const hasVariants = Boolean(
    payload?.variants && Object.keys(payload.variants as Record<string, unknown>).length > 0,
  );

  if (!payload || !parsedNodes.length) {
    return (
      <div className="rounded-xl border border-black/[0.08] bg-white p-4 text-[12px] text-[#6e6e73]">
        <p className="font-medium text-[#1d1d1f] mb-1">Mind map unavailable</p>
        <p>No knowledge map was produced for this answer. Ask a research or analytical question to generate one.</p>
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
      <div className="px-3 py-2 border-b border-[#e5e5ea]">
        <MindMapToolbar
          title={String(payload.title || "Knowledge Map")}
          mapType={String(payload.map_type || "structure")}
          kind={String(payload.kind || "map")}
          activeMapType={activeMapType}
          hasVariants={hasVariants}
          layoutMode={layoutMode}
          onSwitchMapType={setActiveMapType}
          onExpand={handleExpand}
          onCollapse={handleCollapse}
          onToggleLayout={handleToggleLayout}
          onResetFocus={handleResetFocus}
          onAutoTidy={fitView}
          onFitView={fitView}
          onExportPng={handleExportPng}
          onExportJson={handleExportJson}
          onExportMarkdown={handleExportMarkdown}
          onSave={handleSave}
          onShare={handleShare}
        />
      </div>
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
