export type MindmapNode = {
  id: string;
  title: string;
  text?: string;
  type?: string;
  node_type?: string;
  page?: string | null;
  page_ref?: string | null;
  source_id?: string;
  source_name?: string;
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
  map_type?: "structure" | "evidence";
  kind?: string;
  title?: string;
  root_id?: string;
  nodes?: MindmapNode[];
  edges?: MindmapEdge[];
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
  onAskNode?: (payload: FocusNodePayload) => void;
  onSaveMap?: (payload: MindmapPayload) => void;
  onShareMap?: (payload: MindmapPayload) => Promise<string | void> | string | void;
  onMapTypeChange?: (mapType: "structure" | "evidence") => void;
};
