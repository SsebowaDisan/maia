export type ChatAttachment = {
  name: string;
  fileId?: string;
};

export type ClarificationPrompt = {
  runId: string;
  originalRequest: string;
  questions: string[];
  missingRequirements: string[];
  agentMode: "ask" | "company_agent" | "deep_search";
  accessMode: "restricted" | "full_access";
};

export type TrustVerdict = {
  trust_score: number;
  gate_color: "green" | "amber" | "red";
  reason: string;
  contested_claim_count: number;
  resolved_claim_count: number;
};

export type ClaimMatrixSummary = {
  overall_trust_score: number;
  overall_gate_color: "green" | "amber" | "red";
  claim_count: number;
  contested_count: number;
  claims: Array<{
    claim: string;
    trust_score: number;
    gate_color: "green" | "amber" | "red";
    corroboration_score: number;
    credibility_score: number;
    source_diversity_score: number;
    contradictions: Record<string, unknown>[];
  }>;
};

export type ResearchTreeBranch = {
  branch_label: string;
  sub_question: string;
  preferred_providers: string[];
  result_count?: number;
};

export type ChatTurn = {
  user: string;
  assistant: string;
  attachments?: ChatAttachment[];
  info?: string;
  plot?: Record<string, unknown> | null;
  mode?: "ask" | "company_agent" | "deep_search" | "web_search";
  actionsTaken?: AgentActionRecord[];
  sourcesUsed?: AgentSourceRecord[];
  sourceUsage?: SourceUsageRecord[];
  nextRecommendedSteps?: string[];
  activityRunId?: string | null;
  activityEvents?: AgentActivityEvent[];
  needsHumanReview?: boolean;
  humanReviewNotes?: string | null;
  webSummary?: Record<string, unknown>;
  infoPanel?: Record<string, unknown>;
  mindmap?: Record<string, unknown>;
  trustVerdict?: TrustVerdict | null;
  claimMatrix?: ClaimMatrixSummary | null;
  researchTree?: ResearchTreeBranch[] | null;
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

export type SourceUsageRecord = {
  source_id: string;
  source_name: string;
  source_type: string;
  retrieved_count: number;
  cited_count: number;
  max_strength_score: number;
  avg_strength_score: number;
  citation_share: number;
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
  event_family?: string;
  event_priority?: string;
  event_render_mode?: string;
  event_replay_importance?: string;
  replay_importance?: string;
  event_index?: number;
  graph_node_id?: string | null;
  scene_ref?: string | null;
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
  sourceUrl?: string;
  sourceType?: "file" | "website";
  sourceName: string;
  page?: string;
  extract: string;
  claimText?: string;
  evidenceId?: string;
  highlightBoxes?: CitationHighlightBox[];
  unitId?: string;
  selector?: string;
  charStart?: number;
  charEnd?: number;
  graphNodeIds?: string[];
  sceneRefs?: string[];
  eventRefs?: string[];
  matchQuality?: string;
  strengthScore?: number;
  strengthTier?: number;
};
