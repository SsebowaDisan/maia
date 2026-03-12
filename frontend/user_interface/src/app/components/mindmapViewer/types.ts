export type MindmapMapType = "structure" | "evidence" | "work_graph" | "context_mindmap";

export type MindmapNode = {
  id: string;
  title: string;
  text?: string;
  summary?: string;
  synthetic?: boolean;
  type?: string;
  node_type?: string;
  page?: string | null;
  page_ref?: string | null;
  source_id?: string;
  source_name?: string;
  source_type?: string;
  status?: string;
  node_role?: string;
  tool_id?: string;
  action_class?: string;
  confidence?: number | null;
  source_count?: number | null;
  citation_count?: number | null;
  children?: string[];
};

export type MindmapEdge = {
  id?: string;
  source: string;
  target: string;
  type?: string;
  weight?: number;
};

export type ReasoningNode = {
  id: string;
  label: string;
  kind?: string;
  node_id?: string;
};

export type ReasoningEdge = {
  id?: string;
  source: string;
  target: string;
};

export type MindmapPayload = {
  version?: number;
  map_type?: MindmapMapType;
  kind?: string;
  title?: string;
  subtitle?: string;
  artifact_summary?: string;
  view_hint?: string;
  root_id?: string;
  graph?: Record<string, unknown>;
  settings?: Record<string, unknown>;
  tree?: Record<string, unknown>;
  nodes?: MindmapNode[];
  edges?: MindmapEdge[];
  available_map_types?: string[];
  variants?: Record<string, unknown>;
  reasoning_map?: {
    layout?: string;
    nodes?: ReasoningNode[];
    edges?: ReasoningEdge[];
  };
};

export type FocusNodePayload = {
  nodeId: string;
  title: string;
  text: string;
  pageRef?: string;
  sourceId?: string;
  sourceName?: string;
};

export type MindMapViewerProps = {
  payload?: Record<string, unknown> | null;
  conversationId?: string | null;
  maxDepth?: number;
  viewerHeight?: number;
  onAskNode?: (payload: FocusNodePayload) => void;
  onFocusNode?: (payload: FocusNodePayload) => void;
  onSaveMap?: (payload: MindmapPayload) => void;
  onShareMap?: (payload: MindmapPayload) => Promise<string | void> | string | void;
  onMapTypeChange?: (mapType: MindmapMapType) => void;
};
