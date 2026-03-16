import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  MarkerType,
  ReactFlow,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
} from "@xyflow/react";

import "@xyflow/react/dist/style.css";

import type { AgentSummaryRecord } from "../../../api/client";
import type { WorkflowRunRecord, WorkflowTemplate } from "../../../api/client/types";
import {
  useWorkflowStore,
  type WorkflowCanvasEdge,
  type WorkflowCanvasNode,
  type WorkflowCanvasNodeType,
} from "../../stores/workflowStore";
import { NLBuilderSheet } from "./NLBuilderSheet";
import { StepConfigPanel } from "./StepConfigPanel";
import { WorkflowEdge, type WorkflowFlowEdgeData } from "./WorkflowEdge";
import { WorkflowNode, type WorkflowFlowNodeData } from "./WorkflowNode";
import { WorkflowRunHistory } from "./WorkflowRunHistory";
import { WorkflowTemplates } from "./WorkflowTemplates";
import { WorkflowToolbar } from "./WorkflowToolbar";

type WorkflowCanvasProps = {
  agents: AgentSummaryRecord[];
  isRunning: boolean;
  isDirty: boolean;
  templates: WorkflowTemplate[];
  templatesLoading: boolean;
  runHistory: WorkflowRunRecord[];
  runHistoryLoading: boolean;
  nlGenerating: boolean;
  nlStreamLog: string;
  nlError: string;
  onRun: () => void;
  onStop?: () => void;
  onSave: () => void;
  onRefreshTemplates: () => void;
  onRefreshRunHistory: () => void;
  onGenerateFromDescription: (description: string, maxSteps: number) => Promise<boolean>;
  onSelectTemplate: (template: WorkflowTemplate) => void;
  onLoadRunOutputs: (run: WorkflowRunRecord) => void;
};

function inferNodeType(nextIndex: number): WorkflowCanvasNodeType {
  if (nextIndex === 0) {
    return "trigger";
  }
  return "agent";
}

function toFlowNode(node: WorkflowCanvasNode, selectedNodeId: string | null): Node<WorkflowFlowNodeData> {
  return {
    id: node.id,
    type: "workflowNode",
    position: node.position,
    selected: node.id === selectedNodeId,
    data: {
      ...node.data,
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
      toolIds: Array.isArray(node.data.toolIds) ? node.data.toolIds : [],
      config: node.data.config || {},
      inputMapping: node.data.inputMapping || {},
      outputKey: node.data.outputKey,
      description: node.data.description,
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

function WorkflowCanvas({
  agents,
  isRunning,
  isDirty,
  templates,
  templatesLoading,
  runHistory,
  runHistoryLoading,
  nlGenerating,
  nlStreamLog,
  nlError,
  onRun,
  onStop,
  onSave,
  onRefreshTemplates,
  onRefreshRunHistory,
  onGenerateFromDescription,
  onSelectTemplate,
  onLoadRunOutputs,
}: WorkflowCanvasProps) {
  const nodes = useWorkflowStore((state) => state.nodes);
  const edges = useWorkflowStore((state) => state.edges);
  const selectedNodeId = useWorkflowStore((state) => state.selectedNodeId);
  const viewport = useWorkflowStore((state) => state.viewport);
  const setNodes = useWorkflowStore((state) => state.setNodes);
  const setEdges = useWorkflowStore((state) => state.setEdges);
  const addNode = useWorkflowStore((state) => state.addNode);
  const addStoreEdge = useWorkflowStore((state) => state.addEdge);
  const removeNode = useWorkflowStore((state) => state.removeNode);
  const setSelectedNodeId = useWorkflowStore((state) => state.setSelectedNodeId);
  const setViewport = useWorkflowStore((state) => state.setViewport);
  const updateNodeData = useWorkflowStore((state) => state.updateNodeData);
  const updateEdgeCondition = useWorkflowStore((state) => state.updateEdgeCondition);

  const [templatesOpen, setTemplatesOpen] = useState(false);
  const [runHistoryOpen, setRunHistoryOpen] = useState(false);
  const [nlBuilderOpen, setNlBuilderOpen] = useState(false);
  const [toolbarVisible, setToolbarVisible] = useState(true);
  const toolbarHideTimerRef = useRef<number | null>(null);
  const toolbarHoverLockRef = useRef(false);

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
    () => nodes.find((node) => node.id === selectedNodeId) || null,
    [nodes, selectedNodeId],
  );
  const selectedNodeOutgoingEdges = useMemo(
    () => (selectedNode ? edges.filter((edge) => edge.source === selectedNode.id) : []),
    [edges, selectedNode],
  );

  const flowNodes = useMemo<Node<WorkflowFlowNodeData>[]>(
    () => nodes.map((node) => toFlowNode(node, selectedNodeId)),
    [nodes, selectedNodeId],
  );
  const flowEdges = useMemo<Edge<WorkflowFlowEdgeData>[]>(
    () => edges.map(toFlowEdge),
    [edges],
  );

  const nodeTypes = useMemo(
    () => ({
      workflowNode: WorkflowNode,
    }),
    [],
  );
  const edgeTypes = useMemo(
    () => ({
      workflowEdge: WorkflowEdge,
    }),
    [],
  );

  const onNodesChange = useCallback(
    (changes: NodeChange<Node<WorkflowFlowNodeData>>[]) => {
      const changed = applyNodeChanges(changes, flowNodes);
      setNodes(changed.map(toStoreNode));
      const selected = changed.find((node) => node.selected)?.id || null;
      setSelectedNodeId(selected);
    },
    [flowNodes, setNodes, setSelectedNodeId],
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange<Edge<WorkflowFlowEdgeData>>[]) => {
      const changed = applyEdgeChanges(changes, flowEdges);
      setEdges(changed.map(toStoreEdge));
    },
    [flowEdges, setEdges],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) {
        return;
      }
      const next = addEdge(
        {
          ...connection,
          id: `${connection.source}->${connection.target}-${Date.now()}`,
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
    [flowEdges, setEdges],
  );

  const handleAddNode = () => {
    const nextIndex = nodes.length;
    const previous = nodes.at(-1);
    const nextNodeId = `step_${nextIndex + 1}`;
    addNode({
      id: nextNodeId,
      type: inferNodeType(nextIndex),
      position: {
        x: 140 + nextIndex * 320,
        y: 140 + (nextIndex % 2) * 220,
      },
      data: {
        label: `Step ${nextIndex + 1}`,
        agentId: previous?.data.agentId || agents[0]?.agent_id || "",
        toolIds: [],
        config: {},
        inputMapping: previous?.data.outputKey
          ? { message: previous.data.outputKey }
          : { message: "literal:Describe the first step input" },
        outputKey: `step_${nextIndex + 1}_output`,
      },
      runState: "idle",
      runOutput: "",
    });
    if (previous) {
      addStoreEdge({
        id: `${previous.id}->${nextNodeId}-${Date.now()}`,
        source: previous.id,
        target: nextNodeId,
        condition: undefined,
        animated: false,
      });
    }
    setSelectedNodeId(nextNodeId);
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

  return (
    <div
      className="relative h-full w-full overflow-hidden rounded-[24px] border border-black/[0.08] bg-[#eef3fb]"
      onMouseMove={(event) => {
        const bounds = event.currentTarget.getBoundingClientRect();
        const offsetY = event.clientY - bounds.top;
        if (offsetY <= 96) {
          revealToolbar(1800);
        }
      }}
      onMouseLeave={() => scheduleToolbarHide(600)}
    >
      <div
        aria-hidden
        className="absolute inset-x-0 top-0 z-[15] h-16"
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
      />
      <div
        className={`absolute left-3 right-3 top-3 z-20 flex items-start gap-2 transition-all duration-200 ${
          toolbarVisible
            ? "pointer-events-auto translate-y-0 opacity-100"
            : "pointer-events-none -translate-y-2 opacity-0"
        }`}
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
        <div className="flex-1">
          <WorkflowToolbar
            isRunning={isRunning}
            isDirty={isDirty}
            onRun={onRun}
            onStop={onStop}
            onAddStep={handleAddNode}
            onSave={onSave}
            onOpenTemplates={() => setTemplatesOpen((current) => !current)}
            onOpenNlBuilder={() => setNlBuilderOpen(true)}
            onOpenRunHistory={() => setRunHistoryOpen((current) => !current)}
          />
        </div>
      </div>

      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={(_, node) => setSelectedNodeId(node.id)}
        onPaneClick={() => setSelectedNodeId(null)}
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
        runs={runHistory}
        onClose={() => setRunHistoryOpen(false)}
        onRefresh={onRefreshRunHistory}
        onLoadOutputs={(run) => {
          onLoadRunOutputs(run);
          setRunHistoryOpen(false);
        }}
      />

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

      <div className="pointer-events-none absolute inset-y-0 right-0 z-10 p-4">
        <div className="pointer-events-auto">
          <StepConfigPanel
            node={selectedNode}
            agents={agents}
            outgoingEdges={selectedNodeOutgoingEdges}
            onClose={() => setSelectedNodeId(null)}
            onDeleteNode={removeNode}
            onUpdateNodeData={updateNodeData}
            onUpdateEdgeCondition={updateEdgeCondition}
          />
        </div>
      </div>
    </div>
  );
}

export { WorkflowCanvas };
export type { WorkflowCanvasProps };
