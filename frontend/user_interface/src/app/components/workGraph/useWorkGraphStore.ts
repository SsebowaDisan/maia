import { create } from "zustand";

import {
  getAgentRunWorkGraph,
  getAgentRunWorkGraphReplayState,
  subscribeAgentEvents,
} from "../../../api/client/agent";
import type { AgentActivityEvent } from "../../types";
import type {
  WorkGraphEdge,
  WorkGraphFilters,
  WorkGraphNode,
  WorkGraphPayload,
  WorkGraphReplayState,
} from "./work_graph_types";

const WORK_GRAPH_STORAGE_KEY = "maia.work-graph.state.v1";

type WorkGraphStoreState = {
  runId: string | null;
  title: string;
  rootId: string;
  schema: string;
  nodes: WorkGraphNode[];
  edges: WorkGraphEdge[];
  activeNodeIds: string[];
  selectedNodeId: string | null;
  replayCursor: number;
  latestEventIndex: number;
  filters: WorkGraphFilters;
  evidenceFocusId: string | null;
  loading: boolean;
  streaming: boolean;
  error: string | null;
  seenEventIds: string[];
  lastEventNodeId: string | null;
  hydrateFromPayload: (payload: WorkGraphPayload) => void;
  hydrateFromReplayState: (payload: WorkGraphReplayState) => void;
  applyActivityEvent: (event: AgentActivityEvent) => void;
  applyActivityEvents: (events: AgentActivityEvent[]) => void;
  setSelectedNodeId: (nodeId: string | null) => void;
  setReplayCursor: (cursor: number) => void;
  setEvidenceFocusId: (evidenceId: string | null) => void;
  setLoading: (loading: boolean) => void;
  setStreaming: (streaming: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
};

type WorkGraphSyncOptions = {
  filters?: WorkGraphFilters;
  replay?: number;
};

type WorkGraphMindmapPayload = {
  map_type: "work_graph";
  kind: "work_graph";
  schema: string;
  run_id: string;
  title: string;
  root_id: string;
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
  filters: WorkGraphFilters;
};

function readString(value: unknown): string {
  return String(value || "").trim();
}

function readNumber(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function readRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object") {
    return value as Record<string, unknown>;
  }
  return {};
}

function readStringList(value: unknown, limit = 24): string[] {
  if (Array.isArray(value)) {
    return Array.from(
      new Set(
        value
          .map((item) => readString(item))
          .filter((item) => item.length > 0),
      ),
    ).slice(0, Math.max(1, limit));
  }
  const single = readString(value);
  return single ? [single] : [];
}

function normalizeStatus(value: unknown): WorkGraphNode["status"] {
  const normalized = readString(value).toLowerCase();
  if (normalized === "completed" || normalized === "success") {
    return "completed";
  }
  if (normalized === "failed" || normalized === "error") {
    return "failed";
  }
  if (normalized === "blocked" || normalized === "skipped") {
    return "blocked";
  }
  if (normalized === "in_progress" || normalized === "running" || normalized === "waiting") {
    return "running";
  }
  return "queued";
}

function statusPriority(value: WorkGraphNode["status"]): number {
  if (value === "failed") {
    return 5;
  }
  if (value === "blocked") {
    return 4;
  }
  if (value === "running") {
    return 3;
  }
  if (value === "completed") {
    return 2;
  }
  return 1;
}

function inferNodeType(eventType: string, family: string): string {
  const normalizedFamily = readString(family).toLowerCase();
  const normalizedType = readString(eventType).toLowerCase();
  if (normalizedType === "agent.handoff" || normalizedType === "role_handoff") {
    return "decision";
  }
  if (normalizedFamily === "browser") {
    return "browser_action";
  }
  if (normalizedFamily === "doc" || normalizedFamily === "pdf") {
    return "document_review";
  }
  if (normalizedFamily === "sheet") {
    return "spreadsheet_analysis";
  }
  if (normalizedFamily === "email") {
    return "email_draft";
  }
  if (normalizedFamily === "verify") {
    return "verification";
  }
  if (normalizedFamily === "approval") {
    return "approval";
  }
  if (normalizedFamily === "artifact") {
    return "artifact";
  }
  if (normalizedFamily === "api") {
    return "api_operation";
  }
  return "plan_step";
}

function asAgentActivityEvent(raw: unknown, runId: string): AgentActivityEvent | null {
  const row = readRecord(raw);
  const directEventType = readString(row["event_type"]);
  const directEventId = readString(row["event_id"]);
  if (directEventType && directEventId) {
    if (readString(row["run_id"]) && readString(row["run_id"]) !== runId) {
      return null;
    }
    return row as unknown as AgentActivityEvent;
  }
  const data = readRecord(row["data"]);
  const nestedType = readString(data["event_type"]);
  const nestedId = readString(data["event_id"]);
  if (nestedType && nestedId) {
    if (readString(data["run_id"]) && readString(data["run_id"]) !== runId) {
      return null;
    }
    return data as unknown as AgentActivityEvent;
  }
  return null;
}

function seedStateFromStorage(): Partial<WorkGraphStoreState> {
  if (typeof window === "undefined") {
    return {};
  }
  try {
    const parsed = JSON.parse(window.localStorage.getItem(WORK_GRAPH_STORAGE_KEY) || "{}") as Partial<WorkGraphStoreState>;
    return {
      runId: readString(parsed.runId) || null,
      title: readString(parsed.title),
      rootId: readString(parsed.rootId),
      schema: readString(parsed.schema) || "work_graph.v2",
      selectedNodeId: readString(parsed.selectedNodeId) || null,
      replayCursor: readNumber(parsed.replayCursor),
      latestEventIndex: readNumber(parsed.latestEventIndex),
      filters: readRecord(parsed.filters) as WorkGraphFilters,
      evidenceFocusId: readString(parsed.evidenceFocusId) || null,
    };
  } catch {
    return {};
  }
}

const persistedSeed = seedStateFromStorage();

const useWorkGraphStore = create<WorkGraphStoreState>((set, get) => ({
  runId: persistedSeed.runId ?? null,
  title: persistedSeed.title || "",
  rootId: persistedSeed.rootId || "",
  schema: persistedSeed.schema || "work_graph.v2",
  nodes: [],
  edges: [],
  activeNodeIds: [],
  selectedNodeId: persistedSeed.selectedNodeId || null,
  replayCursor: persistedSeed.replayCursor || 0,
  latestEventIndex: persistedSeed.latestEventIndex || 0,
  filters: persistedSeed.filters || {},
  evidenceFocusId: persistedSeed.evidenceFocusId || null,
  loading: false,
  streaming: false,
  error: null,
  seenEventIds: [],
  lastEventNodeId: null,
  hydrateFromPayload: (payload) => {
    const normalizedNodes = Array.isArray(payload.nodes) ? payload.nodes : [];
    const normalizedEdges = Array.isArray(payload.edges) ? payload.edges : [];
    const seenEventIds = Array.from(
      new Set(
        normalizedNodes.flatMap((node) => readStringList(node.event_refs)).filter((item) => item.length > 0),
      ),
    );
    const lastNode = [...normalizedNodes]
      .sort((left, right) => readNumber(left.event_index_end) - readNumber(right.event_index_end))
      .pop();
    set({
      runId: readString(payload.run_id) || null,
      title: readString(payload.title),
      rootId: readString(payload.root_id),
      schema: readString(payload.schema) || "work_graph.v2",
      nodes: normalizedNodes,
      edges: normalizedEdges,
      filters: payload.filters || {},
      seenEventIds,
      lastEventNodeId: readString(lastNode?.id) || null,
      error: null,
    });
  },
  hydrateFromReplayState: (payload) => {
    const latest = readNumber(payload.latest_event_index);
    const activeNodeIds = readStringList(payload.work_graph?.active_node_ids);
    set({
      latestEventIndex: latest,
      replayCursor: latest,
      activeNodeIds,
    });
  },
  applyActivityEvent: (event) =>
    set((state) => {
      const eventId = readString(event.event_id);
      if (!eventId || state.seenEventIds.includes(eventId)) {
        return state;
      }
      const data = readRecord(event.data || event.metadata);
      const graphNodeIds = [
        ...readStringList(data["graph_node_ids"]),
        ...readStringList(data["graph_node_id"]),
        ...readStringList(event.graph_node_id),
      ];
      const nodeIds = Array.from(new Set(graphNodeIds.filter((item) => item.length > 0)));
      if (nodeIds.length <= 0) {
        return {
          ...state,
          seenEventIds: [...state.seenEventIds, eventId],
        };
      }
      const eventIndex = Math.max(
        readNumber(event.event_index),
        readNumber(data["event_index"]),
        readNumber(event.seq),
      );
      const status = normalizeStatus(event.status || data["status"]);
      const family = readString(data["event_family"]);
      const nextNodesById = new Map(state.nodes.map((node) => [node.id, { ...node }]));

      nodeIds.forEach((nodeId) => {
        const current = nextNodesById.get(nodeId);
        if (!current) {
          nextNodesById.set(nodeId, {
            id: nodeId,
            title: readString(event.title) || readString(event.event_type) || nodeId,
            detail: readString(event.detail),
            node_type: inferNodeType(readString(event.event_type), family),
            status,
            agent_id: readString(data["agent_id"]) || null,
            agent_role: readString(data["agent_role"] || data["owner_role"]) || null,
            agent_label: readString(data["agent_label"]) || null,
            agent_color: readString(data["agent_color"]) || null,
            event_index_start: eventIndex || null,
            event_index_end: eventIndex || null,
            scene_refs: readStringList(data["scene_refs"] || data["scene_ref"]),
            evidence_refs: readStringList(data["evidence_refs"] || data["evidence_ids"]),
            artifact_refs: readStringList(data["artifact_refs"] || data["artifact_ids"]),
            event_refs: [eventId],
            metadata: {
              provisional: true,
              event_family: family,
            },
          });
          return;
        }
        current.title = readString(event.title) || current.title;
        current.detail = readString(event.detail) || current.detail;
        current.node_type = current.node_type || inferNodeType(readString(event.event_type), family);
        if (statusPriority(status) >= statusPriority(current.status)) {
          current.status = status;
        }
        current.event_index_start = Math.min(readNumber(current.event_index_start) || eventIndex, eventIndex || 0) || null;
        current.event_index_end = Math.max(readNumber(current.event_index_end), eventIndex) || current.event_index_end;
        current.scene_refs = Array.from(
          new Set([...readStringList(current.scene_refs), ...readStringList(data["scene_refs"] || data["scene_ref"])]),
        );
        current.evidence_refs = Array.from(
          new Set([...readStringList(current.evidence_refs), ...readStringList(data["evidence_refs"] || data["evidence_ids"])]),
        );
        current.artifact_refs = Array.from(
          new Set([...readStringList(current.artifact_refs), ...readStringList(data["artifact_refs"] || data["artifact_ids"])]),
        );
        current.event_refs = Array.from(new Set([...readStringList(current.event_refs), eventId]));
      });

      const primaryNodeId = nodeIds[0];
      const nextEdges = [...state.edges];
      if (state.lastEventNodeId && state.lastEventNodeId !== primaryNodeId) {
        const edgeId = `hierarchy:${state.lastEventNodeId}->${primaryNodeId}:stream`;
        if (!nextEdges.some((edge) => edge.id === edgeId)) {
          nextEdges.push({
            id: edgeId,
            source: state.lastEventNodeId,
            target: primaryNodeId,
            edge_family: "hierarchy",
            relation: "stream_sequence",
            event_index: eventIndex || null,
          });
        }
      }

      return {
        ...state,
        nodes: Array.from(nextNodesById.values()),
        edges: nextEdges,
        activeNodeIds: nodeIds,
        latestEventIndex: Math.max(state.latestEventIndex, eventIndex),
        replayCursor: Math.max(state.replayCursor, eventIndex),
        seenEventIds: [...state.seenEventIds, eventId],
        lastEventNodeId: primaryNodeId,
      };
    }),
  applyActivityEvents: (events) => {
    for (const event of events) {
      get().applyActivityEvent(event);
    }
  },
  setSelectedNodeId: (selectedNodeId) => set({ selectedNodeId: selectedNodeId || null }),
  setReplayCursor: (replayCursor) => set({ replayCursor: Math.max(0, readNumber(replayCursor)) }),
  setEvidenceFocusId: (evidenceFocusId) => set({ evidenceFocusId: readString(evidenceFocusId) || null }),
  setLoading: (loading) => set({ loading: Boolean(loading) }),
  setStreaming: (streaming) => set({ streaming: Boolean(streaming) }),
  setError: (error) => set({ error: error ? String(error) : null }),
  reset: () =>
    set({
      runId: null,
      title: "",
      rootId: "",
      schema: "work_graph.v2",
      nodes: [],
      edges: [],
      activeNodeIds: [],
      selectedNodeId: null,
      replayCursor: 0,
      latestEventIndex: 0,
      filters: {},
      evidenceFocusId: null,
      loading: false,
      streaming: false,
      error: null,
      seenEventIds: [],
      lastEventNodeId: null,
    }),
}));

useWorkGraphStore.subscribe((state) => {
  if (typeof window === "undefined") {
    return;
  }
  const payload = {
    runId: state.runId,
    title: state.title,
    rootId: state.rootId,
    schema: state.schema,
    selectedNodeId: state.selectedNodeId,
    replayCursor: state.replayCursor,
    latestEventIndex: state.latestEventIndex,
    filters: state.filters,
    evidenceFocusId: state.evidenceFocusId,
  };
  window.localStorage.setItem(WORK_GRAPH_STORAGE_KEY, JSON.stringify(payload));
});

async function hydrateWorkGraphRun(runId: string, options?: WorkGraphSyncOptions): Promise<void> {
  if (!runId) {
    useWorkGraphStore.getState().reset();
    return;
  }
  useWorkGraphStore.getState().setLoading(true);
  try {
    const payload = await getAgentRunWorkGraph(runId, options?.filters);
    useWorkGraphStore.getState().hydrateFromPayload(payload);
    const replayState = await getAgentRunWorkGraphReplayState(runId, options?.filters);
    useWorkGraphStore.getState().hydrateFromReplayState(replayState);
    useWorkGraphStore.getState().setError(null);
  } catch (error) {
    useWorkGraphStore.getState().setError(String(error || "Unable to load work graph."));
  } finally {
    useWorkGraphStore.getState().setLoading(false);
  }
}

function startWorkGraphRunSync(runId: string, options?: WorkGraphSyncOptions): () => void {
  if (!runId) {
    useWorkGraphStore.getState().reset();
    return () => {};
  }
  void hydrateWorkGraphRun(runId, options);
  useWorkGraphStore.getState().setStreaming(true);
  const unsubscribe = subscribeAgentEvents({
    runId,
    replay: typeof options?.replay === "number" ? options.replay : 0,
    onEvent: (event) => {
      const normalized = asAgentActivityEvent(event, runId);
      if (!normalized) {
        return;
      }
      useWorkGraphStore.getState().applyActivityEvent(normalized);
    },
    onError: () => {
      useWorkGraphStore.getState().setError("Live work-graph stream disconnected.");
    },
  });
  return () => {
    unsubscribe();
    useWorkGraphStore.getState().setStreaming(false);
  };
}

function buildWorkGraphMindmapPayload(state: {
  runId: string | null;
  title: string;
  rootId: string;
  schema: string;
  nodes: WorkGraphNode[];
  edges: WorkGraphEdge[];
  filters: WorkGraphFilters;
}): WorkGraphMindmapPayload | null {
  if (!state.runId || !state.rootId || state.nodes.length <= 0) {
    return null;
  }
  return {
    map_type: "work_graph",
    kind: "work_graph",
    schema: state.schema || "work_graph.v2",
    run_id: state.runId,
    title: state.title || "Work Graph",
    root_id: state.rootId,
    nodes: state.nodes.map((node) => ({
      ...node,
      type: node.node_type || "plan_step",
      text: node.detail || "",
    })),
    edges: state.edges.map((edge) => ({
      ...edge,
      type: edge.edge_family === "hierarchy" ? "hierarchy" : "dependency",
    })),
    filters: state.filters || {},
  };
}

export { buildWorkGraphMindmapPayload, hydrateWorkGraphRun, startWorkGraphRunSync, useWorkGraphStore };
export type { WorkGraphMindmapPayload };

