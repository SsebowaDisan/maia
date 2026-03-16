import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { type Edge, type Node, type NodeMouseHandler, type ReactFlowInstance } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Info } from "lucide-react";
import { exportMindmapMarkdown as exportMindmapMarkdownApi, getMindmapBySource } from "../../../api/client";
import { MindMapFlowCanvas } from "./MindMapFlowCanvas";
import { MindMapActionMenuButton, MindMapToolbar } from "./MindMapToolbar";
import { MindMapViewerDetails } from "./MindMapViewerDetails";
import type { FocusNodePayload, MindMapViewerProps, MindmapMapType, MindmapNode, MindmapPayload } from "./types";
import { clampMindmapDepth, computeDepths, drawPngFromLayout, focusedBranchIds, isDescendant, parseCanvasState, storageKey, type CanvasState, type MindNodeData } from "./utils";
import { computeInitialCollapsedFromPayload, computeNotebookLayout, toMindmapPayload } from "./viewerHelpers";
import { payloadSupportsMapType } from "./viewerGraph";
import { collectAvailableMindmapTypes, detectMindmapMapType } from "./presentation";
import { buildBranchColorIndexMap, buildChildrenByParent, buildNodeOrder, buildParentCount, resolveRootId, toFocusPayload } from "./viewerDerive";
import { buildFlowEdges, buildFlowNodes, buildReasoningOverlayEdges } from "./viewerElements";
import { normalizeMindmapPayloadForViewer } from "./viewerNormalize";
import { downloadMindmapJson, downloadMindmapMarkdown, downloadMindmapMarkdownText } from "./exporters";
import { MindMapEmptyState } from "./MindMapEmptyState";

const DETAILS_AUTO_COLLAPSE_MS = 12000;
const TOOLBAR_AUTO_HIDE_MS = 7000;

function readStringCandidate(value: unknown): string | null {
  const normalized = String(value || "").trim();
  return normalized || null;
}

function readSourceIdFromPayload(payload: MindmapPayload | null): string | null {
  if (!payload) {
    return null;
  }
  const settingsSourceId = readStringCandidate(
    (payload.settings as Record<string, unknown> | undefined)?.sourceId ||
      (payload.settings as Record<string, unknown> | undefined)?.source_id,
  );
  if (settingsSourceId) {
    return settingsSourceId;
  }
  const graphSourceId = readStringCandidate(
    (payload.graph as Record<string, unknown> | undefined)?.sourceId ||
      (payload.graph as Record<string, unknown> | undefined)?.source_id,
  );
  if (graphSourceId) {
    return graphSourceId;
  }
  const rootId = readStringCandidate(payload.root_id);
  if (rootId && Array.isArray(payload.nodes)) {
    const rootNode = payload.nodes.find((node) => String(node?.id || "").trim() === rootId) || null;
    const rootSourceId = readStringCandidate(rootNode?.source_id);
    if (rootSourceId) {
      return rootSourceId;
    }
  }
  if (Array.isArray(payload.nodes)) {
    for (const node of payload.nodes) {
      const sourceId = readStringCandidate(node?.source_id);
      if (sourceId) {
        return sourceId;
      }
    }
  }
  return null;
}

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
  const [isDetailsCollapsed, setIsDetailsCollapsed] = useState(false);
  const [isToolbarHidden, setIsToolbarHidden] = useState(false);
  const [fitRequestSeq, setFitRequestSeq] = useState(0);
  const [remotePayloadByType, setRemotePayloadByType] = useState<Partial<Record<MindmapMapType, MindmapPayload>>>({});
  const flowRef = useRef<ReactFlowInstance<Node<MindNodeData>, Edge> | null>(null);
  const detailsCollapseTimerRef = useRef<number | null>(null);
  const toolbarHideTimerRef = useRef<number | null>(null);
  const fitTimerRef = useRef<number | null>(null);

  const clearDetailsCollapseTimer = useCallback(() => {
    if (detailsCollapseTimerRef.current !== null) {
      window.clearTimeout(detailsCollapseTimerRef.current);
      detailsCollapseTimerRef.current = null;
    }
  }, []);

  const scheduleDetailsCollapseTimer = useCallback(() => {
    clearDetailsCollapseTimer();
    detailsCollapseTimerRef.current = window.setTimeout(() => {
      setIsDetailsCollapsed(true);
    }, DETAILS_AUTO_COLLAPSE_MS);
  }, [clearDetailsCollapseTimer]);
  const clearToolbarHideTimer = useCallback(() => {
    if (toolbarHideTimerRef.current !== null) {
      window.clearTimeout(toolbarHideTimerRef.current);
      toolbarHideTimerRef.current = null;
    }
  }, []);
  const scheduleToolbarHideTimer = useCallback(() => {
    clearToolbarHideTimer();
    toolbarHideTimerRef.current = window.setTimeout(() => {
      setIsToolbarHidden(true);
    }, TOOLBAR_AUTO_HIDE_MS);
  }, [clearToolbarHideTimer]);
  const revealToolbar = useCallback(() => {
    if (isToolbarHidden) {
      setIsToolbarHidden(false);
    }
  }, [isToolbarHidden]);
  const requestFit = useCallback(() => {
    setFitRequestSeq((previous) => previous + 1);
  }, []);
  useEffect(() => {
    setActiveMapType(detectedBaseMapType);
  }, [basePayload, detectedBaseMapType]);
  const payload = useMemo(() => {
    if (!basePayload) {
      return null;
    }
    const remotePayload = remotePayloadByType[activeMapType];
    if (remotePayload) {
      return remotePayload;
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
  }, [activeMapType, basePayload, detectedBaseMapType, remotePayloadByType]);
  const sourceId = useMemo(() => readSourceIdFromPayload(payload || basePayload), [basePayload, payload]);
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
    setIsDetailsCollapsed(false);
    setIsToolbarHidden(false);
    setRemotePayloadByType({});
    requestFit();
  }, [basePayload, conversationId, detectedBaseMapType, maxDepth, requestFit, viewerPayload]);
  useEffect(() => {
    if (!sourceId || !basePayload) {
      return;
    }
    if (remotePayloadByType[activeMapType]) {
      return;
    }
    const hasLocalVariant =
      activeMapType === detectedBaseMapType ||
      Boolean(basePayload.variants && typeof basePayload.variants === "object" && basePayload.variants[activeMapType]);
    if (hasLocalVariant) {
      return;
    }
    let cancelled = false;
    void getMindmapBySource({
      sourceId,
      mapType: activeMapType === "context_mindmap" ? "structure" : activeMapType,
      maxDepth: viewerMaxDepth,
      includeReasoningMap: showReasoningMap,
    })
      .then((nextPayload) => {
        if (cancelled) {
          return;
        }
        const normalized = toMindmapPayload(nextPayload as Record<string, unknown>);
        if (!normalized) {
          return;
        }
        setRemotePayloadByType((previous) => ({
          ...previous,
          [activeMapType]: normalized,
        }));
      })
      .catch(() => {
        // Keep existing map when source-based fetch is unavailable.
      });
    return () => {
      cancelled = true;
    };
  }, [
    activeMapType,
    basePayload,
    detectedBaseMapType,
    remotePayloadByType,
    showReasoningMap,
    sourceId,
    viewerMaxDepth,
  ]);
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
    flowRef.current?.fitView({
      padding: 0.16,
      maxZoom: 1.06,
      minZoom: 0.18,
      duration: 320,
      ease: (t: number) => 1 - Math.pow(1 - t, 3),
    });
  }, []);
  const handleFlowInit = useCallback((instance: ReactFlowInstance<Node<MindNodeData>, Edge>) => {
    flowRef.current = instance;
    requestFit();
  }, [requestFit]);
  const handleExpand = useCallback(() => {
    setCollapsedNodeIds([]);
    scheduleToolbarHideTimer();
    requestFit();
  }, [requestFit, scheduleToolbarHideTimer]);
  const handleCollapse = useCallback(() => {
    setCollapsedNodeIds(computeInitialCollapsedFromPayload(viewerPayload, viewerMaxDepth));
    scheduleToolbarHideTimer();
    requestFit();
  }, [requestFit, scheduleToolbarHideTimer, viewerPayload, viewerMaxDepth]);
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
    scheduleToolbarHideTimer();
    requestFit();
  }, [childrenByParent, depthMap, requestFit, scheduleToolbarHideTimer, viewerMaxDepth]);
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
      const variantExists =
        mapType === detectedBaseMapType ||
        Boolean(basePayload?.variants && typeof basePayload.variants === "object" && basePayload.variants[mapType]);
      if (!variantExists && sourceId && !remotePayloadByType[mapType]) {
        void getMindmapBySource({
          sourceId,
          mapType: mapType === "context_mindmap" ? "structure" : mapType,
          maxDepth: viewerMaxDepth,
          includeReasoningMap: false,
        })
          .then((nextPayload) => {
            const normalized = toMindmapPayload(nextPayload as Record<string, unknown>);
            if (!normalized) {
              return;
            }
            setRemotePayloadByType((previous) => ({
              ...previous,
              [mapType]: normalized,
            }));
          })
          .catch(() => {
            // Silent fallback to existing payload.
          });
      }
      onMapTypeChange?.(mapType);
      scheduleToolbarHideTimer();
      requestFit();
    },
    [
      basePayload,
      detectedBaseMapType,
      onMapTypeChange,
      remotePayloadByType,
      requestFit,
      scheduleToolbarHideTimer,
      sourceId,
      viewerMaxDepth,
    ],
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
    const localExport = () =>
      downloadMindmapMarkdown({
        payload,
        activeMapType,
        nodeById,
        childrenByParent,
        rootId,
      });

    if (!sourceId) {
      localExport();
      return;
    }

    void exportMindmapMarkdownApi({
      sourceId,
      mapType: activeMapType === "context_mindmap" ? "structure" : activeMapType,
      maxDepth: viewerMaxDepth,
      includeReasoningMap: showReasoningMap,
    })
      .then((markdown) => {
        if (!String(markdown || "").trim()) {
          localExport();
          return;
        }
        downloadMindmapMarkdownText(markdown, activeMapType);
      })
      .catch(() => {
        localExport();
      });
  }, [
    activeMapType,
    childrenByParent,
    nodeById,
    payload,
    rootId,
    showReasoningMap,
    sourceId,
    viewerMaxDepth,
  ]);
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
    if (fitTimerRef.current !== null) {
      window.clearTimeout(fitTimerRef.current);
      fitTimerRef.current = null;
    }
    fitTimerRef.current = window.setTimeout(() => {
      fitView();
      fitTimerRef.current = null;
    }, 72);
    return () => {
      if (fitTimerRef.current !== null) {
        window.clearTimeout(fitTimerRef.current);
        fitTimerRef.current = null;
      }
    };
  }, [fitRequestSeq, fitView, flowEdges.length, flowNodes.length]);
  const availableMapTypes = useMemo(() => collectAvailableMindmapTypes(basePayload), [basePayload]);
  const selectedNode = useMemo(
    () => (selectedNodeId ? parsedNodes.find((node) => node.id === selectedNodeId) || null : null),
    [parsedNodes, selectedNodeId],
  );
  const selectedChildNodes = useMemo(() => {
    if (!selectedNode || !Array.isArray(selectedNode.children) || !selectedNode.children.length) {
      return [];
    }
    return selectedNode.children
      .map((childId) => nodeById.get(String(childId || "").trim()) || null)
      .filter((node): node is MindmapNode => Boolean(node));
  }, [nodeById, selectedNode]);
  const handleNodeClick: NodeMouseHandler<Node<MindNodeData>> = (_event, node) => {
    const focusPayload = resolveNodePayload(node.id);
    if (focusPayload && onFocusNode) onFocusNode(focusPayload);
    setIsDetailsCollapsed(false);
    scheduleDetailsCollapseTimer();
    scheduleToolbarHideTimer();
    setSelectedNodeId(node.id);
  };
  const handleSelectNode = useCallback((nodeId: string) => {
    setSelectedNodeId(nodeId);
    setIsDetailsCollapsed(false);
    scheduleDetailsCollapseTimer();
    scheduleToolbarHideTimer();
    const focusPayload = resolveNodePayload(nodeId);
    if (focusPayload && onFocusNode) {
      onFocusNode(focusPayload);
    }
  }, [onFocusNode, resolveNodePayload, scheduleDetailsCollapseTimer, scheduleToolbarHideTimer]);
  const handleAskSelectedNode = useCallback((focusPayload: FocusNodePayload) => {
    setSelectedNodeId(focusPayload.nodeId);
    onAskNode?.(focusPayload);
  }, [onAskNode]);
  const handleFocusBranch = useCallback((nodeId: string | null) => {
    if (!nodeId) {
      setFocusNodeId(null);
      scheduleToolbarHideTimer();
      requestFit();
      return;
    }
    setFocusNodeId((previous) => (previous === nodeId ? null : nodeId));
    setSelectedNodeId(nodeId);
    scheduleToolbarHideTimer();
    requestFit();
  }, [requestFit, scheduleToolbarHideTimer]);
  const handleClearFocus = useCallback(() => {
    setFocusNodeId(null);
    scheduleToolbarHideTimer();
    requestFit();
  }, [requestFit, scheduleToolbarHideTimer]);
  const handleHideDetailsCard = useCallback(() => {
    clearDetailsCollapseTimer();
    setIsDetailsCollapsed(true);
  }, [clearDetailsCollapseTimer]);
  const handleShowDetailsCard = useCallback(() => {
    setIsDetailsCollapsed(false);
    scheduleDetailsCollapseTimer();
  }, [scheduleDetailsCollapseTimer]);
  const handleDetailsCardActivity = useCallback(() => {
    if (isDetailsCollapsed) {
      return;
    }
    scheduleDetailsCollapseTimer();
  }, [isDetailsCollapsed, scheduleDetailsCollapseTimer]);

  useEffect(() => {
    if (isDetailsCollapsed) {
      clearDetailsCollapseTimer();
      return;
    }
    scheduleDetailsCollapseTimer();
    return clearDetailsCollapseTimer;
  }, [clearDetailsCollapseTimer, isDetailsCollapsed, scheduleDetailsCollapseTimer, selectedNodeId]);

  useEffect(() => () => clearDetailsCollapseTimer(), [clearDetailsCollapseTimer]);
  useEffect(() => () => clearToolbarHideTimer(), [clearToolbarHideTimer]);
  useEffect(() => {
    requestFit();
  }, [effectiveViewerHeight, requestFit]);
  useEffect(
    () => () => {
      if (fitTimerRef.current !== null) {
        window.clearTimeout(fitTimerRef.current);
      }
    },
    [],
  );
  const handleViewerMaxDepthChange = useCallback(
    (depth: number) => {
      setViewerMaxDepth(clampMindmapDepth(depth));
      scheduleToolbarHideTimer();
      requestFit();
    },
    [requestFit, scheduleToolbarHideTimer],
  );
  const handleCanvasMouseMove = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      if (!isToolbarHidden) {
        return;
      }
      const rect = event.currentTarget.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      if (x <= 460 && y <= 120) {
        revealToolbar();
        scheduleToolbarHideTimer();
      }
    },
    [isToolbarHidden, revealToolbar, scheduleToolbarHideTimer],
  );
  const handleCanvasInteraction = useCallback(() => {
    scheduleToolbarHideTimer();
  }, [scheduleToolbarHideTimer]);
  if (!payload || !parsedNodes.length) {
    return <MindMapEmptyState />;
  }
  return (
    <div
      className="relative overflow-hidden rounded-[24px] bg-[#eef2f7]"
      style={{ height: `${effectiveViewerHeight}px` }}
      onMouseMove={handleCanvasMouseMove}
    >
          <div
            className={`pointer-events-none absolute inset-x-3 top-4 z-40 flex justify-start transition-opacity duration-200 md:inset-x-4 md:top-4 ${
              isToolbarHidden ? "opacity-0" : "opacity-100"
            }`}
          >
            <div
              className={`pointer-events-auto transition-transform duration-200 ${
                isToolbarHidden ? "-translate-y-1" : "translate-y-0"
              }`}
              onMouseEnter={() => {
                revealToolbar();
                clearToolbarHideTimer();
              }}
              onMouseLeave={() => {
                scheduleToolbarHideTimer();
              }}
            >
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
                onMaxDepthChange={handleViewerMaxDepthChange}
                onToggleReasoningMap={() => setShowReasoningMap((previous) => !previous)}
                onClearFocus={handleClearFocus}
                onExportPng={handleExportPng}
                onExportJson={handleExportJson}
                onExportMarkdown={handleExportMarkdown}
                onSave={handleSave}
                onShare={handleShare}
              />
            </div>
          </div>

          <div className="pointer-events-none absolute right-3 top-4 z-40 md:right-4 md:top-4">
            <div className="pointer-events-auto">
              <MindMapActionMenuButton
                onExportPng={handleExportPng}
                onExportJson={handleExportJson}
                onExportMarkdown={handleExportMarkdown}
                onSave={handleSave}
                onShare={handleShare}
              />
            </div>
          </div>

          <MindMapFlowCanvas
            height={effectiveViewerHeight}
            nodes={flowNodes}
            edges={flowEdges}
            onInit={handleFlowInit}
            onNodeClick={handleNodeClick}
            onCanvasInteraction={handleCanvasInteraction}
          />

          {isDetailsCollapsed ? (
            <div className="pointer-events-none absolute right-3 top-[3.25rem] z-30 hidden md:right-4 lg:block">
              <button
                type="button"
                onClick={handleShowDetailsCard}
                className="pointer-events-auto inline-flex h-9 w-9 items-center justify-center rounded-full border border-transparent bg-transparent text-[#5b6473] shadow-none transition-colors hover:bg-black/[0.06] hover:text-[#17171b]"
                title="Show details"
              >
                <Info className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <div className="pointer-events-none absolute inset-y-0 right-5 z-20 hidden items-center lg:flex">
              <div
                className="pointer-events-auto h-[400px] max-h-[calc(100%-5rem)] w-[360px] rounded-[20px]"
                onMouseMove={handleDetailsCardActivity}
                onMouseDown={handleDetailsCardActivity}
                onWheel={handleDetailsCardActivity}
                onTouchStart={handleDetailsCardActivity}
                onKeyDown={handleDetailsCardActivity}
              >
                <MindMapViewerDetails
                  activeMapType={activeMapType}
                  selectedNode={selectedNode}
                  childNodes={selectedChildNodes}
                  onFocusBranch={handleFocusBranch}
                  isFocusActive={Boolean(selectedNode && focusNodeId === selectedNode.id)}
                  onAskNode={onAskNode ? handleAskSelectedNode : undefined}
                  onClose={handleHideDetailsCard}
                  canvasMode
                />
              </div>
            </div>
          )}

          <div className="pointer-events-none absolute inset-x-3 bottom-3 z-20 lg:hidden">
            <div className="pointer-events-auto">
              <MindMapViewerDetails
                activeMapType={activeMapType}
                selectedNode={selectedNode}
                childNodes={selectedChildNodes}
                onFocusBranch={handleFocusBranch}
                isFocusActive={Boolean(selectedNode && focusNodeId === selectedNode.id)}
                onAskNode={onAskNode ? handleAskSelectedNode : undefined}
                canvasMode
              />
            </div>
          </div>
    </div>
  );
}
