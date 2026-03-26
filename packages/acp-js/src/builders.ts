// ─── ACP Message Builders ───────────────────────────────────────────────────
// Convenience functions to create well-formed ACP payloads.

import type {
  ACPMessage,
  ACPHandoff,
  ACPReview,
  ACPArtifact,
  ACPActivity,
  ACPCapabilities,
  ACPEvent,
  MessageIntent,
  ReviewVerdict,
  ActivityType,
  ArtifactKind,
  AgentPersonality,
  AgentSkill,
  HandoffTask,
  AgentPresence,
  DeliveryStatus,
} from "./types";

let _sequence = 0;

function nextSequence(): number {
  return _sequence++;
}

function now(): string {
  return new Date().toISOString();
}

function uid(): string {
  return `${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

// ── Envelope ─────────────────────────────────────────────────────────────────

export function envelope<T>(
  agentId: string,
  runId: string,
  eventType: string,
  payload: T,
  parentEventId?: string,
): ACPEvent<T> {
  return {
    acp_version: "1.0",
    run_id: runId,
    agent_id: agentId,
    event_type: eventType as ACPEvent["event_type"],
    timestamp: now(),
    sequence: nextSequence(),
    parent_event_id: parentEventId,
    payload,
  };
}

// ── Message ──────────────────────────────────────────────────────────────────

export function message(opts: {
  from: string;
  to: string;
  intent: MessageIntent;
  content: string;
  thinking?: string;
  mood?: ACPMessage["mood"];
  messageId?: string;
  threadId?: string;
  inReplyTo?: string;
  taskId?: string;
  taskTitle?: string;
  handoffId?: string;
  reviewId?: string;
  channel?: "direct" | "thread" | "broadcast";
  mentions?: string[];
  requiresAck?: boolean;
  deliveryStatus?: DeliveryStatus;
  ackedBy?: string[];
  artifacts?: ACPArtifact[];
}): ACPMessage {
  return {
    from: opts.from,
    to: opts.to,
    intent: opts.intent,
    content: opts.content,
    thinking: opts.thinking,
    mood: opts.mood,
    artifacts: opts.artifacts ?? [],
    context: {
      message_id: opts.messageId ?? `msg_${uid()}`,
      thread_id: opts.threadId,
      in_reply_to: opts.inReplyTo,
      task_id: opts.taskId,
      task_title: opts.taskTitle,
      handoff_id: opts.handoffId,
      review_id: opts.reviewId,
      channel: opts.channel ?? (opts.to === "agent://broadcast" ? "broadcast" : "direct"),
      mentions: opts.mentions,
      requires_ack: opts.requiresAck,
      delivery_status: opts.deliveryStatus,
      acked_by: opts.ackedBy,
    },
  };
}

// ── Handoff ──────────────────────────────────────────────────────────────────

export function handoff(opts: {
  from: string;
  to: string;
  task: HandoffTask | string;
  handoffId?: string;
  status?: ACPHandoff["status"];
  requiresAck?: boolean;
  acceptedBy?: string;
  declinedReason?: string;
  context?: Record<string, unknown>;
  artifacts?: ACPArtifact[];
}): ACPHandoff {
  const task: HandoffTask =
    typeof opts.task === "string"
      ? { description: opts.task, priority: "normal", task_id: `task_${uid()}` }
      : opts.task;

  return {
    from: opts.from,
    to: opts.to,
    task,
    handoff_id: opts.handoffId ?? `handoff_${uid()}`,
    status: opts.status ?? task.status ?? "proposed",
    requires_ack: opts.requiresAck,
    accepted_by: opts.acceptedBy,
    declined_reason: opts.declinedReason,
    context: opts.context ?? {},
    artifacts: opts.artifacts ?? [],
    prior_steps: [],
  };
}

// ── Review ───────────────────────────────────────────────────────────────────

export function review(opts: {
  reviewer: string;
  author: string;
  verdict: ReviewVerdict;
  feedback?: string;
  score?: number;
  revisionInstructions?: string;
  strengths?: string[];
  issues?: ACPReview["issues"];
  round?: number;
}): ACPReview {
  return {
    reviewer: opts.reviewer,
    author: opts.author,
    verdict: opts.verdict,
    feedback: opts.feedback,
    score: opts.score,
    revision_instructions: opts.revisionInstructions,
    strengths: opts.strengths,
    issues: opts.issues,
    round: opts.round ?? 1,
    max_rounds: 3,
  };
}

// ── Artifact ─────────────────────────────────────────────────────────────────

export function artifact(opts: {
  kind: ArtifactKind;
  title: string;
  content: string;
  mimeType?: string;
  metadata?: Record<string, unknown>;
}): ACPArtifact {
  return {
    artifact_id: `artifact_${uid()}`,
    kind: opts.kind,
    title: opts.title,
    content: opts.content,
    mime_type: opts.mimeType,
    metadata: opts.metadata,
    version: 1,
  };
}

// ── Activity ─────────────────────────────────────────────────────────────────

export function activity(opts: {
  agentId: string;
  activity: ActivityType;
  detail?: string;
  tool?: ACPActivity["tool"];
  browser?: ACPActivity["browser"];
  progress?: ACPActivity["progress"];
  cost?: ACPActivity["cost"];
}): ACPActivity {
  return {
    agent_id: opts.agentId,
    activity: opts.activity,
    detail: opts.detail,
    tool: opts.tool,
    browser: opts.browser,
    progress: opts.progress,
    cost: opts.cost,
  };
}

// ── Capabilities ─────────────────────────────────────────────────────────────

export function capabilities(opts: {
  agentId: string;
  name: string;
  description?: string;
  role?: string;
  personality?: AgentPersonality;
  skills: AgentSkill[];
  connectors?: string[];
  acceptsIntents?: ACPCapabilities["accepts_intents"];
  maxConcurrentTasks?: number;
  presence?: AgentPresence;
}): ACPCapabilities {
  return {
    agent_id: opts.agentId,
    name: opts.name,
    description: opts.description,
    role: opts.role,
    personality: opts.personality,
    skills: opts.skills,
    connectors: opts.connectors ?? [],
    accepts_intents: opts.acceptsIntents ?? [],
    max_concurrent_tasks: opts.maxConcurrentTasks ?? 1,
    presence: opts.presence,
  };
}
