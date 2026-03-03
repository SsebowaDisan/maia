export type ChatAttachment = {
  name: string;
  fileId?: string;
};

export type ChatTurn = {
  user: string;
  assistant: string;
  attachments?: ChatAttachment[];
  info?: string;
  plot?: Record<string, unknown> | null;
  mode?: "ask" | "company_agent";
  actionsTaken?: AgentActionRecord[];
  sourcesUsed?: AgentSourceRecord[];
  nextRecommendedSteps?: string[];
  activityRunId?: string | null;
  activityEvents?: AgentActivityEvent[];
  needsHumanReview?: boolean;
  humanReviewNotes?: string | null;
  webSummary?: Record<string, unknown>;
  infoPanel?: Record<string, unknown>;
};

export type AgentActionRecord = {
  tool_id: string;
  action_class: "read" | "draft" | "execute";
  status: "success" | "failed" | "skipped";
  summary: string;
  started_at?: string;
  ended_at?: string;
  metadata?: Record<string, unknown>;
};

export type AgentSourceRecord = {
  source_type: string;
  label: string;
  url?: string | null;
  file_id?: string | null;
  score?: number | null;
  metadata?: Record<string, unknown>;
};

export type AgentActivityEvent = {
  event_schema_version?: string;
  event_id: string;
  run_id: string;
  seq?: number;
  ts?: string;
  type?: string;
  stage?: string;
  status?: string;
  event_type: string;
  title: string;
  detail: string;
  timestamp: string;
  data?: Record<string, unknown>;
  snapshot_ref?: string | null;
  metadata: Record<string, unknown>;
};

export type CitationHighlightBox = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type CitationFocus = {
  fileId?: string;
  sourceName: string;
  page?: string;
  extract: string;
  evidenceId?: string;
  highlightBoxes?: CitationHighlightBox[];
};
