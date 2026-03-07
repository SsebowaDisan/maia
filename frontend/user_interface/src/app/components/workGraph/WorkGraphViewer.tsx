import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import { useShallow } from "zustand/react/shallow";

import "@xyflow/react/dist/style.css";

import { computeWorkGraphLaneLayout, computeWorkGraphLayout } from "./layout";
import { WorkGraphEdgeRenderer } from "./WorkGraphEdge";
import { WorkGraphNodeCard, statusColor, type WorkGraphNodeRenderData } from "./WorkGraphNode";
import { useWorkGraphStore } from "./useWorkGraphStore";
import { WorkGraphToolbar } from "./WorkGraphToolbar";
import { buildWorkGraphJumpTarget, emitWorkGraphJumpTarget } from "./theatreSync";
import { extractNodeRiskReason } from "./evidenceSync";
import type { WorkGraphNode } from "./work_graph_types";
import {
  filterWorkGraphEdges,
  filterWorkGraphNodes,
  hiddenNodeIdsForCollapsed,
  toggleCollapsedNodeIds,
} from "./searchFilters";
import {
  createCollaborationTransport,
  type CollaborationCommentEvent,
  type CollaborationSelectionEvent,
  type CollaborationTransport,
} from "./collaboration";
import { WorkGraphLegend } from "./WorkGraphLegend";
import {
  WorkGraphControlPanel,
  type CollaboratorPresence,
  type NodeComment,
} from "./WorkGraphControlPanel";

type WorkGraphViewerProps = {
  viewerHeight?: number;
  onAskNode?: (payload: {
    nodeId: string;
    title: string;
    text: string;
    pageRef?: string;
    sourceId?: string;
    sourceName?: string;
  }) => void;
  onInspectEvidence?: (payload: {
    nodeId: string;
    title: string;
    evidenceIds: string[];
    sceneRefs: string[];
    eventRefs: string[];
  }) => void;
  onInspectVerifier?: (payload: {
    nodeId: string;
    title: string;
    detail: string;
    status: string;
    confidence: number | null;
    riskReason: string;
    sceneRefs: string[];
    eventRefs: string[];
  }) => void;
};

const nodeTypes = { work: WorkGraphNodeCard };
const edgeTypes = { workEdge: WorkGraphEdgeRenderer };

function createLocalViewerIdentity() {
  if (typeof window === "undefined") {
    return { userId: "viewer-local", userLabel: "You" };
  }
  const storageKey = "maia.work-graph.viewer.identity.v1";
  const existing = String(window.localStorage.getItem(storageKey) || "").trim();
  if (existing) {
    return { userId: existing, userLabel: "You" };
  }
  const created = `viewer-${Math.random().toString(36).slice(2, 10)}`;
  window.localStorage.setItem(storageKey, created);
  return { userId: created, userLabel: "You" };
}

function WorkGraphViewer({ viewerHeight = 520, onAskNode, onInspectEvidence, onInspectVerifier }: WorkGraphViewerProps) {
  const slice = useWorkGraphStore(
    useShallow((state) => ({
      runId: state.runId,
      rootId: state.rootId,
      nodes: state.nodes,
      edges: state.edges,
      activeNodeIds: state.activeNodeIds,
      loading: state.loading,
      streaming: state.streaming,
      selectedNodeId: state.selectedNodeId,
      setSelectedNodeId: state.setSelectedNodeId,
      setReplayCursor: state.setReplayCursor,
    })),
  );
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [roleFilter, setRoleFilter] = useState("all");
  const [confidenceFilter, setConfidenceFilter] = useState<"all" | "low" | "medium_high">("all");
  const [edgeFamilyFilter, setEdgeFamilyFilter] = useState("all");
  const [focusMode, setFocusMode] = useState(false);
  const [collapsedNodeIds, setCollapsedNodeIds] = useState<string[]>([]);
  const [commentDraft, setCommentDraft] = useState("");
  const [presenceByUser, setPresenceByUser] = useState<Record<string, CollaboratorPresence>>({});
  const [commentsByNode, setCommentsByNode] = useState<Record<string, NodeComment[]>>({});
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const identityRef = useRef(createLocalViewerIdentity());
  const collaborationRef = useRef<CollaborationTransport | null>(null);

  const roleOptions = useMemo(() => {
    const roles = slice.nodes
      .map((node) => String(node.agent_role || "system").trim())
      .filter((role) => role.length > 0);
    return Array.from(new Set(roles)).sort((left, right) => left.localeCompare(right));
  }, [slice.nodes]);

  useEffect(() => {
    if (!slice.runId) {
      collaborationRef.current?.dispose();
      collaborationRef.current = null;
      return;
    }
    const transport = createCollaborationTransport({
      provider: "local_broadcast",
      channelId: `work-graph:${slice.runId}`,
    });
    collaborationRef.current = transport;
    const unsubscribe = transport.subscribe((event) => {
      if (event.kind === "selection") {
        const selectionEvent = event as CollaborationSelectionEvent;
        setPresenceByUser((previous) => ({
          ...previous,
          [selectionEvent.userId]: {
            userId: selectionEvent.userId,
            userLabel: selectionEvent.userLabel,
            nodeId: selectionEvent.nodeId,
            timestamp: selectionEvent.timestamp,
          },
        }));
        return;
      }
      if (event.kind === "comment") {
        const commentEvent = event as CollaborationCommentEvent;
        setCommentsByNode((previous) => {
          const currentNodeComments = Array.isArray(previous[commentEvent.nodeId])
            ? previous[commentEvent.nodeId]
            : [];
          const nextNodeComments = [...currentNodeComments, {
            commentId: commentEvent.commentId,
            userId: commentEvent.userId,
            userLabel: commentEvent.userLabel,
            text: commentEvent.text,
            timestamp: commentEvent.timestamp,
          }].slice(-40);
          return {
            ...previous,
            [commentEvent.nodeId]: nextNodeComments,
          };
        });
      }
    });

    return () => {
      unsubscribe();
      transport.dispose();
      if (collaborationRef.current === transport) {
        collaborationRef.current = null;
      }
    };
  }, [slice.runId]);

  const filteredNodes = useMemo(
    () =>
      filterWorkGraphNodes(slice.nodes, {
        query: searchQuery,
        agentRole: roleFilter,
        status: statusFilter,
        confidence: confidenceFilter,
        focusMode,
        edgeFamily: edgeFamilyFilter,
      }),
    [confidenceFilter, edgeFamilyFilter, focusMode, roleFilter, searchQuery, slice.nodes, statusFilter],
  );

  const collapsedHiddenNodeIds = useMemo(
    () => hiddenNodeIdsForCollapsed(filteredNodes, slice.edges, collapsedNodeIds),
    [collapsedNodeIds, filteredNodes, slice.edges],
  );

  const visibleNodes = useMemo(
    () => filteredNodes.filter((node) => !collapsedHiddenNodeIds.has(node.id)),
    [collapsedHiddenNodeIds, filteredNodes],
  );

  const visibleNodeIds = useMemo(() => new Set(visibleNodes.map((node) => node.id)), [visibleNodes]);

  const visibleEdges = useMemo(
    () => filterWorkGraphEdges(slice.edges, visibleNodeIds, edgeFamilyFilter),
    [edgeFamilyFilter, slice.edges, visibleNodeIds],
  );

  const collaboratorPresence = useMemo(() => {
    const cutoff = Date.now() - 5 * 60 * 1000;
    return Object.values(presenceByUser)
      .filter((row) => Date.parse(row.timestamp) >= cutoff)
      .sort((left, right) => Date.parse(right.timestamp) - Date.parse(left.timestamp))
      .slice(0, 8);
  }, [presenceByUser]);

  const selectedNodeComments = useMemo(() => {
    const selectedNodeId = String(slice.selectedNodeId || "").trim();
    if (!selectedNodeId) {
      return [];
    }
    return commentsByNode[selectedNodeId] || [];
  }, [commentsByNode, slice.selectedNodeId]);

  const effectiveViewerHeight = Math.max(260, Math.min(1200, Math.round(Number(viewerHeight) || 520)));
  const [elkPositions, setElkPositions] = useState<Record<string, { x: number; y: number }>>({});
  const fallbackPositions = useMemo(
    () => computeWorkGraphLayout(visibleNodes, visibleEdges, slice.rootId),
    [slice.rootId, visibleEdges, visibleNodes],
  );

  useEffect(() => {
    let cancelled = false;
    void computeWorkGraphLaneLayout(visibleNodes, visibleEdges, slice.rootId).then((positions) => {
      if (cancelled) {
        return;
      }
      setElkPositions(positions);
    });
    return () => {
      cancelled = true;
    };
  }, [slice.rootId, visibleEdges, visibleNodes]);

  const positions = Object.keys(elkPositions).length > 0 ? elkPositions : fallbackPositions;

  const focusActiveNode = useCallback(() => {
    const nextNodeId = slice.activeNodeIds[0] || visibleNodes[0]?.id || null;
    slice.setSelectedNodeId(nextNodeId);
  }, [slice, visibleNodes]);

  const toggleCollapseSelectedNode = useCallback(() => {
    if (!slice.selectedNodeId) {
      return;
    }
    setCollapsedNodeIds((previous) => toggleCollapsedNodeIds(previous, slice.selectedNodeId || ""));
  }, [slice.selectedNodeId]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const isTypingTarget =
        target &&
        (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
      if (event.key === "/" && !isTypingTarget) {
        event.preventDefault();
        searchInputRef.current?.focus();
        return;
      }
      if (isTypingTarget) {
        return;
      }
      if (event.key.toLowerCase() === "f") {
        event.preventDefault();
        focusActiveNode();
        return;
      }
      if (event.key.toLowerCase() === "c") {
        event.preventDefault();
        toggleCollapseSelectedNode();
        return;
      }
      if (event.key.toLowerCase() === "x") {
        event.preventDefault();
        setCollapsedNodeIds([]);
        return;
      }
      if (event.key.toLowerCase() === "u") {
        event.preventDefault();
        setFocusMode((previous) => !previous);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [focusActiveNode, toggleCollapseSelectedNode]);

  const flowNodes = useMemo(
    () =>
      visibleNodes.map((node): Node<WorkGraphNodeRenderData> => ({
        id: node.id,
        type: "work",
        position: positions[node.id] || { x: 120, y: 100 },
        data: {
          title: String(node.title || node.id),
          detail: String(node.detail || ""),
          nodeType: String(node.node_type || ""),
          status: String(node.status || "queued"),
          role: String(node.agent_role || "system"),
          confidence: typeof node.confidence === "number" ? node.confidence : null,
          progress: typeof node.progress === "number" ? node.progress : null,
          evidenceCount: Number(node.evidence_count || (node.evidence_refs || []).length || 0),
          artifactCount: Number(node.artifact_count || (node.artifact_refs || []).length || 0),
          sceneCount: Number(node.scene_count || (node.scene_refs || []).length || 0),
          riskReason: extractNodeRiskReason(node),
          isActive: slice.activeNodeIds.includes(node.id) || slice.selectedNodeId === node.id,
          onAsk: onAskNode
            ? (nodeId: string) =>
                onAskNode({
                  nodeId,
                  title: String(node.title || ""),
                  text: String(node.detail || ""),
                })
            : undefined,
          onInspectEvidence: onInspectEvidence
            ? (nodeId: string) => {
                const match = slice.nodes.find((row) => row.id === nodeId);
                if (!match) {
                  return;
                }
                onInspectEvidence({
                  nodeId,
                  title: String(match.title || nodeId),
                  evidenceIds: Array.isArray(match.evidence_refs) ? match.evidence_refs : [],
                  sceneRefs: Array.isArray(match.scene_refs) ? match.scene_refs : [],
                  eventRefs: Array.isArray(match.event_refs) ? match.event_refs : [],
                });
              }
            : undefined,
          onInspectVerifier: onInspectVerifier
            ? (nodeId: string) => {
                const match = slice.nodes.find((row) => row.id === nodeId);
                if (!match) {
                  return;
                }
                onInspectVerifier({
                  nodeId,
                  title: String(match.title || nodeId),
                  detail: String(match.detail || ""),
                  status: String(match.status || "queued"),
                  confidence: typeof match.confidence === "number" ? match.confidence : null,
                  riskReason: extractNodeRiskReason(match),
                  sceneRefs: Array.isArray(match.scene_refs) ? match.scene_refs : [],
                  eventRefs: Array.isArray(match.event_refs) ? match.event_refs : [],
                });
              }
            : undefined,
        },
        selectable: true,
        draggable: false,
      })),
    [onAskNode, onInspectEvidence, onInspectVerifier, positions, slice.activeNodeIds, slice.nodes, slice.selectedNodeId, visibleNodes],
  );

  const flowEdges = useMemo(
    () =>
      visibleEdges.map((edge): Edge => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        type: "workEdge",
        animated: edge.edge_family === "handoff" || edge.edge_family === "verification",
        data: {
          edge_family: edge.edge_family,
          relation: edge.relation,
        },
      })),
    [visibleEdges],
  );

  const handleNodeClick = (_event: unknown, node: Node<WorkGraphNodeRenderData>) => {
    slice.setSelectedNodeId(node.id);
    collaborationRef.current?.publish({
      kind: "selection",
      runId: String(slice.runId || ""),
      nodeId: node.id,
      userId: identityRef.current.userId,
      userLabel: identityRef.current.userLabel,
      timestamp: new Date().toISOString(),
    });
    const matchedNode = slice.nodes.find((row: WorkGraphNode) => row.id === node.id);
    if (!matchedNode) {
      return;
    }
    const jumpTarget = buildWorkGraphJumpTarget(matchedNode);
    if (typeof jumpTarget.eventIndexStart === "number" && jumpTarget.eventIndexStart > 0) {
      slice.setReplayCursor(jumpTarget.eventIndexStart);
    }
    emitWorkGraphJumpTarget(jumpTarget);
  };

  const submitNodeComment = () => {
    const selectedNodeId = String(slice.selectedNodeId || "").trim();
    const text = String(commentDraft || "").trim();
    if (!selectedNodeId || !text) {
      return;
    }
    collaborationRef.current?.publish({
      kind: "comment",
      runId: String(slice.runId || ""),
      nodeId: selectedNodeId,
      commentId: `${selectedNodeId}:${Date.now()}`,
      text,
      userId: identityRef.current.userId,
      userLabel: identityRef.current.userLabel,
      timestamp: new Date().toISOString(),
    });
    setCommentDraft("");
  };

  return (
    <div>
      <WorkGraphToolbar
        runId={slice.runId}
        nodeCount={visibleNodes.length}
        edgeCount={visibleEdges.length}
        loading={slice.loading}
        streaming={slice.streaming}
        onFocusActive={focusActiveNode}
      />
      <WorkGraphControlPanel
        searchInputRef={searchInputRef}
        searchQuery={searchQuery}
        onSearchQueryChange={setSearchQuery}
        statusFilter={statusFilter}
        onStatusFilterChange={setStatusFilter}
        roleFilter={roleFilter}
        onRoleFilterChange={setRoleFilter}
        roleOptions={roleOptions}
        confidenceFilter={confidenceFilter}
        onConfidenceFilterChange={setConfidenceFilter}
        edgeFamilyFilter={edgeFamilyFilter}
        onEdgeFamilyFilterChange={setEdgeFamilyFilter}
        focusMode={focusMode}
        onToggleFocusMode={() => setFocusMode((previous) => !previous)}
        onToggleCollapseSelectedNode={toggleCollapseSelectedNode}
        hasSelectedNode={Boolean(slice.selectedNodeId)}
        onExpandAll={() => setCollapsedNodeIds([])}
        canExpandAll={collapsedNodeIds.length > 0}
        visibleNodeCount={visibleNodes.length}
        totalNodeCount={slice.nodes.length}
        collaboratorPresence={collaboratorPresence}
        selectedNodeId={slice.selectedNodeId}
        selectedNodeComments={selectedNodeComments}
        commentDraft={commentDraft}
        onCommentDraftChange={setCommentDraft}
        onSubmitNodeComment={submitNodeComment}
      />
      <WorkGraphLegend />
      <div style={{ height: `${effectiveViewerHeight}px` }} className="overflow-hidden rounded-xl border border-[#d2d2d7]">
        <ReactFlow
          fitView
          nodes={flowNodes}
          edges={flowEdges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodeClick={handleNodeClick}
          minZoom={0.3}
          maxZoom={1.8}
          attributionPosition="bottom-right"
        >
          <MiniMap pannable zoomable nodeColor={(node) => statusColor(String(node.data?.["status"] || "queued"))} />
          <Controls showInteractive />
          <Background gap={20} color="#f0f1f4" />
        </ReactFlow>
      </div>
    </div>
  );
}

export { WorkGraphViewer, computeWorkGraphLayout };
