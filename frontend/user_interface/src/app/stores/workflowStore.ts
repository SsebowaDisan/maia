import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { WorkflowDefinition } from "../../api/client/types";

type WorkflowCanvasNodeType = "agent" | "trigger" | "condition" | "output";

/** Backend step types — deterministic automation nodes */
type StepType =
  | "agent"
  | "http_request"
  | "condition"
  | "code"
  | "transform"
  | "delay"
  | "foreach"
  | "merge"
  | "switch"
  | "knowledge_search";

type WorkflowCanvasNodeData = {
  label: string;
  agentId: string;
  agentName?: string;
  agentDescription?: string;
  agentTags?: string[];
  requiredConnectors?: string[];
  toolIds: string[];
  stepType: StepType;
  stepConfig: Record<string, unknown>;
  config: Record<string, unknown>;
  inputMapping: Record<string, string>;
  timeoutS?: number;
  maxRetries?: number;
  outputKey: string;
  description?: string;
  /** Plain-text description of what this step receives (shown on trigger/first node) */
  inputDescription?: string;
  /** Plain-text description of what this step produces (shown on output/last node) */
  outputDescription?: string;
  validationWarning?: string;
};

type WorkflowCanvasNodeRunState =
  | "idle"
  | "running"
  | "completed"
  | "failed"
  | "skipped"
  | "blocked";

type WorkflowCanvasNode = {
  id: string;
  type: WorkflowCanvasNodeType;
  position: { x: number; y: number };
  data: WorkflowCanvasNodeData;
  runState?: WorkflowCanvasNodeRunState;
  runOutput?: string;
};

type WorkflowCanvasEdge = {
  id: string;
  source: string;
  target: string;
  condition?: string;
  animated?: boolean;
};

type WorkflowRunStatus = "idle" | "running" | "completed" | "failed";

type WorkflowRunState = {
  runId: string | null;
  status: WorkflowRunStatus;
  activeStepId: string | null;
  detail: string | null;
  stepResults: Record<string, { output: string; duration_ms: number }>;
};

type WorkflowViewport = {
  x: number;
  y: number;
  zoom: number;
};

type WorkflowStoreState = {
  workflowId: string | null;
  workflowName: string;
  workflowDescription: string;
  activeTemplateId: string | null;
  nodes: WorkflowCanvasNode[];
  edges: WorkflowCanvasEdge[];
  selectedNodeId: string | null;
  viewport: WorkflowViewport;
  isDirty: boolean;
  run: WorkflowRunState;
  setMetadata: (payload: {
    workflowId?: string | null;
    workflowName?: string;
    workflowDescription?: string;
    activeTemplateId?: string | null;
  }) => void;
  setNodes: (nodes: WorkflowCanvasNode[]) => void;
  setEdges: (edges: WorkflowCanvasEdge[]) => void;
  setSelectedNodeId: (nodeId: string | null) => void;
  setViewport: (viewport: Partial<WorkflowViewport>) => void;
  updateNodeData: (
    nodeId: string,
    patch: Partial<WorkflowCanvasNodeData>,
    options?: { markDirty?: boolean },
  ) => void;
  updateEdgeCondition: (edgeId: string, condition: string) => void;
  addNode: (node: WorkflowCanvasNode) => void;
  removeNode: (nodeId: string) => void;
  addEdge: (edge: WorkflowCanvasEdge) => void;
  removeEdge: (edgeId: string) => void;
  loadDefinition: (
    definition: WorkflowDefinition,
    metadata?: { workflowId?: string | null; activeTemplateId?: string | null },
  ) => void;
  toDefinition: () => WorkflowDefinition;
  markSaved: () => void;
  reset: () => void;
  startRun: (runId: string) => void;
  setRunStatus: (status: WorkflowRunStatus) => void;
  setRunDetail: (detail: string | null) => void;
  setActiveStep: (stepId: string | null) => void;
  setNodeRunState: (
    nodeId: string,
    runState: WorkflowCanvasNodeRunState,
    detail?: string | null,
  ) => void;
  appendStepOutput: (stepId: string, outputChunk: string) => void;
  setStepResult: (stepId: string, output: string, durationMs: number) => void;
  hydrateRunOutputs: (results: Array<{ step_id: string; output_preview?: string; duration_ms?: number }>) => void;
  clearRun: () => void;
};

const defaultViewport: WorkflowViewport = { x: 0, y: 0, zoom: 1 };
const defaultRunState: WorkflowRunState = {
  runId: null,
  status: "idle",
  activeStepId: null,
  detail: null,
  stepResults: {},
};

function inferNodeType(stepIndex: number, totalSteps: number): WorkflowCanvasNodeType {
  if (stepIndex === 0 && totalSteps === 1) return "trigger";
  if (stepIndex === 0) return "trigger";
  if (stepIndex === totalSteps - 1) return "output";
  return "agent";
}

function applyAutoLayout(
  nodes: WorkflowCanvasNode[],
  edges: WorkflowCanvasEdge[],
): WorkflowCanvasNode[] {
  if (!nodes.length) {
    return nodes;
  }

  const horizontalGap = 400;
  const verticalGap = 190;
  const originX = 120;
  const originY = 120;

  const nodeIds = nodes.map((node) => node.id);
  const nodeIdSet = new Set(nodeIds);
  const incomingCount = new Map<string, number>();
  const outgoing = new Map<string, string[]>();
  const depthMap = new Map<string, number>();

  for (const nodeId of nodeIds) {
    incomingCount.set(nodeId, 0);
    depthMap.set(nodeId, 0);
  }

  for (const edge of edges) {
    if (!nodeIdSet.has(edge.source) || !nodeIdSet.has(edge.target)) {
      continue;
    }
    incomingCount.set(edge.target, (incomingCount.get(edge.target) || 0) + 1);
    const currentOutgoing = outgoing.get(edge.source) || [];
    currentOutgoing.push(edge.target);
    outgoing.set(edge.source, currentOutgoing);
  }

  const queue: string[] = nodeIds.filter((nodeId) => (incomingCount.get(nodeId) || 0) === 0);
  let cursor = 0;
  while (cursor < queue.length) {
    const sourceId = queue[cursor++];
    const sourceDepth = depthMap.get(sourceId) || 0;
    for (const targetId of outgoing.get(sourceId) || []) {
      const nextDepth = Math.max(depthMap.get(targetId) || 0, sourceDepth + 1);
      depthMap.set(targetId, nextDepth);
      const nextIncoming = (incomingCount.get(targetId) || 0) - 1;
      incomingCount.set(targetId, nextIncoming);
      if (nextIncoming === 0) {
        queue.push(targetId);
      }
    }
  }

  let fallbackDepth = Math.max(...Array.from(depthMap.values(), (value) => Number(value || 0)));
  for (const nodeId of nodeIds) {
    if ((incomingCount.get(nodeId) || 0) > 0) {
      fallbackDepth += 1;
      depthMap.set(nodeId, fallbackDepth);
    }
  }

  const lanesByDepth = new Map<number, number>();
  const positionById = new Map<string, { x: number; y: number }>();
  for (const nodeId of nodeIds) {
    const depth = Math.max(0, Number(depthMap.get(nodeId) || 0));
    const lane = lanesByDepth.get(depth) || 0;
    lanesByDepth.set(depth, lane + 1);
    positionById.set(nodeId, {
      x: originX + depth * horizontalGap,
      y: originY + lane * verticalGap,
    });
  }

  return nodes.map((node) => ({
    ...node,
    position: positionById.get(node.id) || node.position,
  }));
}

function definitionToNodes(definition: WorkflowDefinition): WorkflowCanvasNode[] {
  const steps = Array.isArray(definition.steps) ? definition.steps : [];
  const baseNodes = steps.map((step, index) => {
    const nodeType = inferNodeType(index, steps.length);
    return {
      id: step.step_id,
      type: nodeType,
      position: { x: 0, y: 0 },
      data: {
        label: String(step.description || step.output_key || step.step_id || "Step"),
        agentId: String(step.agent_id || "").trim(),
        agentName: String(step.agent_id || "").trim(),
        agentDescription: "",
        agentTags: [],
        toolIds: [],
        stepType: (step as any).step_type || "agent",
        stepConfig: (step as any).step_config || {},
        config: {},
        inputMapping: step.input_mapping || {},
        outputKey: String(step.output_key || "").trim() || `${step.step_id}_output`,
        description: step.description,
        inputDescription: nodeType === "trigger" ? "Specify input format…" : undefined,
        outputDescription: nodeType === "output" ? "Specify output format…" : undefined,
        timeoutS: (step as any).timeout_s,
        maxRetries: (step as any).max_retries,
        validationWarning: "",
      },
      runState: "idle" as const,
      runOutput: "",
    };
  });
  return applyAutoLayout(baseNodes, definitionToEdges(definition));
}

function definitionToEdges(definition: WorkflowDefinition): WorkflowCanvasEdge[] {
  const edges = Array.isArray(definition.edges) ? definition.edges : [];
  return edges.map((edge) => ({
    id: `${edge.from_step}->${edge.to_step}`,
    source: edge.from_step,
    target: edge.to_step,
    condition: edge.condition,
    animated: false,
  }));
}

const initialState = {
  workflowId: null,
  workflowName: "Untitled workflow",
  workflowDescription: "",
  activeTemplateId: null,
  nodes: [] as WorkflowCanvasNode[],
  edges: [] as WorkflowCanvasEdge[],
  selectedNodeId: null,
  viewport: defaultViewport,
  isDirty: false,
  run: defaultRunState,
};

const useWorkflowStore = create<WorkflowStoreState>()(
  persist(
    (set, get) => ({
      ...initialState,
      setMetadata: (payload) =>
        set((state) => ({
          ...state,
          workflowId:
            payload.workflowId !== undefined ? payload.workflowId : state.workflowId,
          workflowName:
            payload.workflowName !== undefined
              ? String(payload.workflowName || "").trim() || "Untitled workflow"
              : state.workflowName,
          workflowDescription:
            payload.workflowDescription !== undefined
              ? String(payload.workflowDescription || "")
              : state.workflowDescription,
          activeTemplateId:
            payload.activeTemplateId !== undefined
              ? payload.activeTemplateId
              : state.activeTemplateId,
          isDirty: true,
        })),
      setNodes: (nodes) =>
        set((state) => ({
          ...state,
          nodes,
          isDirty: true,
        })),
      setEdges: (edges) =>
        set((state) => ({
          ...state,
          edges,
          isDirty: true,
        })),
      setSelectedNodeId: (nodeId) => set({ selectedNodeId: nodeId }),
      setViewport: (viewport) =>
        set((state) => ({
          ...state,
          viewport: {
            x: viewport.x ?? state.viewport.x,
            y: viewport.y ?? state.viewport.y,
            zoom: viewport.zoom ?? state.viewport.zoom,
          },
        })),
      updateNodeData: (nodeId, patch, options) =>
        set((state) => ({
          ...state,
          nodes: state.nodes.map((node) =>
            node.id === nodeId
              ? {
                  ...node,
                  data: {
                    ...node.data,
                    ...patch,
                  },
                }
              : node,
          ),
          isDirty: options?.markDirty === false ? state.isDirty : true,
        })),
      updateEdgeCondition: (edgeId, condition) =>
        set((state) => ({
          ...state,
          edges: state.edges.map((edge) =>
            edge.id === edgeId ? { ...edge, condition: condition || undefined } : edge,
          ),
          isDirty: true,
        })),
      addNode: (node) =>
        set((state) => ({
          ...state,
          nodes: [...state.nodes, node],
          isDirty: true,
        })),
      removeNode: (nodeId) =>
        set((state) => ({
          ...state,
          nodes: state.nodes.filter((node) => node.id !== nodeId),
          edges: state.edges.filter((edge) => edge.source !== nodeId && edge.target !== nodeId),
          selectedNodeId: state.selectedNodeId === nodeId ? null : state.selectedNodeId,
          isDirty: true,
        })),
      addEdge: (edge) =>
        set((state) => ({
          ...state,
          edges: [...state.edges, edge],
          isDirty: true,
        })),
      removeEdge: (edgeId) =>
        set((state) => ({
          ...state,
          edges: state.edges.filter((edge) => edge.id !== edgeId),
          isDirty: true,
        })),
      loadDefinition: (definition, metadata) =>
        set((state) => ({
          ...state,
          workflowId:
            metadata?.workflowId !== undefined
              ? metadata.workflowId
              : definition.workflow_id || state.workflowId,
          workflowName: String(definition.name || "Untitled workflow"),
          workflowDescription: String(definition.description || ""),
          activeTemplateId:
            metadata?.activeTemplateId !== undefined
              ? metadata.activeTemplateId
              : state.activeTemplateId,
          nodes: definitionToNodes(definition),
          edges: definitionToEdges(definition),
          selectedNodeId: null,
          run: defaultRunState,
          isDirty: false,
        })),
      toDefinition: () => {
        const state = get();
        const steps = state.nodes.map((node) => ({
          step_id: node.id,
          agent_id: node.data.agentId,
          step_type: node.data.stepType || "agent",
          step_config: node.data.stepConfig || {},
          input_mapping: node.data.inputMapping,
          output_key: node.data.outputKey || `${node.id}_output`,
          description: node.data.description || node.data.label,
          ...(node.data.timeoutS ? { timeout_s: node.data.timeoutS } : {}),
          ...(node.data.maxRetries ? { max_retries: node.data.maxRetries } : {}),
        }));
        const edges = state.edges.map((edge) => ({
          from_step: edge.source,
          to_step: edge.target,
          condition: edge.condition || undefined,
        }));
        return {
          workflow_id: String(state.workflowId || "").trim() || `wf_${Date.now()}`,
          name: String(state.workflowName || "").trim() || "Untitled workflow",
          description: String(state.workflowDescription || "").trim(),
          steps,
          edges,
        };
      },
      markSaved: () => set({ isDirty: false }),
      reset: () => set({ ...initialState }),
      startRun: (runId) =>
        set((state) => ({
          ...state,
          run: {
            runId,
            status: "running",
            activeStepId: null,
            detail: null,
            stepResults: {},
          },
          nodes: state.nodes.map((node) => ({
            ...node,
            runState: "idle",
            runOutput: "",
          })),
        })),
      setRunStatus: (status) =>
        set((state) => ({
          ...state,
          run: {
            ...state.run,
            status,
          },
        })),
      setRunDetail: (detail) =>
        set((state) => ({
          ...state,
          run: {
            ...state.run,
            detail: detail ? String(detail) : null,
          },
        })),
      setActiveStep: (stepId) =>
        set((state) => ({
          ...state,
          run: {
            ...state.run,
            activeStepId: stepId,
          },
          edges: state.edges.map((edge) => ({
            ...edge,
            animated: Boolean(stepId && edge.target === stepId),
          })),
        })),
      setNodeRunState: (nodeId, runState, detail) =>
        set((state) => ({
          ...state,
          nodes: state.nodes.map((node) =>
            node.id === nodeId
              ? {
                  ...node,
                  runState,
                  runOutput: detail ? String(detail) : node.runOutput,
                }
              : node,
          ),
        })),
      appendStepOutput: (stepId, outputChunk) =>
        set((state) => {
          const chunk = String(outputChunk || "");
          if (!chunk.trim()) {
            return state;
          }
          return {
            ...state,
            nodes: state.nodes.map((node) =>
              node.id === stepId
                ? {
                    ...node,
                    runOutput: `${String(node.runOutput || "")}${chunk}`,
                  }
                : node,
            ),
          };
        }),
      setStepResult: (stepId, output, durationMs) =>
        set((state) => ({
          ...state,
          run: {
            ...state.run,
            stepResults: {
              ...state.run.stepResults,
              [stepId]: {
                output: String(output || ""),
                duration_ms: Math.max(0, Number(durationMs || 0)),
              },
            },
          },
          nodes: state.nodes.map((node) =>
            node.id === stepId
              ? {
                  ...node,
                  runOutput: String(output || ""),
                }
              : node,
          ),
        })),
      hydrateRunOutputs: (results) =>
        set((state) => {
          const nextStepResults: Record<string, { output: string; duration_ms: number }> = {};
          for (const row of results) {
            const stepId = String(row.step_id || "").trim();
            if (!stepId) {
              continue;
            }
            nextStepResults[stepId] = {
              output: String(row.output_preview || ""),
              duration_ms: Math.max(0, Number(row.duration_ms || 0)),
            };
          }
          return {
            ...state,
            run: {
              ...state.run,
              stepResults: {
                ...state.run.stepResults,
                ...nextStepResults,
              },
            },
            nodes: state.nodes.map((node) => {
              const result = nextStepResults[node.id];
              if (!result) {
                return node;
              }
              return {
                ...node,
                runOutput: result.output,
              };
            }),
          };
        }),
      clearRun: () =>
        set((state) => ({
          ...state,
          run: defaultRunState,
          edges: state.edges.map((edge) => ({ ...edge, animated: false })),
          nodes: state.nodes.map((node) => ({
            ...node,
            runState: "idle",
          })),
        })),
    }),
    {
      name: "maia.workflow.canvas.v1",
      partialize: (state) => ({
        workflowId: state.workflowId,
        workflowName: state.workflowName,
        workflowDescription: state.workflowDescription,
        activeTemplateId: state.activeTemplateId,
        nodes: state.nodes,
        edges: state.edges,
        selectedNodeId: state.selectedNodeId,
        viewport: state.viewport,
      }),
    },
  ),
);

export { useWorkflowStore, applyAutoLayout, definitionToEdges, definitionToNodes };
export type {
  StepType,
  WorkflowCanvasEdge,
  WorkflowCanvasNode,
  WorkflowCanvasNodeData,
  WorkflowCanvasNodeRunState,
  WorkflowCanvasNodeType,
  WorkflowRunState,
  WorkflowRunStatus,
  WorkflowViewport,
};
