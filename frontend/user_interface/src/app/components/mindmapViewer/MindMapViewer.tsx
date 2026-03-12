import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { type Edge, type Node, type NodeMouseHandler, type ReactFlowInstance } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { MindMapFlowCanvas } from "./MindMapFlowCanvas";
import { MindMapToolbar } from "./MindMapToolbar";
import { MindMapViewerDetails } from "./MindMapViewerDetails";
import type { FocusNodePayload, MindMapViewerProps, MindmapMapType, MindmapPayload } from "./types";
import { clampMindmapDepth, computeDepths, drawPngFromLayout, focusedBranchIds, isDescendant, parseCanvasState, storageKey, type CanvasState, type MindNodeData } from "./utils";
import { computeInitialCollapsedFromPayload, computeNotebookLayout, computeRadialLayout, toMindmapPayload } from "./viewerHelpers";
import { payloadSupportsMapType } from "./viewerGraph";
import { collectAvailableMindmapTypes, detectMindmapMapType, preferredLayoutForPayload } from "./presentation";
import { buildBranchColorIndexMap, buildChildrenByParent, buildNodeOrder, buildParentCount, resolveRootId, toFocusPayload } from "./viewerDerive";
import { buildFlowEdges, buildFlowNodes, buildReasoningOverlayEdges } from "./viewerElements";
import { normalizeMindmapPayloadForViewer } from "./viewerNormalize";
import { downloadMindmapJson, downloadMindmapMarkdown } from "./exporters";
import { MindMapEmptyState } from "./MindMapEmptyState";
export function MindMapViewer({
  payload: rawPayload,
  conversationId = null,
  maxDepth = 4,
  viewerHeight = 520,
  onAskNode,
  onFocusNode,
  onSaveMap,
  onShareMap,
  onMapTypeChange,
}: MindMapViewerProps) {
  const effectiveViewerHeight = Math.max(260, Math.min(1200, Math.round(Number(viewerHeight) || 520)));
  const basePayload = useMemo(() => toMindmapPayload(rawPayload), [rawPayload]);
  const detectedBaseMapType = useMemo(() => detectMindmapMapType(basePayload), [basePayload]);
  const [collapsedNodeIds, setCollapsedNodeIds] = useState<string[]>([]);
  const [activeMapType, setActiveMapType] = useState<MindmapMapType>("structure");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null);
  const [showReasoningMap, setShowReasoningMap] = useState(false);
  const [viewerMaxDepth, setViewerMaxDepth] = useState(() => clampMindmapDepth(maxDepth));
  const [lastFitKey, setLastFitKey] = useState("");
  const flowRef = useRef<ReactFlowInstance<Node<MindNodeData>, Edge> | null>(null);
  useEffect(() => {
    setActiveMapType(detectedBaseMapType);
  }, [basePayload, detectedBaseMapType]);
  const payload = useMemo(() => {
    if (!basePayload) {
      return null;
    }
    if (activeMapType === detectedBaseMapType) {
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
  }, [activeMapType, basePayload, detectedBaseMapType]);
  const viewerPayload = useMemo(
    () => normalizeMindmapPayloadForViewer(payload, activeMapType),
    [activeMapType, payload],
  );
  useEffect(() => {
    const key = storageKey(viewerPayload, conversationId);
    const saved = parseCanvasState(window.localStorage.getItem(key));
    const nextMapType = saved && payloadSupportsMapType(basePayload, saved.activeMapType)
      ? saved.activeMapType
      : detectMindmapMapType(basePayload);
    const initialDepth = clampMindmapDepth(saved?.maxDepth ?? maxDepth);
    const variantPayload =
      basePayload && nextMapType !== detectedBaseMapType && basePayload.variants?.[nextMapType]
        ? (basePayload.variants[nextMapType] as MindmapPayload)
        : basePayload;
    const normalizedVariantPayload = normalizeMindmapPayloadForViewer(variantPayload, nextMapType);
    const variantNodeIds = new Set(
      (normalizedVariantPayload?.nodes || [])
        .map((node) => String(node?.id || "").trim())
        .filter(Boolean),
    );
    const restoredFocusNodeId =
      saved?.focusNodeId && variantNodeIds.has(saved.focusNodeId) ? saved.focusNodeId : null;
    const restoredSelectedNodeId =
      saved?.focusedNodeId && variantNodeIds.has(saved.focusedNodeId)
        ? saved.focusedNodeId
        : restoredFocusNodeId;
    setCollapsedNodeIds(computeInitialCollapsedFromPayload(normalizedVariantPayload, initialDepth));
    setSelectedNodeId(restoredSelectedNodeId);
    setFocusNodeId(restoredFocusNodeId);
    setActiveMapType(nextMapType);
    setViewerMaxDepth(initialDepth);
    setShowReasoningMap(false);
  }, [basePayload, conversationId, detectedBaseMapType, maxDepth, viewerPayload]);
  useEffect(() => {
    const key = storageKey(viewerPayload, conversationId);
    const state: CanvasState = {
      collapsedNodeIds,
      showReasoningMap,
      layoutMode: "horizontal",
      nodePositions: {},
      activeMapType,
      focusedNodeId: selectedNodeId,
      focusNodeId,
      maxDepth: viewerMaxDepth,
    };
    window.localStorage.setItem(key, JSON.stringify(state));
  }, [
    activeMapType,
    collapsedNodeIds,
    conversationId,
    focusNodeId,
    viewerPayload,
    selectedNodeId,
    showReasoningMap,
    viewerMaxDepth,
  ]);
  const parsedNodes = useMemo(() => viewerPayload?.nodes || [], [viewerPayload]);
  const parsedEdges = useMemo(() => viewerPayload?.edges || [], [viewerPayload]);
  const hierarchyEdges = useMemo(
    () => parsedEdges.filter((edge) => !edge.type || edge.type === "hierarchy"),
    [parsedEdges],
  );
  const nodeById = useMemo(() => new Map(parsedNodes.map((node) => [node.id, node])), [parsedNodes]);
  const childrenByParent = useMemo(() => buildChildrenByParent(hierarchyEdges), [hierarchyEdges]);
  const parentCount = useMemo(() => buildParentCount(hierarchyEdges), [hierarchyEdges]);
  const rootId = useMemo(
    () => resolveRootId(viewerPayload, parsedNodes, nodeById, parentCount, childrenByParent),
    [childrenByParent, nodeById, parentCount, parsedNodes, viewerPayload],
  );
  const depthMap = useMemo(() => computeDepths(rootId, hierarchyEdges), [hierarchyEdges, rootId]);
  const branchColorIndexMap = useMemo(
    () => buildBranchColorIndexMap(childrenByParent, nodeById, rootId),
    [childrenByParent, nodeById, rootId],
  );
  const nodeOrder = useMemo(() => buildNodeOrder(parsedNodes, depthMap), [depthMap, parsedNodes]);
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
  const focusVisibleIds = useMemo(() => (focusNodeId ? focusedBranchIds(focusNodeId, hierarchyEdges) : null), [focusNodeId, hierarchyEdges]);
  const visibleBaseNodes = useMemo(
    () =>
      parsedNodes
        .filter((node) => (focusVisibleIds ? focusVisibleIds.has(node.id) : !hiddenIds.has(node.id)))
        .filter((node) => typeof depthMap[node.id] === "number")
        .filter((node) => (depthMap[node.id] ?? 0) <= viewerMaxDepth),
    [depthMap, focusVisibleIds, hiddenIds, parsedNodes, viewerMaxDepth],
  );
  const allNodeIds = useMemo(() => new Set(parsedNodes.map((node) => node.id)), [parsedNodes]);
  const visibleIds = useMemo(() => new Set(visibleBaseNodes.map((node) => node.id)), [visibleBaseNodes]);
  const layoutParams = useMemo(
    () => ({
      rootId,
      nodeIds: visibleIds,
      childrenByParent,
      depthMap,
      collapsedSet: focusVisibleIds ? new Set<string>() : new Set(collapsedNodeIds),
      maxDepth: viewerMaxDepth,
      nodeOrder,
    }),
    [childrenByParent, collapsedNodeIds, depthMap, focusVisibleIds, nodeOrder, rootId, viewerMaxDepth, visibleIds],
  );
  const layoutMode = "horizontal" as const;
  const layout = useMemo(() => computeNotebookLayout(layoutParams), [layoutParams]);
  const getCenter = useCallback(
    (nodeId: string): { x: number; y: number } => {
      const pos = layout[nodeId] ?? { x: 0, y: 0 };
      if (layoutMode === "horizontal") {
        const depth = depthMap[nodeId] ?? 1;
        const halfWidth = depth <= 0 ? 200 : depth === 1 ? 160 : 140;
        const halfHeight = depth <= 0 ? 38 : 34;
        return { x: pos.x + halfWidth, y: pos.y + halfHeight };
      }
      return pos;
    },
    [depthMap, layout, layoutMode],
  );
  const hasReasoningMap = Boolean(payload?.reasoning_map?.edges?.length);
  const resolveNodePayload = useCallback(
    (nodeId: string) => toFocusPayload(parsedNodes.find((row) => row.id === nodeId) || null),
    [parsedNodes],
  );
  const fitView = useCallback(() => {
    flowRef.current?.fitView({ padding: 0.14, maxZoom: 1.1, minZoom: 0.2, duration: 220 });
  }, []);
  const handleFlowInit = useCallback((instance: ReactFlowInstance<Node<MindNodeData>, Edge>) => {
    flowRef.current = instance;
    setLastFitKey("");
  }, []);
  const handleExpand = useCallback(() => setCollapsedNodeIds([]), []);
  const handleCollapse = useCallback(() => {
    setCollapsedNodeIds(computeInitialCollapsedFromPayload(viewerPayload, viewerMaxDepth));
  }, [viewerPayload, viewerMaxDepth]);
  const toggleNodeCollapse = useCallback((nodeId: string) => {
    setCollapsedNodeIds((previous) => {
      const isCollapsed = previous.includes(nodeId);
      if (!isCollapsed) {
        return [...previous, nodeId];
      }
      const next = new Set(previous.filter((entry) => entry !== nodeId));
      const directChildren = (childrenByParent.get(nodeId) || []).filter(
        (childId) => (depthMap[childId] ?? Number.MAX_SAFE_INTEGER) <= viewerMaxDepth,
      );
      directChildren.forEach((childId) => {
        const grandChildren = (childrenByParent.get(childId) || []).filter(
          (grandChildId) => (depthMap[grandChildId] ?? Number.MAX_SAFE_INTEGER) <= viewerMaxDepth,
        );
        if (grandChildren.length > 0) {
          next.add(childId);
        }
      });
      return Array.from(next);
    });
  }, [childrenByParent, depthMap, viewerMaxDepth]);
  const handleSwitchMapType = useCallback(
    (mapType: MindmapMapType) => {
      const variantPayload =
        basePayload && mapType !== detectedBaseMapType && basePayload.variants?.[mapType]
          ? (basePayload.variants[mapType] as MindmapPayload)
          : basePayload;
      const normalizedVariantPayload = normalizeMindmapPayloadForViewer(variantPayload, mapType);
      setCollapsedNodeIds(computeInitialCollapsedFromPayload(normalizedVariantPayload, viewerMaxDepth));
      setActiveMapType(mapType);
      setSelectedNodeId(null);
      setFocusNodeId(null);
      setShowReasoningMap(false);
      onMapTypeChange?.(mapType);
    },
    [basePayload, detectedBaseMapType, onMapTypeChange, viewerMaxDepth],
  );
  const handleExportJson = useCallback(() => {
    if (!payload) {
      return;
    }
    downloadMindmapJson(payload, activeMapType);
  }, [activeMapType, payload]);
  const handleExportMarkdown = useCallback(() => {
    if (!payload) {
      return;
    }
    downloadMindmapMarkdown({
      payload,
      activeMapType,
      nodeById,
      childrenByParent,
      rootId,
    });
  }, [activeMapType, childrenByParent, nodeById, payload, rootId]);
  const handleSave = useCallback(() => {
    if (payload && onSaveMap) {
      onSaveMap(payload);
    }
  }, [onSaveMap, payload]);
  const handleShare = useCallback(async () => {
    if (payload && onShareMap) {
      await onShareMap(payload);
    }
  }, [onShareMap, payload]);
  const normalizedReasoningEdges = useMemo(() => {
    if (!payload?.reasoning_map?.edges?.length) {
      return [];
    }
    const reasoningNodeTargetById = new Map(
      (payload.reasoning_map.nodes || []).map((node) => [node.id, node.node_id || node.id]),
    );
    return payload.reasoning_map.edges
      .map((edge) => ({
        id: edge.id,
        source: String(reasoningNodeTargetById.get(edge.source) || edge.source || ""),
        target: String(reasoningNodeTargetById.get(edge.target) || edge.target || ""),
      }))
      .filter((edge) => edge.source && edge.target && nodeById.has(edge.source) && nodeById.has(edge.target));
  }, [nodeById, payload?.reasoning_map]);
  const flowNodes = useMemo(
    () =>
      buildFlowNodes({
        visibleNodes: visibleBaseNodes,
        activeMapType,
        allNodeIds,
        branchColorIndexMap,
        childrenByParent,
        collapsedNodeIds,
        depthMap,
        layout,
        layoutMode,
        maxDepth: viewerMaxDepth,
        nodeById,
        rootId,
        selectedNodeId,
        onToggleNode: toggleNodeCollapse,
        isInteractive: Boolean(onFocusNode || onAskNode),
      }),
    [
      activeMapType,
      allNodeIds,
      branchColorIndexMap,
      childrenByParent,
      collapsedNodeIds,
      depthMap,
      layout,
      layoutMode,
      viewerMaxDepth,
      nodeById,
      onAskNode,
      onFocusNode,
      rootId,
      selectedNodeId,
      toggleNodeCollapse,
      visibleBaseNodes,
    ],
  );
  const hierarchyFlowEdges = useMemo(
    () =>
      buildFlowEdges({
        hierarchyEdges,
        visibleIds,
        depthMap,
        branchColorIndexMap,
        selectedNodeId,
        getCenter,
      }),
    [branchColorIndexMap, depthMap, getCenter, hierarchyEdges, selectedNodeId, visibleIds],
  );
  const reasoningFlowEdges = useMemo(
    () =>
      showReasoningMap && hasReasoningMap && layoutMode === "balanced"
        ? buildReasoningOverlayEdges({
            reasoningEdges: normalizedReasoningEdges,
            visibleIds,
            getCenter,
          })
        : [],
    [getCenter, hasReasoningMap, layoutMode, normalizedReasoningEdges, showReasoningMap, visibleIds],
  );
  const flowEdges = useMemo(
    () => [...hierarchyFlowEdges, ...reasoningFlowEdges],
    [hierarchyFlowEdges, reasoningFlowEdges],
  );
  const handleExportPng = useCallback(() => {
    if (!flowNodes.length) {
      return;
    }
    drawPngFromLayout(flowNodes, flowEdges, String(payload?.title || activeMapType || "mindmap"));
  }, [activeMapType, flowEdges, flowNodes, payload?.title]);
  useEffect(() => {
    if (!hasReasoningMap && showReasoningMap) {
      setShowReasoningMap(false);
    }
  }, [hasReasoningMap, showReasoningMap]);
  useEffect(() => {
    if (focusNodeId && !nodeById.has(focusNodeId)) {
      setFocusNodeId(null);
    }
  }, [focusNodeId, nodeById]);
  useEffect(() => {
    if (!flowRef.current || !flowNodes.length) {
      return;
    }
    const key = `${activeMapType}:${layoutMode}:${focusNodeId || ""}:${viewerMaxDepth}`;
    if (key === lastFitKey) {
      return;
    }
    const timer = window.setTimeout(() => {
      fitView();
      setLastFitKey(key);
    }, 60);
    return () => window.clearTimeout(timer);
  }, [activeMapType, fitView, focusNodeId, flowNodes, lastFitKey, layoutMode, viewerMaxDepth]);
  const availableMapTypes = useMemo(() => collectAvailableMindmapTypes(basePayload), [basePayload]);
  const selectedNode = useMemo(
    () => (selectedNodeId ? parsedNodes.find((node) => node.id === selectedNodeId) || null : null),
    [parsedNodes, selectedNodeId],
  );
  const handleNodeClick: NodeMouseHandler<Node<MindNodeData>> = (_event, node) => {
    const focusPayload = resolveNodePayload(node.id);
    if (focusPayload && onFocusNode) onFocusNode(focusPayload);
    setSelectedNodeId(node.id);
  };
  const handleSelectNode = useCallback((nodeId: string) => {
    setSelectedNodeId(nodeId);
    const focusPayload = resolveNodePayload(nodeId);
    if (focusPayload && onFocusNode) {
      onFocusNode(focusPayload);
    }
  }, [onFocusNode, resolveNodePayload]);
  const handleAskSelectedNode = useCallback((focusPayload: FocusNodePayload) => {
    setSelectedNodeId(focusPayload.nodeId);
    onAskNode?.(focusPayload);
  }, [onAskNode]);
  const handleFocusBranch = useCallback((nodeId: string | null) => {
    if (!nodeId) {
      setFocusNodeId(null);
      return;
    }
    setFocusNodeId((previous) => (previous === nodeId ? null : nodeId));
    setSelectedNodeId(nodeId);
  }, []);
  const handleClearFocus = useCallback(() => setFocusNodeId(null), []);
  if (!payload || !parsedNodes.length) {
    return <MindMapEmptyState />;
  }
  return (
    <div className="overflow-hidden rounded-[28px] border border-[#dedfd7] bg-[linear-gradient(180deg,#fcfcfa_0%,#f6f5f1_100%)] shadow-[0_18px_50px_rgba(15,23,42,0.08)]">
      <div className="border-b border-black/[0.06] bg-[linear-gradient(180deg,rgba(255,255,255,0.84),rgba(251,251,248,0.78))] px-5 py-4 backdrop-blur md:px-6">
        <MindMapToolbar
          activeMapType={activeMapType}
          availableMapTypes={availableMapTypes}
          maxDepth={viewerMaxDepth}
          showReasoningMap={showReasoningMap}
          hasReasoningMap={hasReasoningMap}
          focusNodeId={focusNodeId}
          onSwitchMapType={handleSwitchMapType}
          onExpand={handleExpand}
          onCollapse={handleCollapse}
          onFitView={fitView}
          onMaxDepthChange={(depth) => setViewerMaxDepth(clampMindmapDepth(depth))}
          onToggleReasoningMap={() => setShowReasoningMap((previous) => !previous)}
          onClearFocus={handleClearFocus}
          onExportPng={handleExportPng}
          onExportJson={handleExportJson}
          onExportMarkdown={handleExportMarkdown}
          onSave={handleSave}
          onShare={handleShare}
        />
      </div>
      <div className="relative">
        <div className="grid min-h-0 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="min-w-0 px-4 pb-6 pt-4 md:px-5 md:pb-8 md:pt-5">
          <div
            className="overflow-hidden rounded-[24px] border border-black/[0.06] bg-white shadow-[inset_0_1px_0_rgba(255,255,255,0.88)]"
            style={{ height: `${effectiveViewerHeight}px` }}
          >
            <MindMapFlowCanvas
              height={effectiveViewerHeight}
              nodes={flowNodes}
              edges={flowEdges}
              onInit={handleFlowInit}
              onNodeClick={handleNodeClick}
            />
          </div>
          </div>
          <aside className="border-t border-black/[0.06] bg-[linear-gradient(180deg,#f8f7f3_0%,#f3f1eb_100%)] px-4 pb-6 pt-4 xl:border-l xl:border-t-0 xl:px-5 xl:pb-8 xl:pt-5">
            <div className="xl:sticky xl:top-5">
            <MindMapViewerDetails
              activeMapType={activeMapType}
              selectedNode={selectedNode}
              onFocusBranch={handleFocusBranch}
              isFocusActive={Boolean(selectedNode && focusNodeId === selectedNode.id)}
              onAskNode={onAskNode ? handleAskSelectedNode : undefined}
            />
            </div>
          </aside>
        </div>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-[linear-gradient(180deg,rgba(246,245,241,0)_0%,rgba(246,245,241,0.82)_62%,rgba(246,245,241,1)_100%)]" />
        <div className="pointer-events-none h-5 bg-[linear-gradient(180deg,rgba(246,245,241,0.78),rgba(246,245,241,1))]" />
      </div>
    </div>
  );
}
