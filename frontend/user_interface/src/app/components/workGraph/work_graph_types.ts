export type WorkGraphNodeStatus = "queued" | "running" | "completed" | "failed" | "blocked";

export type WorkGraphEdgeFamily = "hierarchy" | "dependency" | "evidence" | "verification" | "handoff";

export type WorkGraphNode = {
  id: string;
  title: string;
  detail?: string;
  node_type?: string;
  status?: WorkGraphNodeStatus;
  agent_id?: string | null;
  agent_role?: string | null;
  agent_label?: string | null;
  agent_color?: string | null;
  confidence?: number | null;
  progress?: number | null;
  started_at?: string | null;
  ended_at?: string | null;
  duration_ms?: number | null;
  event_index_start?: number | null;
  event_index_end?: number | null;
  evidence_refs?: string[];
  artifact_refs?: string[];
  scene_refs?: string[];
  event_refs?: string[];
  evidence_count?: number;
  artifact_count?: number;
  scene_count?: number;
  metadata?: Record<string, unknown>;
};

export type WorkGraphEdge = {
  id: string;
  source: string;
  target: string;
  edge_family: WorkGraphEdgeFamily;
  relation?: string;
  event_index?: number | null;
  weight?: number;
  metadata?: Record<string, unknown>;
};

export type WorkGraphFilters = {
  agent_role?: string;
  status?: string;
  event_index_min?: number;
  event_index_max?: number;
};

export type WorkGraphPayload = {
  version?: number;
  map_type?: string;
  kind?: string;
  schema?: string;
  run_id: string;
  title?: string;
  root_id: string;
  nodes: WorkGraphNode[];
  edges: WorkGraphEdge[];
  graph?: Record<string, unknown>;
  filters?: WorkGraphFilters;
};

export type WorkGraphNodeRange = {
  node_id: string;
  status?: string;
  agent_role?: string | null;
  event_index_start?: number | null;
  event_index_end?: number | null;
  scene_refs?: string[];
  event_refs?: string[];
};

export type WorkGraphReplayState = {
  run_id: string;
  latest_event_index?: number;
  graph_snapshots?: Array<Record<string, unknown>>;
  evidence_snapshots?: Array<Record<string, unknown>>;
  artifact_snapshots?: Array<Record<string, unknown>>;
  work_graph?: {
    run_id: string;
    root_id?: string;
    filters?: WorkGraphFilters;
    active_node_ids?: string[];
    node_ranges?: WorkGraphNodeRange[];
  };
};

