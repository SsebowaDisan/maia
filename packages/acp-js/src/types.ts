// ─── ACP v1 Type Definitions ────────────────────────────────────────────────
// These types map 1:1 to the JSON Schema definitions in acp-spec/schema/

export type ACPVersion = "1.0";

// ── Intents ──────────────────────────────────────────────────────────────────

export type MessageIntent =
  | "propose"
  | "challenge"
  | "clarify"
  | "review"
  | "handoff"
  | "summarize"
  | "agree"
  | "escalate";

// ── Mood ─────────────────────────────────────────────────────────────────────

export type AgentMood =
  | "neutral"
  | "confident"
  | "uncertain"
  | "excited"
  | "concerned"
  | "focused";

export type DeliveryStatus =
  | "draft"
  | "queued"
  | "sent"
  | "delivered"
  | "acknowledged"
  | "failed";

export type AgentAvailability =
  | "available"
  | "focused"
  | "busy"
  | "offline";

export type TaskLifecycleStatus =
  | "proposed"
  | "accepted"
  | "in_progress"
  | "blocked"
  | "completed"
  | "rejected";

// ── Activity ─────────────────────────────────────────────────────────────────

export type ActivityType =
  | "thinking"
  | "searching"
  | "reading"
  | "writing"
  | "browsing"
  | "coding"
  | "analyzing"
  | "tool_calling"
  | "waiting"
  | "reviewing"
  | "idle"
  | "error";

// ── Review Verdict ───────────────────────────────────────────────────────────

export type ReviewVerdict = "approve" | "revise" | "reject" | "escalate";

// ── Artifact Kind ────────────────────────────────────────────────────────────

export type ArtifactKind =
  | "text"
  | "markdown"
  | "json"
  | "csv"
  | "html"
  | "code"
  | "image"
  | "pdf"
  | "url"
  | "binary";

// ── Event Types ──────────────────────────────────────────────────────────────

export type EventType =
  | "message"
  | "handoff"
  | "review"
  | "artifact"
  | "event"
  | "capabilities";

// ── Core Structures ──────────────────────────────────────────────────────────

export interface ACPEvent<T = unknown> {
  acp_version: ACPVersion;
  run_id: string;
  agent_id: string;
  event_type: EventType;
  timestamp: string;
  sequence?: number;
  parent_event_id?: string;
  payload: T;
}

export interface ACPMessage {
  from: string;
  to: string;
  intent: MessageIntent;
  content: string;
  artifacts?: ACPArtifact[];
  context?: MessageContext;
  thinking?: string;
  mood?: AgentMood;
}

export interface MessageContext {
  message_id?: string;
  run_id?: string;
  step?: string;
  thread_id?: string;
  in_reply_to?: string;
  task_id?: string;
  task_title?: string;
  handoff_id?: string;
  review_id?: string;
  channel?: "direct" | "thread" | "broadcast";
  mentions?: string[];
  requires_ack?: boolean;
  delivery_status?: DeliveryStatus;
  acked_by?: string[];
  [key: string]: unknown;
}

export interface ACPHandoff {
  from: string;
  to: string;
  task: HandoffTask;
  handoff_id?: string;
  status?: TaskLifecycleStatus;
  requires_ack?: boolean;
  accepted_by?: string;
  declined_reason?: string;
  context?: Record<string, unknown>;
  artifacts?: ACPArtifact[];
  prior_steps?: PriorStep[];
}

export interface HandoffTask {
  task_id?: string;
  thread_id?: string;
  description: string;
  constraints?: string[];
  definition_of_done?: string;
  deadline_seconds?: number;
  priority?: "low" | "normal" | "high" | "critical";
  owner_agent_id?: string;
  status?: TaskLifecycleStatus;
  blockers?: string[];
}

export interface PriorStep {
  agent_id: string;
  summary: string;
  status: "completed" | "partial" | "failed";
}

export interface ACPReview {
  reviewer: string;
  author: string;
  artifact_id?: string;
  verdict: ReviewVerdict;
  score?: number;
  feedback?: string;
  revision_instructions?: string;
  strengths?: string[];
  issues?: ReviewIssue[];
  round?: number;
  max_rounds?: number;
}

export interface ReviewIssue {
  severity: "minor" | "major" | "critical";
  description: string;
  location?: string;
}

export interface ACPArtifact {
  artifact_id: string;
  kind: ArtifactKind;
  title?: string;
  content: string;
  content_url?: string;
  mime_type?: string;
  size_bytes?: number;
  checksum?: string;
  metadata?: Record<string, unknown>;
  version?: number;
  parent_artifact_id?: string;
}

export interface ACPActivity {
  agent_id: string;
  activity: ActivityType;
  detail?: string;
  tool?: ToolActivity;
  browser?: BrowserActivity;
  progress?: ProgressInfo;
  cost?: CostInfo;
}

export interface ToolActivity {
  tool_id: string;
  tool_name?: string;
  connector_id?: string;
  input_summary?: string;
  output_summary?: string;
  status: "started" | "running" | "completed" | "failed";
}

export interface BrowserActivity {
  url: string;
  title?: string;
  screenshot_url?: string;
  action?: "navigate" | "click" | "type" | "scroll" | "extract";
}

export interface ProgressInfo {
  current: number;
  total: number;
  percentage?: number;
}

export interface CostInfo {
  tokens_used: number;
  cost_usd: number;
  model?: string;
}

export interface AgentPresence {
  availability?: AgentAvailability;
  status_text?: string;
  current_focus?: string;
  current_task_id?: string;
  active_task_count?: number;
  last_seen_at?: string;
}

export interface DeliveryReceipt {
  status: DeliveryStatus;
  delivered_at?: string;
  acknowledged_at?: string;
  recipient?: string;
  error?: string;
}

export interface ACPCapabilities {
  agent_id: string;
  name: string;
  description?: string;
  role?: string;
  personality?: AgentPersonality;
  skills: AgentSkill[];
  connectors?: string[];
  accepts_intents?: MessageIntent[];
  max_concurrent_tasks?: number;
  presence?: AgentPresence;
  cost_per_invocation?: CostInfo;
}

export interface AgentPersonality {
  style?: "concise" | "detailed" | "conversational" | "formal" | "creative";
  traits?: string[];
  avatar_color?: string;
  avatar_emoji?: string;
}

export interface AgentSkill {
  skill_id: string;
  description: string;
  input_schema?: Record<string, unknown>;
  output_schema?: Record<string, unknown>;
}

// ── Client Options ───────────────────────────────────────────────────────────

export interface ACPClientOptions {
  agentId: string;
  name?: string;
  role?: string;
  personality?: AgentPersonality;
  streamUrl?: string;
  transport?: ACPTransport;
  registry?: ACPRegistryLike;
  onEvent?: (event: ACPEvent) => void;
  onError?: (error: Error) => void;
}

export interface ACPTransport {
  deliver<T = unknown>(
    event: ACPEvent<T>,
    options?: { recipient?: string; timeoutMs?: number },
  ): Promise<DeliveryReceipt> | DeliveryReceipt;
}

export interface ACPRegistryLike {
  upsertCapabilities(capabilities: ACPCapabilities): void;
  updatePresence(agentId: string, presence: AgentPresence): void;
  getCapabilities(agentId: string): ACPCapabilities | undefined;
  listAgents(): ACPCapabilities[];
  listAvailableAgents(intent?: MessageIntent): ACPCapabilities[];
  resolveRecipient(input: {
    to?: string;
    intent?: MessageIntent;
    excludeAgentId?: string;
  }): ACPCapabilities | undefined;
}

// ── Typed Event Map ──────────────────────────────────────────────────────────

export interface ACPEventMap {
  message: ACPEvent<ACPMessage>;
  handoff: ACPEvent<ACPHandoff>;
  review: ACPEvent<ACPReview>;
  artifact: ACPEvent<ACPArtifact>;
  event: ACPEvent<ACPActivity>;
  capabilities: ACPEvent<ACPCapabilities>;
  "*": ACPEvent;
}
