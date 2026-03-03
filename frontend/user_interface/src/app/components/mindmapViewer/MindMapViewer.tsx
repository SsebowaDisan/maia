import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Maximize2, Minimize2 } from "lucide-react";

import { MindMapToolbar } from "./MindMapToolbar";
import { MindNodeCard } from "./MindNodeCard";
import type { MindMapViewerProps, MindmapPayload } from "./types";
import {
  computeBalancedLayout,
  computeDepths,
  drawPngFromLayout,
  focusedBranchIds,
  isDescendant,
  mapPayloadToMarkdown,
  parseCanvasState,
  storageKey,
  type CanvasState,
  type MindNodeData,
} from "./utils";

const nodeTypes = { mind: MindNodeCard };

function toMindmapPayload(raw: Record<string, unknown> | null | undefined): MindmapPayload | null {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  return raw as MindmapPayload;
}

export function MindMapViewer({
  payload: rawPayload,
  conversationId = null,
  maxDepth = 4,
  onAskNode,
  onSaveMap,
  onShareMap,
  onMapTypeChange,
}: MindMapViewerProps) {
  const basePayload = useMemo(() => toMindmapPayload(rawPayload), [rawPayload]);
  const [collapsedNodeIds, setCollapsedNodeIds] = useState<string[]>([]);
  const [showReasoningMap, setShowReasoningMap] = useState(false);
  const [layoutMode, setLayoutMode] = useState<"balanced" | "horizontal">("balanced");
  const [nodePositions, setNodePositions] = useState<Record<string, { x: number; y: number }>>({});
  const [activeMapType, setActiveMapType] = useState<"structure" | "evidence">("structure");
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);
  const flowRef = useRef<ReactFlowInstance<Node<MindNodeData>, Edge> | null>(null);
  const reasoningFlowRef = useRef<ReactFlowInstance | null>(null);

  useEffect(() => {
    const detected = basePayload?.map_type === "evidence" ? "evidence" : "structure";
    setActiveMapType(detected);
  }, [basePayload]);

  const payload = useMemo(() => {
    if (!basePayload) {
      return null;
    }
    const detected = basePayload.map_type === "evidence" ? "evidence" : "structure";
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
      setCollapsedNodeIds([]);
      setShowReasoningMap(false);
      setLayoutMode("balanced");
      setNodePositions({});
      setFocusedNodeId(null);
      return;
    }
    setCollapsedNodeIds(saved.collapsedNodeIds);
    setShowReasoningMap(saved.showReasoningMap);
    setLayoutMode(saved.layoutMode);
    setNodePositions(saved.nodePositions);
    setActiveMapType(saved.activeMapType);
    setFocusedNodeId(saved.focusedNodeId);
  }, [conversationId, payload]);

  useEffect(() => {
    const key = storageKey(payload, conversationId);
    const state: CanvasState = {
      collapsedNodeIds,
      showReasoningMap,
      layoutMode,
      nodePositions,
      activeMapType,
      focusedNodeId,
    };
    window.localStorage.setItem(key, JSON.stringify(state));
  }, [
    activeMapType,
    collapsedNodeIds,
    conversationId,
    focusedNodeId,
    layoutMode,
    nodePositions,
    payload,
    showReasoningMap,
  ]);

  const parsedNodes = useMemo(() => payload?.nodes || [], [payload]);
  const parsedEdges = useMemo(() => payload?.edges || [], [payload]);
  const rootId = useMemo(
    () => String(payload?.root_id || parsedNodes[0]?.id || ""),
    [payload, parsedNodes],
  );

  const childrenByParent = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const edge of parsedEdges) {
      if (edge.type && edge.type !== "hierarchy") {
        continue;
      }
      const rows = map.get(edge.source) || [];
      rows.push(edge.target);
      map.set(edge.source, rows);
    }
    return map;
  }, [parsedEdges]);
  const depthMap = useMemo(() => computeDepths(rootId, parsedEdges), [parsedEdges, rootId]);
  const focusSet = useMemo(
    () => (focusedNodeId ? focusedBranchIds(focusedNodeId, parsedEdges) : null),
    [focusedNodeId, parsedEdges],
  );

  const flowNodes = useMemo(() => {
    const hiddenIds = new Set<string>();
    for (const collapsedId of collapsedNodeIds) {
      for (const node of parsedNodes) {
        if (isDescendant(node.id, collapsedId, childrenByParent)) {
          hiddenIds.add(node.id);
        }
      }
    }

    const layout = computeBalancedLayout({
      rootId,
      nodes: parsedNodes.map((node) => ({ id: node.id })),
      edges: parsedEdges,
      collapsedNodeIds,
      maxDepth,
      centerX: 0,
      centerY: 0,
      depthGap: 240,
      leafGap: 120,
    });

    return parsedNodes
      .filter((node) => !hiddenIds.has(node.id))
      .filter((node) => (depthMap[node.id] ?? 0) <= maxDepth)
      .map((node, index) => {
        const depth = depthMap[node.id] ?? 1;
        const fallback = layout[node.id] || { x: depth * 220, y: index * 92 };
        const opacity = focusSet ? (focusSet.has(node.id) ? 1 : 0.22) : 1;
        return {
          id: node.id,
          type: "mind",
          draggable: true,
          position: nodePositions[node.id] || fallback,
          style: {
            opacity,
            transition: "opacity 200ms ease-in-out",
          },
          data: {
            title: node.title || node.id,
            subtitle: node.page_ref
              ? `page ${node.page_ref}`
              : node.page
                ? `page ${node.page}`
                : node.node_type || node.type || "",
            hasChildren: (node.children || childrenByParent.get(node.id) || []).length > 0,
            collapsed: collapsedNodeIds.includes(node.id),
            nodeType: String(node.type || node.node_type || ""),
            onToggle: (nodeId: string) =>
              setCollapsedNodeIds((prev) =>
                prev.includes(nodeId) ? prev.filter((row) => row !== nodeId) : [...prev, nodeId],
              ),
            onAsk: onAskNode
              ? (nodeId: string) => {
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
                }
              : undefined,
            onFocus: (nodeId: string) =>
              setFocusedNodeId((prev) => (prev === nodeId ? null : nodeId)),
          } satisfies MindNodeData,
        } satisfies Node<MindNodeData>;
      });
  }, [
    childrenByParent,
    collapsedNodeIds,
    depthMap,
    focusSet,
    maxDepth,
    nodePositions,
    onAskNode,
    parsedEdges,
    parsedNodes,
    rootId,
  ]);

  const visibleIds = useMemo(() => new Set(flowNodes.map((node) => node.id)), [flowNodes]);
  const flowEdges = useMemo(
    () =>
      (parsedEdges || [])
        .filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target))
        .map(
          (edge): Edge => ({
            id: edge.id || `${edge.source}->${edge.target}`,
            source: edge.source,
            target: edge.target,
            animated: edge.type === "support",
            style: {
              stroke:
                edge.type === "reference" || edge.type === "hyperlink"
                  ? "#9aa0a6"
                  : edge.type === "support"
                    ? "#4f46e5"
                    : "#d2d2d7",
              strokeDasharray: edge.type === "reference" || edge.type === "hyperlink" ? "4 3" : undefined,
              opacity: focusSet ? (focusSet.has(edge.source) ? 1 : 0.14) : 1,
              transition: "opacity 200ms ease-in-out",
            },
          }),
        ),
    [focusSet, parsedEdges, visibleIds],
  );

  const reasoningNodes = useMemo(() => {
    const rows = payload?.reasoning_map?.nodes || [];
    return rows.map(
      (row, idx): Node => ({
        id: row.id || `r-${idx}`,
        position: { x: idx * 240, y: 42 },
        data: { label: row.label || row.id, kind: row.kind || "step" },
        type: "default",
      }),
    );
  }, [payload]);
  const reasoningEdges = useMemo(
    () =>
      (payload?.reasoning_map?.edges || []).map(
        (row): Edge => ({
          id: row.id || `${row.source}->${row.target}`,
          source: row.source,
          target: row.target,
        }),
      ),
    [payload],
  );

  const handleDownloadJson = useCallback(() => {
    if (!payload) {
      return;
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${String(payload.title || "mindmap").replace(/\s+/g, "_").toLowerCase()}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }, [payload]);
  const handleDownloadMarkdown = useCallback(() => {
    if (!payload) {
      return;
    }
    const markdown = mapPayloadToMarkdown(payload as unknown as Record<string, unknown>);
    const blob = new Blob([markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${String(payload.title || "mindmap").replace(/\s+/g, "_").toLowerCase()}.md`;
    link.click();
    URL.revokeObjectURL(url);
  }, [payload]);

  useEffect(() => {
    if (!focusedNodeId || !flowRef.current) {
      return;
    }
    const focusedNodes = flowNodes.filter((node) => focusSet?.has(node.id));
    if (!focusedNodes.length) {
      return;
    }
    const xs = focusedNodes.map((node) => node.position.x);
    const ys = focusedNodes.map((node) => node.position.y);
    const x = Math.min(...xs) - 80;
    const y = Math.min(...ys) - 80;
    const width = Math.max(200, Math.max(...xs) - Math.min(...xs) + 280);
    const height = Math.max(160, Math.max(...ys) - Math.min(...ys) + 220);
    flowRef.current.fitBounds({ x, y, width, height }, { duration: 200, padding: 0.18 });
  }, [focusSet, focusedNodeId, flowNodes]);

  if (!payload || !parsedNodes.length) {
    return (
      <div className="rounded-xl border border-black/[0.08] bg-white p-4 text-[12px] text-[#6e6e73]">
        Mind-map is not available for this answer.
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-black/[0.08] bg-[#f2f2f7] p-3 space-y-3 shadow-[0_16px_40px_-34px_rgba(0,0,0,0.35)]">
      <MindMapToolbar
        title={payload.title || "Mind-map"}
        mapType={String(payload.map_type || "structure")}
        kind={String(payload.kind || "tree")}
        activeMapType={activeMapType}
        hasVariants={Boolean(basePayload?.variants && typeof basePayload.variants === "object")}
        onSwitchMapType={(mapType) => {
          setActiveMapType(mapType);
          onMapTypeChange?.(mapType);
        }}
        onExpand={() => setCollapsedNodeIds([])}
        onCollapse={() => setCollapsedNodeIds(flowNodes.map((node) => node.id))}
        onToggleLayout={() => setLayoutMode((prev) => (prev === "balanced" ? "horizontal" : "balanced"))}
        layoutMode={layoutMode}
        onResetFocus={() => {
          setFocusedNodeId(null);
          flowRef.current?.fitView({ duration: 200, padding: 0.12 });
        }}
        onAutoTidy={() => setNodePositions({})}
        onFitView={() => flowRef.current?.fitView({ duration: 200, padding: 0.12 })}
        onExportPng={() => drawPngFromLayout(flowNodes, flowEdges, String(payload.title || "mindmap"))}
        onExportJson={handleDownloadJson}
        onExportMarkdown={handleDownloadMarkdown}
        onSave={() => onSaveMap?.(payload)}
        onShare={async () => {
          const shared = await onShareMap?.(payload);
          if (typeof shared === "string" && shared.trim()) {
            await navigator.clipboard.writeText(shared);
          } else {
            await navigator.clipboard.writeText(JSON.stringify(payload));
          }
        }}
      />
      <div className="h-[420px] w-full rounded-2xl border border-black/[0.06] overflow-hidden bg-[#fafafc]">
        <ReactFlow
          nodeTypes={nodeTypes}
          nodes={
            layoutMode === "horizontal"
              ? flowNodes.map((node, index) => {
                  const depth = depthMap[node.id] ?? 0;
                  return {
                    ...node,
                    position: nodePositions[node.id] || { x: depth * 260, y: index * 96 },
                  };
                })
              : flowNodes
          }
          edges={flowEdges}
          onInit={(instance) => {
            flowRef.current = instance;
            window.setTimeout(() => instance.fitView({ duration: 200, padding: 0.12 }), 60);
          }}
          onNodeDragStop={(_, node) =>
            setNodePositions((prev) => ({ ...prev, [node.id]: { x: node.position.x, y: node.position.y } }))
          }
          fitView
          attributionPosition="bottom-right"
        >
          <Background color="#e3e4e8" gap={22} />
          <MiniMap pannable zoomable />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      {payload.reasoning_map?.nodes?.length ? (
        <div className="space-y-2">
          <button
            type="button"
            onClick={() => setShowReasoningMap((prev) => !prev)}
            className="inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1.5 rounded-full border border-black/[0.08] bg-white text-[#1d1d1f] hover:bg-[#f5f5f7]"
          >
            {showReasoningMap ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
            {showReasoningMap ? "Hide reasoning map" : "Show reasoning map"}
          </button>
          {showReasoningMap ? (
            <div className="h-[240px] w-full rounded-2xl border border-black/[0.06] overflow-hidden bg-[#fafafc]">
              <ReactFlow
                nodes={reasoningNodes}
                edges={reasoningEdges}
                onInit={(instance) => {
                  reasoningFlowRef.current = instance;
                  window.setTimeout(() => instance.fitView({ duration: 180, padding: 0.12 }), 60);
                }}
                fitView
              >
                <Background color="#e3e4e8" gap={20} />
                <Controls showInteractive={false} />
              </ReactFlow>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
