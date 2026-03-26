/**
 * Brain runtime types — agents, steps, conversations, context, results.
 */
import type { ACPEvent, AgentPersonality } from "@maia/acp";

// ── Agent ────────────────────────────────────────────────────────────────────

export interface AgentDefinition {
  /** Agent ID (e.g., "agent://researcher"). */
  id: string;
  /** Display name. */
  name: string;
  /** Role in the team. */
  role: string;
  /** System instructions for the LLM. */
  instructions: string;
  /** Tools this agent can use. */
  tools?: string[];
  /** Personality for Theatre rendering. */
  personality?: AgentPersonality;
}

// ── Configuration ────────────────────────────────────────────────────────────

export interface BrainOptions {
  /** Agents available to the Brain. */
  agents: AgentDefinition[];
  /** LLM configuration. */
  llm: LLMConfig;
  /** Maximum review rounds per step (default: 3). */
  maxReviewRounds?: number;
  /** Maximum conversation turns per step (default: 8). */
  maxConversationTurns?: number;
  /** Maximum total steps (default: 20). */
  maxSteps?: number;
  /** Budget limit in USD (default: no limit). */
  budgetUsd?: number;
  /** Event callback — called for every ACP event. */
  onEvent?: (event: ACPEvent) => void;
}

export interface LLMConfig {
  /** API key for the LLM provider. */
  apiKey: string;
  /** Base URL (default: https://api.openai.com/v1). */
  baseUrl?: string;
  /** Model name (default: gpt-4o). */
  model?: string;
  /** Temperature (default: 0.3). */
  temperature?: number;
  /** Max tokens per call. */
  maxTokens?: number;
}

// ── Conversation ─────────────────────────────────────────────────────────────

export interface ConversationTurn {
  /** Who spoke. */
  agentId: string;
  /** Intended recipient, if any. */
  toAgentId?: string;
  /** What intent. */
  intent: string;
  /** What they said. */
  content: string;
  /** Their internal reasoning (visible in Theatre if showThinking). */
  thinking?: string;
  /** Agent's mood. */
  mood?: string;
  /** ACP message identifier. */
  messageId?: string;
  /** Conversation thread identifier. */
  threadId?: string;
  /** Linked task identifier. */
  taskId?: string;
  /** Linked task title. */
  taskTitle?: string;
  /** Whether acknowledgement was requested. */
  requiresAck?: boolean;
  /** ISO timestamp. */
  timestamp: string;
}

export interface ConversationThread {
  /** Unique thread ID. */
  threadId: string;
  /** Which step this conversation belongs to. */
  stepIndex: number;
  /** All turns in order. */
  turns: ConversationTurn[];
}

// ── Shared Context ───────────────────────────────────────────────────────────

export interface SharedContext {
  /** The original user goal. */
  goal: string;
  /** Completed step summaries — grows after each step. */
  completedSteps: StepSummary[];
  /** Key decisions made during conversations. */
  decisions: string[];
  /** All conversation turns across all steps. */
  allConversations: ConversationTurn[];
}

export interface StepSummary {
  agentId: string;
  task: string;
  output: string;
  verdict: string;
}

// ── Step ─────────────────────────────────────────────────────────────────────

export interface BrainStep {
  /** Step index. */
  index: number;
  /** Agent assigned to this step. */
  agentId: string;
  /** What the agent should do. */
  task: string;
  /** Output from this step (updated after execution + revisions). */
  output?: string;
  /** Review verdict. */
  reviewVerdict?: "approve" | "revise" | "reject" | "escalate";
  /** Review round reached. */
  reviewRound?: number;
  /** Conversation thread for this step. */
  conversation?: ConversationThread;
  /** Cost for this step. */
  costUsd?: number;
  /** Tokens used. */
  tokensUsed?: number;
}

// ── Result ───────────────────────────────────────────────────────────────────

export interface BrainResult {
  /** All steps executed. */
  steps: BrainStep[];
  /** Final synthesized output. */
  output: string;
  /** All ACP events emitted. */
  events: ACPEvent[];
  /** All conversation threads. */
  conversations: ConversationThread[];
  /** Total cost. */
  totalCostUsd: number;
  /** Total tokens. */
  totalTokens: number;
  /** Run ID. */
  runId: string;
}
