import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Download, Maximize2, Minimize2, RotateCcw, Share2 } from "lucide-react";
import {
  computeDepths,
  drawPngFromLayout,
  isDescendant,
  parseCanvasState,
  storageKey,
  type MindNodeData,
} from "./mindmapViewer/utils";

type MindmapNode = {
  id: string;
  title: string;
  text?: string;
  node_type?: string;
  page_ref?: string | null;
  source_id?: string;
  source_name?: string;
  children?: string[];
  thumbnail?: string | null;
};

type MindmapEdge = {
  id?: string;
  source: string;
  target: string;
  type?: string;
};

type ReasoningNode = {
  id: string;
  label: string;
  kind?: string;
  node_id?: string;
};

type ReasoningEdge = {
  id?: string;
  source: string;
  target: string;
};

type MindmapPayload = {
  version?: number;
  kind?: string;
  title?: string;
  root_id?: string;
  nodes?: MindmapNode[];
  edges?: MindmapEdge[];
  reasoning_map?: {
    layout?: string;
    nodes?: ReasoningNode[];
    edges?: ReasoningEdge[];
  };
  settings?: Record<string, unknown>;
};

type FocusNodePayload = {
  nodeId: string;
  title: string;
  text: string;
  pageRef?: string;
  sourceId?: string;
  sourceName?: string;
};

type MindmapViewerProps = {
  payload?: Record<string, unknown> | null;
  conversationId?: string | null;
  maxDepth?: number;
  onAskNode?: (payload: FocusNodePayload) => void;
  onSaveMap?: (payload: MindmapPayload) => void;
  onShareMap?: (payload: MindmapPayload) => Promise<string | void> | string | void;
};

function toMindmapPayload(raw: Record<string, unknown> | null | undefined): MindmapPayload | null {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  return raw as MindmapPayload;
}

function MindNode({ id, data }: NodeProps<MindNodeData>) {
  return (
    <div className="rounded-xl border border-black/[0.08] bg-white px-3 py-2 shadow-[0_12px_24px_-24px_rgba(0,0,0,0.55)] min-w-[150px] max-w-[260px]">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[12px] text-[#1d1d1f] truncate" title={data.title}>
            {data.title}
          </p>
          {data.subtitle ? (
            <p className="text-[10px] text-[#6e6e73] truncate" title={data.subtitle}>
              {data.subtitle}
            </p>
          ) : null}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {data.onAsk ? (
            <button
              type="button"
              onClick={() => data.onAsk?.(id)}
              className="h-5 px-1.5 rounded-md border border-black/[0.08] text-[9px] text-[#1d1d1f] hover:bg-[#f5f5f7]"
            >
              Ask
            </button>
          ) : null}
          {data.hasChildren ? (
            <button
              type="button"
              onClick={() => data.onToggle(id)}
              className="h-5 w-5 rounded-md border border-black/[0.08] text-[10px] text-[#1d1d1f] hover:bg-[#f5f5f7]"
            >
              {data.collapsed ? "+" : "-"}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

const nodeTypes = { mind: MindNode };

export function MindmapViewer({
  payload: rawPayload,
  conversationId = null,
  maxDepth = 4,
  onAskNode,
  onSaveMap,
  onShareMap,
}: MindmapViewerProps) {
  const payload = useMemo(() => toMindmapPayload(rawPayload), [rawPayload]);
  const [collapsedNodeIds, setCollapsedNodeIds] = useState<string[]>([]);
  const [showReasoningMap, setShowReasoningMap] = useState(false);
  const [layoutMode, setLayoutMode] = useState<"vertical" | "horizontal">("vertical");
  const [nodePositions, setNodePositions] = useState<Record<string, { x: number; y: number }>>({});
  const flowRef = useRef<ReactFlowInstance<Node<MindNodeData>, Edge> | null>(null);
  const reasoningFlowRef = useRef<ReactFlowInstance | null>(null);

  useEffect(() => {
    const key = storageKey(payload, conversationId);
    const saved = parseCanvasState(window.localStorage.getItem(key));
    if (!saved) {
      setCollapsedNodeIds([]);
      setShowReasoningMap(false);
      setLayoutMode("vertical");
      setNodePositions({});
      return;
    }
    setCollapsedNodeIds(saved.collapsedNodeIds);
    setShowReasoningMap(saved.showReasoningMap);
    setLayoutMode(saved.layoutMode);
    setNodePositions(saved.nodePositions);
  }, [conversationId, payload]);

  useEffect(() => {
    const key = storageKey(payload, conversationId);
    const state: CanvasState = {
      collapsedNodeIds,
      showReasoningMap,
      layoutMode,
      nodePositions,
    };
    window.localStorage.setItem(key, JSON.stringify(state));
  }, [collapsedNodeIds, conversationId, layoutMode, nodePositions, payload, showReasoningMap]);

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

  const flowNodes = useMemo(() => {
    const hiddenIds = new Set<string>();
    for (const collapsedId of collapsedNodeIds) {
      for (const node of parsedNodes) {
        if (isDescendant(node.id, collapsedId, childrenByParent)) {
          hiddenIds.add(node.id);
        }
      }
    }
    const visibleNodes = parsedNodes.filter((node) => !hiddenIds.has(node.id));
    const byDepth = new Map<number, MindmapNode[]>();
    for (const node of visibleNodes) {
      const depth = depthMap[node.id] ?? 1;
      if (depth > maxDepth) {
        continue;
      }
      const rows = byDepth.get(depth) || [];
      rows.push(node);
      byDepth.set(depth, rows);
    }
    const reactNodes: Node<MindNodeData>[] = [];
    for (const [depth, rows] of byDepth.entries()) {
      rows.forEach((node, index) => {
        const defaultPos =
          layoutMode === "horizontal"
            ? { x: depth * 280, y: index * 84 }
            : { x: index * 260, y: depth * 90 };
        reactNodes.push({
          id: node.id,
          type: "mind",
          draggable: true,
          position: nodePositions[node.id] || defaultPos,
          data: {
            title: node.title || node.id,
            subtitle: node.page_ref ? `page ${node.page_ref}` : node.node_type || "",
            hasChildren: (node.children || childrenByParent.get(node.id) || []).length > 0,
            collapsed: collapsedNodeIds.includes(node.id),
            onToggle: (nodeId) =>
              setCollapsedNodeIds((prev) =>
                prev.includes(nodeId) ? prev.filter((row) => row !== nodeId) : [...prev, nodeId],
              ),
            onAsk: onAskNode
              ? (nodeId) => {
                  const selected = parsedNodes.find((row) => row.id === nodeId);
                  if (!selected) {
                    return;
                  }
                  onAskNode({
                    nodeId: selected.id,
                    title: selected.title || "",
                    text: selected.text || "",
                    pageRef: selected.page_ref || undefined,
                    sourceId: selected.source_id,
                    sourceName: selected.source_name,
                  });
                }
              : undefined,
          },
        });
      });
    }
    return reactNodes;
  }, [
    childrenByParent,
    collapsedNodeIds,
    depthMap,
    layoutMode,
    maxDepth,
    nodePositions,
    onAskNode,
    parsedNodes,
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
            style: {
              stroke: edge.type === "reference" || edge.type === "hyperlink" ? "#9aa0a6" : "#d2d2d7",
              strokeDasharray: edge.type === "reference" || edge.type === "hyperlink" ? "4 3" : undefined,
            },
          }),
        ),
    [parsedEdges, visibleIds],
  );

  const reasoningNodes = useMemo(() => {
    const rows = payload?.reasoning_map?.nodes || [];
    return rows.map(
      (row, idx): Node => ({
        id: row.id || `r-${idx}`,
        position: { x: idx * 240, y: 40 },
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

  if (!payload || !parsedNodes.length) {
    return (
      <div className="rounded-xl border border-black/[0.08] bg-white p-4 text-[12px] text-[#6e6e73]">
        Mind-map is not available for this answer.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-black/[0.08] bg-white p-3 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[12px] font-medium text-[#1d1d1f] truncate">{payload.title || "Mind-map"}</p>
          <p className="text-[10px] text-[#6e6e73] uppercase">{payload.kind || "tree"}</p>
        </div>
        <div className="flex items-center gap-1.5">
          <button type="button" onClick={() => setCollapsedNodeIds([])} className="h-7 px-2 rounded-lg border border-black/[0.08] text-[11px] hover:bg-[#f5f5f7]">Expand</button>
          <button type="button" onClick={() => setCollapsedNodeIds(flowNodes.map((node) => node.id))} className="h-7 px-2 rounded-lg border border-black/[0.08] text-[11px] hover:bg-[#f5f5f7]">Collapse</button>
          <button type="button" onClick={() => setLayoutMode((prev) => (prev === "vertical" ? "horizontal" : "vertical"))} className="h-7 px-2 rounded-lg border border-black/[0.08] text-[11px] hover:bg-[#f5f5f7]">{layoutMode === "vertical" ? "Horizontal" : "Vertical"}</button>
          <button type="button" onClick={() => flowRef.current?.fitView({ duration: 200 })} className="h-7 w-7 rounded-lg border border-black/[0.08] text-[#1d1d1f] hover:bg-[#f5f5f7]"><Maximize2 className="w-3.5 h-3.5 mx-auto" /></button>
          <button type="button" onClick={() => setNodePositions({})} className="h-7 w-7 rounded-lg border border-black/[0.08] text-[#1d1d1f] hover:bg-[#f5f5f7]"><RotateCcw className="w-3.5 h-3.5 mx-auto" /></button>
          <button type="button" onClick={() => drawPngFromLayout(flowNodes, flowEdges, String(payload.title || "mindmap"))} className="h-7 w-7 rounded-lg border border-black/[0.08] text-[#1d1d1f] hover:bg-[#f5f5f7]"><Download className="w-3.5 h-3.5 mx-auto" /></button>
          <button type="button" onClick={handleDownloadJson} className="h-7 px-2 rounded-lg border border-black/[0.08] text-[11px] hover:bg-[#f5f5f7]">JSON</button>
          <button type="button" onClick={() => onSaveMap?.(payload)} className="h-7 px-2 rounded-lg border border-black/[0.08] text-[11px] hover:bg-[#f5f5f7]">Save</button>
          <button
            type="button"
            onClick={async () => {
              const shared = await onShareMap?.(payload);
              if (typeof shared === "string" && shared.trim()) {
                await navigator.clipboard.writeText(shared);
              } else {
                await navigator.clipboard.writeText(JSON.stringify(payload));
              }
            }}
            className="h-7 w-7 rounded-lg border border-black/[0.08] text-[#1d1d1f] hover:bg-[#f5f5f7]"
          >
            <Share2 className="w-3.5 h-3.5 mx-auto" />
          </button>
        </div>
      </div>
      <div className="h-[360px] w-full rounded-lg border border-black/[0.06] overflow-hidden bg-[#fafafc]">
        <ReactFlow
          nodeTypes={nodeTypes}
          nodes={flowNodes}
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
          <Background color="#ececf0" gap={18} />
          <MiniMap pannable zoomable />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      {payload.reasoning_map?.nodes?.length ? (
        <div className="space-y-2">
          <button
            type="button"
            onClick={() => setShowReasoningMap((prev) => !prev)}
            className="inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1.5 rounded-lg border border-black/[0.08] text-[#1d1d1f] hover:bg-[#f5f5f7]"
          >
            {showReasoningMap ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
            {showReasoningMap ? "Hide reasoning map" : "Show reasoning map"}
          </button>
          {showReasoningMap ? (
            <div className="h-[220px] w-full rounded-lg border border-black/[0.06] overflow-hidden bg-[#fafafc]">
              <ReactFlow
                nodes={reasoningNodes}
                edges={reasoningEdges}
                onInit={(instance) => {
                  reasoningFlowRef.current = instance;
                  window.setTimeout(() => instance.fitView({ duration: 180, padding: 0.12 }), 60);
                }}
                fitView
              >
                <Background color="#ececf0" gap={18} />
                <Controls showInteractive={false} />
              </ReactFlow>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
