import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  MarkerType,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  useReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
} from "@xyflow/react";

import "@xyflow/react/dist/style.css";
import { Plus, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { listAgents, listMarketplaceAgents } from "../../../api/client";
import type { WorkflowRunRecord, WorkflowTemplate } from "../../../api/client/types";
import {
  applyAutoLayout,
  useWorkflowStore,
  type WorkflowCanvasEdge,
  type WorkflowCanvasNode,
  type WorkflowCanvasNodeType,
} from "../../stores/workflowStore";
import {
  AgentPickerPanel,
  normalizeAgentRow,
  type WorkflowSelectableAgent,
} from "./AgentPickerPanel";
import { NLBuilderSheet } from "./NLBuilderSheet";
import { StepConfigPanel } from "./StepConfigPanel";
import { WorkflowEdge, type WorkflowFlowEdgeData } from "./WorkflowEdge";
import { WorkflowNode, type WorkflowFlowNodeData } from "./WorkflowNode";
import { RunInspector } from "./RunInspector";
import { WorkflowRunHistory } from "./WorkflowRunHistory";
import { WorkflowTemplates } from "./WorkflowTemplates";
import { WorkflowToolbar } from "./WorkflowToolbar";
import { useWorkflowViewStore } from "../../stores/workflowViewStore";

type WorkflowCanvasProps = {
  isRunning: boolean;
  isDirty: boolean;
  templates: WorkflowTemplate[];
  templatesLoading: boolean;
  runHistory: WorkflowRunRecord[];
  runHistoryLoading: boolean;
  runHistoryHasMore: boolean;
  runHistoryLoadingMore: boolean;
  nlGenerating: boolean;
  nlStreamLog: string;
  nlError: string;
  onRun: () => void;
  onStop?: () => void;
  onSave: () => void;
  onSchedule?: () => void;
  onRefreshTemplates: () => void;
  onRefreshRunHistory: () => void;
  onLoadMoreRunHistory: () => void;
  onGenerateFromDescription: (description: string, maxSteps: number) => Promise<boolean>;
  onSelectTemplate: (template: WorkflowTemplate) => void;
  onLoadRunOutputs: (run: WorkflowRunRecord) => void;
  initialAgentHintId?: string | null;
  validationWarningsByNodeId?: Record<string, string>;
};

function inferNodeType(nextIndex: number, totalAfterAdd: number): WorkflowCanvasNodeType {
  if (nextIndex === 0 && totalAfterAdd === 1) return "trigger"; // only node is both trigger & output — keep as trigger
  if (nextIndex === 0) return "trigger";
  if (nextIndex === totalAfterAdd - 1) return "output"; // last node is output
  return "agent";
}

function nextStepOrdinal(nodes: WorkflowCanvasNode[]): number {
  let maxOrdinal = 0;
  const existingIds = new Set(nodes.map((node) => String(node.id || "").trim()).filter(Boolean));
  for (const node of nodes) {
    const match = String(node.id || "").trim().match(/^step_(\d+)$/i);
    if (!match?.[1]) {
      continue;
    }
    const parsed = Number.parseInt(match[1], 10);
    if (Number.isFinite(parsed) && parsed > maxOrdinal) {
      maxOrdinal = parsed;
    }
  }

  let candidate = Math.max(1, maxOrdinal + 1);
  while (existingIds.has(`step_${candidate}`)) {
    candidate += 1;
  }
  return candidate;
}
function toFlowNode(
  node: WorkflowCanvasNode,
  selectedNodeId: string | null,
  validationWarningsByNodeId?: Record<string, string>,
): Node<WorkflowFlowNodeData> {
  return {
    id: node.id,
    type: "workflowNode",
    position: node.position,
    selected: node.id === selectedNodeId,
    data: {
      ...node.data,
      validationWarning: String(validationWarningsByNodeId?.[node.id] || "").trim(),
      nodeType: node.type,
      runState: node.runState,
      runOutput: node.runOutput,
    },
  };
}

function toStoreNode(node: Node<WorkflowFlowNodeData>): WorkflowCanvasNode {
  return {
    id: node.id,
    type: node.data.nodeType,
    position: node.position,
    data: {
      label: node.data.label,
      agentId: node.data.agentId,
      agentName: node.data.agentName,
      agentDescription: node.data.agentDescription,
      agentTags: Array.isArray(node.data.agentTags) ? node.data.agentTags : [],
      requiredConnectors: Array.isArray(node.data.requiredConnectors) ? node.data.requiredConnectors : [],
      toolIds: Array.isArray(node.data.toolIds) ? node.data.toolIds : [],
      stepType: node.data.stepType || "agent",
      stepConfig: node.data.stepConfig || {},
      config: node.data.config || {},
      inputMapping: node.data.inputMapping || {},
      outputKey: node.data.outputKey,
      description: node.data.description,
      inputDescription: node.data.inputDescription,
      outputDescription: node.data.outputDescription,
      timeoutS: node.data.timeoutS,
      maxRetries: node.data.maxRetries,
      validationWarning: node.data.validationWarning,
    },
    runState: node.data.runState,
    runOutput: node.data.runOutput,
  };
}

function toFlowEdge(edge: WorkflowCanvasEdge): Edge<WorkflowFlowEdgeData> {
  return {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    type: "workflowEdge",
    markerEnd: {
      type: MarkerType.ArrowClosed,
      width: 16,
      height: 16,
      color: "#9db6dc",
    },
    data: {
      condition: edge.condition,
      animated: edge.animated,
    },
  };
}

function toStoreEdge(edge: Edge<WorkflowFlowEdgeData>): WorkflowCanvasEdge {
  return {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    condition: edge.data?.condition,
    animated: edge.data?.animated || false,
  };
}

function wouldCreateCycle(
  sourceId: string,
  targetId: string,
  existingEdges: WorkflowCanvasEdge[],
): boolean {
  const adjacency = new Map<string, string[]>();
  for (const edge of existingEdges) {
    const outgoing = adjacency.get(edge.source) || [];
    outgoing.push(edge.target);
    adjacency.set(edge.source, outgoing);
  }
  const withCandidate = adjacency.get(sourceId) || [];
  withCandidate.push(targetId);
  adjacency.set(sourceId, withCandidate);

  const visited = new Set<string>();
  const stack = [targetId];
  while (stack.length > 0) {
    const nodeId = stack.pop() as string;
    if (nodeId === sourceId) {
      return true;
    }
    if (visited.has(nodeId)) {
      continue;
    }
    visited.add(nodeId);
    for (const nextId of adjacency.get(nodeId) || []) {
      stack.push(nextId);
    }
  }
  return false;
}

// ── Empty canvas overlay ──────────────────────────────────────────────────────

function agentMonogramLetter(name: string) {
  return String(name || "").trim().charAt(0).toUpperCase() || "A";
}

type EmptyCanvasOverlayProps = {
  onAddAgent: (agent: WorkflowSelectableAgent) => void;
  onOpenPicker: () => void;
};

function EmptyCanvasOverlay({ onAddAgent, onOpenPicker }: EmptyCanvasOverlayProps) {
  const [agents, setAgents] = useState<WorkflowSelectableAgent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let disposed = false;
    Promise.all([
      listMarketplaceAgents({ sort_by: "installs", limit: 100 }),
      listAgents().catch(() => []),
    ])
      .then(([catalogRows, installedRows]) => {
        const installedIds = new Set(
          (installedRows || [])
            .map((row) => String(row.agent_id || "").trim())
            .filter(Boolean),
        );
        const normalized = (catalogRows || [])
          .map((row) => normalizeAgentRow(row, installedIds))
          .filter((row) => row.agentId && row.isInstalled)
          .slice(0, 12);
        if (!disposed) setAgents(normalized);
      })
      .catch(() => { if (!disposed) setAgents([]); })
      .finally(() => { if (!disposed) setLoading(false); });
    return () => { disposed = true; };
  }, []);

  return (
    <div className="pointer-events-auto absolute inset-0 z-[5] flex flex-col items-center justify-center px-8">
      <div className="w-full max-w-2xl rounded-3xl border border-black/[0.07] bg-white/90 p-8 shadow-[0_8px_40px_-12px_rgba(15,23,42,0.18)] backdrop-blur-md">
        {/* Header */}
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-[20px] font-bold text-[#101828]">Start your workflow</h2>
            <p className="mt-1 text-[13px] text-[#667085]">
              Pick one of your installed agents to add as the first step, or browse all available agents.
            </p>
          </div>
          <button
            type="button"
            onClick={onOpenPicker}
            className="flex shrink-0 items-center gap-1.5 rounded-xl bg-[#7c3aed] px-4 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-[#6d28d9]"
          >
            <Plus size={14} />
            Browse all
          </button>
        </div>

        {/* Agent grid */}
        {loading ? (
          <div className="grid grid-cols-3 gap-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-[88px] animate-pulse rounded-2xl bg-[#f0f4ff]" />
            ))}
          </div>
        ) : agents.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-6 text-center">
            <Sparkles size={28} className="text-[#a78bfa]" />
            <p className="text-[13px] text-[#667085]">
              No agents installed yet.{" "}
              <button
                type="button"
                className="font-semibold text-[#3b5bdb] hover:underline"
                onClick={onOpenPicker}
              >
                Browse the marketplace
              </button>{" "}
              to get started.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-3">
            {agents.map((agent) => (
              <button
                key={agent.id}
                type="button"
                onClick={() => onAddAgent(agent)}
                className="group flex flex-col gap-2 rounded-2xl border border-black/[0.07] bg-[#f8fafc] p-3.5 text-left transition-all hover:border-[#3b5bdb]/30 hover:bg-[#f0f4ff] hover:shadow-[0_2px_12px_-4px_rgba(59,91,219,0.2)]"
              >
                <div className="flex items-center gap-2.5">
                  <div className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[#f5f3ff] to-[#ede9fe] text-[14px] font-bold text-[#7c3aed]">
                    {agentMonogramLetter(agent.name)}
                  </div>
                  <p className="truncate text-[12px] font-semibold text-[#101828] group-hover:text-[#7c3aed]">
                    {agent.name}
                  </p>
                </div>
                {agent.description ? (
                  <p className="line-clamp-2 text-[10px] leading-[1.5] text-[#667085]">
                    {agent.description}
                  </p>
                ) : null}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Canvas ─────────────────────────────────────────────────────────────────────

function WorkflowCanvasInner({
  isRunning,
  isDirty,
  templates,
  templatesLoading,
  runHistory,
  runHistoryLoading,
  runHistoryHasMore,
  runHistoryLoadingMore,
  nlGenerating,
  nlStreamLog,
  nlError,
  onRun,
  onStop,
  onSave,
  onRefreshTemplates,
  onRefreshRunHistory,
  onLoadMoreRunHistory,
  onGenerateFromDescription,
  onSelectTemplate,
  onLoadRunOutputs,
  initialAgentHintId = null,
  validationWarningsByNodeId = {},
}: WorkflowCanvasProps) {
  const { fitView, setViewport: setRFViewport } = useReactFlow();
  const storeWorkflowId = useWorkflowStore((state) => state.workflowId);
  const nodes = useWorkflowStore((state) => state.nodes);
  const edges = useWorkflowStore((state) => state.edges);
  const selectedNodeId = useWorkflowStore((state) => state.selectedNodeId);
  const viewport = useWorkflowStore((state) => state.viewport);
  const setNodes = useWorkflowStore((state) => state.setNodes);
  const setEdges = useWorkflowStore((state) => state.setEdges);
  const removeNode = useWorkflowStore((state) => state.removeNode);
  const setSelectedNodeId = useWorkflowStore((state) => state.setSelectedNodeId);
  const setViewport = useWorkflowStore((state) => state.setViewport);
  const updateNodeData = useWorkflowStore((state) => state.updateNodeData);
  const updateEdgeCondition = useWorkflowStore((state) => state.updateEdgeCondition);

  // Local panel-node state guarantees the config panel closes immediately via
  // React setState, without depending on a Zustand round-trip through selectors.
  const [panelNodeId, setPanelNodeId] = useState<string | null>(selectedNodeId);

  // Keep local panelNodeId in sync when Zustand selectedNodeId changes externally
  // (e.g. onNodeClick, addNodeWithAgent).
  useEffect(() => {
    setPanelNodeId(selectedNodeId);
  }, [selectedNodeId]);

  const [templatesOpen, setTemplatesOpen] = useState(false);
  const [runHistoryOpen, setRunHistoryOpen] = useState(false);
  const [runInspectorOpen, setRunInspectorOpen] = useState(false);
  const [nlBuilderOpen, setNlBuilderOpen] = useState(false);
  const [agentPickerOpen, setAgentPickerOpen] = useState(false);
  const [agentPickerNodeId, setAgentPickerNodeId] = useState<string | null>(null);
  const [agentPickerPreferredAgentId, setAgentPickerPreferredAgentId] = useState("");
  const [toolbarVisible, setToolbarVisible] = useState(true);
  const toolbarHideTimerRef = useRef<number | null>(null);
  const toolbarHoverLockRef = useRef(false);
  const consumedInitialAgentHintRef = useRef("");

  const clearToolbarHideTimer = useCallback(() => {
    if (toolbarHideTimerRef.current === null) {
      return;
    }
    window.clearTimeout(toolbarHideTimerRef.current);
    toolbarHideTimerRef.current = null;
  }, []);

  const scheduleToolbarHide = useCallback(
    (delayMs = 1800) => {
      clearToolbarHideTimer();
      toolbarHideTimerRef.current = window.setTimeout(() => {
        toolbarHideTimerRef.current = null;
        if (toolbarHoverLockRef.current) {
          return;
        }
        setToolbarVisible(false);
      }, delayMs);
    },
    [clearToolbarHideTimer],
  );

  const revealToolbar = useCallback(
    (hideDelayMs = 1800) => {
      setToolbarVisible(true);
      scheduleToolbarHide(hideDelayMs);
    },
    [scheduleToolbarHide],
  );

  const selectedNode = useMemo(
    () => nodes.find((node) => node.id === panelNodeId) || null,
    [nodes, panelNodeId],
  );
  const selectedNodeOutgoingEdges = useMemo(
    () => (selectedNode ? edges.filter((edge) => edge.source === selectedNode.id) : []),
    [edges, selectedNode],
  );
  const availableOutputKeys = useMemo(
    () =>
      nodes
        .filter((node) => node.id !== selectedNodeId)
        .map((node) => String(node.data.outputKey || "").trim())
        .filter(Boolean),
    [nodes, selectedNodeId],
  );

  // Map outputKey → human-readable step label for the config panel
  const outputKeyLabels = useMemo(() => {
    const result: Record<string, string> = {};
    for (const node of nodes) {
      const key = String(node.data.outputKey || "").trim();
      if (key) result[key] = String(node.data.label || node.id).trim();
    }
    return result;
  }, [nodes]);

  const flowNodes = useMemo<Node<WorkflowFlowNodeData>[]>(
    () => nodes.map((node) => toFlowNode(node, selectedNodeId, validationWarningsByNodeId)),
    [nodes, selectedNodeId, validationWarningsByNodeId],
  );
  const flowEdges = useMemo<Edge<WorkflowFlowEdgeData>[]>(
    () => edges.map(toFlowEdge),
    [edges],
  );

  const nodeTypes = useMemo(() => ({ workflowNode: WorkflowNode }), []);
  const edgeTypes = useMemo(() => ({ workflowEdge: WorkflowEdge }), []);

  // Only process user-initiated position changes (drag).  ReactFlow manages
  // dimensions & selection internally — if we round-trip dimension changes through
  // toStoreNode (which drops width/height) it creates an infinite measure loop.
  const onNodesChange = useCallback(
    (changes: NodeChange<Node<WorkflowFlowNodeData>>[]) => {
      const positionChanges = changes.filter((c) => c.type === "position");
      if (positionChanges.length === 0) return;
      const latest = useWorkflowStore.getState();
      const currentFlowNodes = latest.nodes.map((n) =>
        toFlowNode(n, latest.selectedNodeId, validationWarningsByNodeId),
      );
      const changed = applyNodeChanges(positionChanges, currentFlowNodes);
      setNodes(changed.map(toStoreNode));
    },
    [setNodes, validationWarningsByNodeId],
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange<Edge<WorkflowFlowEdgeData>>[]) => {
      const currentFlowEdges = useWorkflowStore.getState().edges.map(toFlowEdge);
      const changed = applyEdgeChanges(changes, currentFlowEdges);
      setEdges(changed.map(toStoreEdge));
    },
    [setEdges],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) {
        return;
      }
      const sourceId = String(connection.source).trim();
      const targetId = String(connection.target).trim();
      if (!sourceId || !targetId) {
        return;
      }
      if (sourceId === targetId) {
        toast.warning("A step cannot connect to itself.");
        return;
      }
      const isDuplicate = edges.some(
        (edge) => edge.source === sourceId && edge.target === targetId,
      );
      if (isDuplicate) {
        toast.warning("That connection already exists.");
        return;
      }
      if (wouldCreateCycle(sourceId, targetId, edges)) {
        toast.warning("Cycle detected. Connect downstream only.");
        return;
      }
      const next = addEdge(
        {
          ...connection,
          id: `${sourceId}->${targetId}-${Date.now()}`,
          type: "workflowEdge",
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 16,
            height: 16,
            color: "#9db6dc",
          },
          data: {
            condition: "",
            animated: false,
          },
        },
        flowEdges,
      );
      setEdges(next.map(toStoreEdge));
    },
    [edges, flowEdges, setEdges],
  );

  // Reconnect: user drags an existing edge endpoint to a different node
  const onReconnect = useCallback(
    (oldEdge: Edge<WorkflowFlowEdgeData>, newConnection: Connection) => {
      const sourceId = String(newConnection.source || "").trim();
      const targetId = String(newConnection.target || "").trim();
      if (!sourceId || !targetId || sourceId === targetId) return;
      // Check for duplicates (ignore the edge being reconnected)
      const otherEdges = edges.filter((e) => e.id !== oldEdge.id);
      if (otherEdges.some((e) => e.source === sourceId && e.target === targetId)) {
        toast.warning("That connection already exists.");
        return;
      }
      if (wouldCreateCycle(sourceId, targetId, otherEdges)) {
        toast.warning("Cycle detected. Connect downstream only.");
        return;
      }
      // Replace old edge with the new connection
      const updatedEdges: WorkflowCanvasEdge[] = edges.map((e) =>
        e.id === oldEdge.id
          ? { ...e, source: sourceId, target: targetId }
          : e,
      );
      setEdges(updatedEdges);
    },
    [edges, setEdges],
  );

  const isValidConnection = useCallback(
    (connection: Connection | Edge<WorkflowFlowEdgeData>) => {
      const sourceId = String(connection.source || "").trim();
      const targetId = String(connection.target || "").trim();
      if (!sourceId || !targetId) {
        return false;
      }
      if (sourceId === targetId) {
        return false;
      }
      const duplicate = edges.some(
        (edge) => edge.source === sourceId && edge.target === targetId,
      );
      if (duplicate) {
        return false;
      }
      return !wouldCreateCycle(sourceId, targetId, edges);
    },
    [edges],
  );

  const addNodeWithAgent = (agent: WorkflowSelectableAgent) => {
    const nextIndex = nodes.length;
    const previous = nodes.at(-1);
    const nextOrdinal = nextStepOrdinal(nodes);
    const nextNodeId = `step_${nextOrdinal}`;
    const nextNode: WorkflowCanvasNode = {
      id: nextNodeId,
      type: inferNodeType(nextIndex, nextIndex + 1),
      position: { x: 0, y: 0 },
      data: {
        label: String(agent.name || `Step ${nextOrdinal}`),
        agentId: String(agent.agentId || "").trim(),
        agentName: String(agent.name || "").trim(),
        agentDescription: String(agent.description || "").trim(),
        agentTags: Array.isArray(agent.tags) ? agent.tags : [],
        requiredConnectors: Array.isArray(agent.requiredConnectors) ? agent.requiredConnectors : [],
        toolIds: [],
        config: {
          agent_name: String(agent.name || "").trim(),
          agent_description: String(agent.description || "").trim(),
          agent_tags: Array.isArray(agent.tags) ? agent.tags : [],
        },
        inputMapping: previous?.data.outputKey
          ? { message: previous.data.outputKey }
          : { message: "literal:Describe the first step input" },
        outputKey: `step_${nextOrdinal}_output`,
      },
      runState: "idle",
      runOutput: "",
    };
    const nextEdges = previous
      ? [
          ...edges,
          {
            id: `${previous.id}->${nextNodeId}-${Date.now()}`,
            source: previous.id,
            target: nextNodeId,
            condition: undefined,
            animated: false,
          },
        ]
      : edges;
    // Re-type previous last node from "output" to "agent" when appending
    const updatedNodes = nodes.map((n) =>
      n.type === "output" ? { ...n, type: "agent" as const } : n,
    );
    const laidOut = applyAutoLayout([...updatedNodes, nextNode], nextEdges);
    setNodes(laidOut);
    if (nextEdges !== edges) {
      setEdges(nextEdges);
    }
    setPanelNodeId(nextNodeId);
    setSelectedNodeId(nextNodeId);
    // For the very first node, reset viewport to a safe position so the node at
    // ~(120,120) is visible — fitView can fail when a single node hasn't been
    // measured yet.  For subsequent nodes, fitView works because earlier nodes
    // already have dimensions.
    if (nextIndex === 0) {
      setRFViewport({ x: 50, y: 30, zoom: 1 }, { duration: 250 });
    }
    setTimeout(() => fitView({ padding: 0.5, maxZoom: 1, duration: 350 }), 500);
  };

  const applyAgentToNode = (nodeId: string, agent: WorkflowSelectableAgent) => {
    const targetNode = nodes.find((node) => node.id === nodeId);
    if (!targetNode) {
      return;
    }
    const currentLabel = String(targetNode.data.label || "").trim();
    const currentAgentName = String(targetNode.data.agentName || "").trim();
    const shouldReplaceLabel =
      !currentLabel ||
      /^step\s+\d+$/i.test(currentLabel) ||
      (currentAgentName.length > 0 && currentLabel === currentAgentName);
    updateNodeData(nodeId, {
      agentId: String(agent.agentId || "").trim(),
      agentName: String(agent.name || "").trim(),
      agentDescription: String(agent.description || "").trim(),
      agentTags: Array.isArray(agent.tags) ? agent.tags : [],
      requiredConnectors: Array.isArray(agent.requiredConnectors) ? agent.requiredConnectors : [],
      config: {
        ...(targetNode.data.config || {}),
        agent_name: String(agent.name || "").trim(),
        agent_description: String(agent.description || "").trim(),
        agent_tags: Array.isArray(agent.tags) ? agent.tags : [],
      },
      ...(shouldReplaceLabel ? { label: String(agent.name || "Agent step") } : {}),
    });
  };

  const handleAddNode = () => {
    setAgentPickerNodeId(null);
    setAgentPickerPreferredAgentId("");
    setAgentPickerOpen(true);
  };

  useEffect(() => {
    revealToolbar(2400);
    return () => {
      clearToolbarHideTimer();
    };
  }, [clearToolbarHideTimer, revealToolbar]);

  useEffect(() => {
    if (templatesOpen || runHistoryOpen || nlBuilderOpen) {
      setToolbarVisible(true);
      clearToolbarHideTimer();
      return;
    }
    scheduleToolbarHide(1800);
  }, [
    clearToolbarHideTimer,
    nlBuilderOpen,
    runHistoryOpen,
    scheduleToolbarHide,
    templatesOpen,
  ]);

  useEffect(() => {
    const hint = String(initialAgentHintId || "").trim();
    if (!hint) {
      return;
    }
    if (consumedInitialAgentHintRef.current === hint) {
      return;
    }
    consumedInitialAgentHintRef.current = hint;
    setAgentPickerNodeId(null);
    setAgentPickerPreferredAgentId(hint);
    setAgentPickerOpen(true);
  }, [initialAgentHintId]);

  return (
    <div
      className="relative h-full w-full overflow-hidden bg-[#eef3fb]"
      onMouseMove={(event) => {
        const bounds = event.currentTarget.getBoundingClientRect();
        const offsetY = event.clientY - bounds.top;
        if (offsetY <= 96) {
          revealToolbar(1800);
        }
      }}
      onMouseLeave={() => scheduleToolbarHide(600)}
    >
      {/* Toolbar is always visible — no hover trigger needed */}
      <div
        className="pointer-events-none absolute left-3 right-3 top-3 z-20 flex items-start gap-2"
      >
        <div
          className="pointer-events-auto"
          onMouseEnter={() => {
            toolbarHoverLockRef.current = true;
            setToolbarVisible(true);
            clearToolbarHideTimer();
          }}
          onMouseMove={() => {
            toolbarHoverLockRef.current = true;
            setToolbarVisible(true);
            clearToolbarHideTimer();
          }}
          onMouseLeave={() => {
            toolbarHoverLockRef.current = false;
            scheduleToolbarHide(700);
          }}
          onFocusCapture={() => {
            toolbarHoverLockRef.current = true;
            setToolbarVisible(true);
            clearToolbarHideTimer();
          }}
          onBlurCapture={() => {
            toolbarHoverLockRef.current = false;
            scheduleToolbarHide(700);
          }}
        >
          <WorkflowToolbar
            isRunning={isRunning}
            isDirty={isDirty}
            onRun={onRun}
            onStop={onStop}
            onAddStep={handleAddNode}
            onSave={onSave}
            onSchedule={onSchedule || (() => {})}
            onOpenTemplates={() => setTemplatesOpen((current) => !current)}
            onOpenNlBuilder={() => setNlBuilderOpen(true)}
            onOpenRunHistory={() => setRunHistoryOpen((current) => !current)}
            onOpenRunInspector={() => setRunInspectorOpen((current) => !current)}
            onAllWorkflows={() => {
              useWorkflowViewStore.getState().setView("gallery");
            }}
          />
        </div>
      </div>

      {nodes.length === 0 ? (
        <EmptyCanvasOverlay
          onAddAgent={(agent) => {
            addNodeWithAgent(agent);
          }}
          onOpenPicker={() => {
            setAgentPickerNodeId(null);
            setAgentPickerPreferredAgentId("");
            setAgentPickerOpen(true);
          }}
        />
      ) : null}

      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onReconnect={onReconnect}
        isValidConnection={isValidConnection}
        onNodeClick={(_, node) => { setPanelNodeId(node.id); setSelectedNodeId(node.id); }}
        onPaneClick={() => { setPanelNodeId(null); setSelectedNodeId(null); }}
        onMoveEnd={(_, nextViewport) => setViewport(nextViewport)}
        defaultViewport={viewport}
        fitView
        fitViewOptions={{ maxZoom: 1.1, minZoom: 0.45, padding: 0.24 }}
        minZoom={0.32}
        maxZoom={1.8}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={22} size={1.2} color="#d7e0ee" />
      </ReactFlow>

      {/* Click-outside backdrop for side panels */}
      {(templatesOpen || runHistoryOpen || runInspectorOpen) ? (
        <div
          className="absolute inset-0 z-[18]"
          onClick={() => {
            setTemplatesOpen(false);
            setRunHistoryOpen(false);
            setRunInspectorOpen(false);
          }}
        />
      ) : null}

      <WorkflowTemplates
        open={templatesOpen}
        loading={templatesLoading}
        templates={templates}
        onClose={() => setTemplatesOpen(false)}
        onRefresh={onRefreshTemplates}
        onSelectTemplate={(template) => {
          onSelectTemplate(template);
          setTemplatesOpen(false);
        }}
      />

      <WorkflowRunHistory
        open={runHistoryOpen}
        loading={runHistoryLoading}
        loadingMore={runHistoryLoadingMore}
        hasMore={runHistoryHasMore}
        runs={runHistory}
        nodes={nodes}
        onClose={() => setRunHistoryOpen(false)}
        onRefresh={onRefreshRunHistory}
        onLoadMore={onLoadMoreRunHistory}
        onLoadOutputs={(run) => {
          onLoadRunOutputs(run);
          setRunHistoryOpen(false);
        }}
      />

      {runInspectorOpen ? (
        <div className="pointer-events-auto absolute right-4 top-4 z-30 h-[calc(100%-32px)]">
          <RunInspector
            workflowId={storeWorkflowId || ""}
            onClose={() => setRunInspectorOpen(false)}
          />
        </div>
      ) : null}

      <NLBuilderSheet
        open={nlBuilderOpen}
        isGenerating={nlGenerating}
        streamLog={nlStreamLog}
        error={nlError}
        onClose={() => setNlBuilderOpen(false)}
        onGenerate={async (description, maxSteps) => {
          const success = await onGenerateFromDescription(description, maxSteps);
          if (success) {
            setNlBuilderOpen(false);
          }
        }}
      />

      {/* Agent picker renders as a fixed modal — placed outside the stacking container */}
      <AgentPickerPanel
        open={agentPickerOpen}
        preferredAgentId={agentPickerPreferredAgentId}
        onClose={() => {
          setAgentPickerOpen(false);
          setAgentPickerNodeId(null);
          setAgentPickerPreferredAgentId("");
        }}
        onSelectAgent={(agent) => {
          if (agentPickerNodeId) {
            applyAgentToNode(agentPickerNodeId, agent);
          } else {
            addNodeWithAgent(agent);
          }
          setAgentPickerOpen(false);
          setAgentPickerNodeId(null);
          setAgentPickerPreferredAgentId("");
        }}
      />

      {selectedNode ? (
        <div className="pointer-events-none absolute inset-y-0 right-0 z-[25] flex items-start gap-3 p-4">
          <div className="pointer-events-auto h-full">
            <StepConfigPanel
              node={selectedNode}
              outgoingEdges={selectedNodeOutgoingEdges}
              outputKeyLabels={outputKeyLabels}
              onClose={() => {
                setPanelNodeId(null);
                setSelectedNodeId(null);
                setTimeout(() => fitView({ padding: 0.5, maxZoom: 1, duration: 300 }), 200);
              }}
              onDeleteNode={(nodeId) => { setPanelNodeId(null); removeNode(nodeId); }}
              onRequestChangeAgent={(nodeId) => {
                const currentNode = nodes.find((node) => node.id === nodeId);
                setAgentPickerNodeId(nodeId);
                setAgentPickerPreferredAgentId(
                  String(currentNode?.data.agentId || "").trim(),
                );
                setAgentPickerOpen(true);
              }}
              onUpdateNodeData={updateNodeData}
              onUpdateEdgeCondition={updateEdgeCondition}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}

function WorkflowCanvas(props: WorkflowCanvasProps) {
  return (
    <ReactFlowProvider>
      <WorkflowCanvasInner {...props} />
    </ReactFlowProvider>
  );
}

export { WorkflowCanvas };
export type { WorkflowCanvasProps };

