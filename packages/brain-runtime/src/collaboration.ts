/**
 * LLM-native collaboration helpers for agent-to-agent coordination.
 * These functions use live ACP context to suggest who should speak next,
 * draft a natural message, and compress thread state for the UI/runtime.
 */

import { message as buildMessage } from "@maia/acp";
import type {
  ACPCapabilities,
  ACPEvent,
  ACPMessage,
  AgentPresence,
  MessageIntent,
} from "@maia/acp";
import { callLLMJson } from "./llm";
import type { LLMCallResult } from "./llm";
import type { AgentDefinition, LLMConfig } from "./types";

export interface CollaborationParticipant {
  agentId: string;
  name: string;
  role?: string;
  description?: string;
  skills?: string[];
  acceptsIntents?: MessageIntent[];
  presence?: AgentPresence;
}

export interface CollaborationContext {
  objective: string;
  currentAgentId: string;
  participants: CollaborationParticipant[];
  events: ACPEvent[];
  threadId?: string;
  taskId?: string;
  taskTitle?: string;
  maxWords?: number;
}

export interface ConversationMove {
  action: "reply" | "ask" | "handoff" | "review" | "summarize" | "wait";
  toAgentId?: string;
  intent: MessageIntent;
  reason: string;
  requiresAck?: boolean;
  mentions?: string[];
  confidence?: number;
}

export interface MessageDraft {
  toAgentId: string;
  intent: MessageIntent;
  content: string;
  thinking?: string;
  mood?: ACPMessage["mood"];
  taskId?: string;
  taskTitle?: string;
  threadId?: string;
  requiresAck?: boolean;
  mentions?: string[];
}

export interface ThreadDigest {
  summary: string;
  decisions: string[];
  blockers: string[];
  openQuestions: string[];
  nextAction?: string;
  nextOwnerAgentId?: string;
}

function emptyCost(llm: LLMConfig): LLMCallResult {
  return {
    text: "",
    tokensUsed: 0,
    costUsd: 0,
    model: llm.model ?? "gpt-4o",
    success: true,
  };
}

function normalizeParticipants(
  participants: Array<CollaborationParticipant | AgentDefinition | ACPCapabilities>,
): CollaborationParticipant[] {
  return participants.map((participant) => {
    if ("agent_id" in participant) {
      return {
        agentId: participant.agent_id,
        name: participant.name,
        role: participant.role,
        description: participant.description,
        skills: participant.skills?.map((skill) => skill.description ?? skill.skill_id) ?? [],
        acceptsIntents: participant.accepts_intents,
        presence: participant.presence,
      };
    }
    if ("id" in participant) {
      return {
        agentId: participant.id,
        name: participant.name,
        role: participant.role,
        description: participant.instructions,
        skills: participant.tools ?? [],
      };
    }
    return participant;
  });
}

function truncate(text: string, maxLength: number): string {
  const value = String(text || "").trim();
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, Math.max(0, maxLength - 3))}...`;
}

function eventLine(event: ACPEvent): string {
  if (event.event_type === "message") {
    const payload = event.payload as ACPMessage;
    const context = payload.context ?? {};
    const target = payload.to === "agent://broadcast" ? "everyone" : payload.to;
    return [
      `${payload.from} -> ${target}`,
      `[${payload.intent}]`,
      truncate(payload.content, 240),
      context.task_title ? `(task: ${context.task_title})` : "",
      context.delivery_status ? `(delivery: ${context.delivery_status})` : "",
    ]
      .filter(Boolean)
      .join(" ");
  }
  if (event.event_type === "handoff") {
    const payload = event.payload as Record<string, any>;
    return `${payload.from} handed off to ${payload.to}: ${truncate(payload.task?.description ?? "", 220)}`;
  }
  if (event.event_type === "review") {
    const payload = event.payload as Record<string, any>;
    return `${payload.reviewer} reviewed ${payload.author}: ${payload.verdict}`;
  }
  return `${event.agent_id} ${event.event_type}`;
}

function formatParticipants(participants: CollaborationParticipant[], currentAgentId: string): string {
  return participants
    .map((participant) => {
      const intents =
        participant.acceptsIntents && participant.acceptsIntents.length > 0
          ? participant.acceptsIntents.join(", ")
          : "any";
      const presence = participant.presence;
      return [
        `- ${participant.agentId}${participant.agentId === currentAgentId ? " (current speaker)" : ""}`,
        `${participant.name}${participant.role ? `, ${participant.role}` : ""}`,
        participant.description ? `- ${truncate(participant.description, 140)}` : "",
        participant.skills && participant.skills.length > 0
          ? `- skills: ${participant.skills.slice(0, 6).join(", ")}`
          : "",
        `- intents: ${intents}`,
        presence?.availability ? `- availability: ${presence.availability}` : "",
        presence?.current_focus ? `- focus: ${truncate(presence.current_focus, 100)}` : "",
        typeof presence?.active_task_count === "number"
          ? `- active tasks: ${presence.active_task_count}`
          : "",
      ]
        .filter(Boolean)
        .join(" ");
    })
    .join("\n");
}

function formatRecentEvents(events: ACPEvent[]): string {
  if (!events.length) {
    return "(no recent conversation)";
  }
  return events.slice(-12).map(eventLine).join("\n");
}

function lastMessageId(events: ACPEvent[]): string | undefined {
  for (let index = events.length - 1; index >= 0; index--) {
    const event = events[index];
    if (event.event_type !== "message") {
      continue;
    }
    const payload = event.payload as ACPMessage;
    if (payload.context?.message_id) {
      return payload.context.message_id;
    }
  }
  return undefined;
}

function moveSystemPrompt(maxWords: number): string {
  return [
    "You coordinate a team of AI workmates.",
    "Decide the most useful next communication move for the current agent.",
    "Use natural human work patterns: ask for verification when needed, hand off when the work should switch owners, summarize when the thread is getting noisy, and wait when no message adds value.",
    "Prefer the best teammate based on role fit, current focus, and availability.",
    `If a message is needed, keep it under ${maxWords} words.`,
    "Return JSON only with keys: action, to_agent_id, intent, reason, requires_ack, mentions, confidence.",
  ].join(" ");
}

function moveUserPrompt(context: CollaborationContext): string {
  return [
    `Objective: ${context.objective}`,
    context.taskTitle ? `Task title: ${context.taskTitle}` : "",
    context.taskId ? `Task id: ${context.taskId}` : "",
    context.threadId ? `Thread id: ${context.threadId}` : "",
    `Current agent: ${context.currentAgentId}`,
    "",
    "Participants:",
    formatParticipants(context.participants, context.currentAgentId),
    "",
    "Recent events:",
    formatRecentEvents(context.events),
  ]
    .filter(Boolean)
    .join("\n");
}

function draftSystemPrompt(maxWords: number): string {
  return [
    "You write natural teammate-to-teammate messages for an AI team.",
    "Sound like a strong human workmate: direct, specific, and useful.",
    "Do not use canned greetings, filler, or robotic recap.",
    "Ground the message in the supplied thread context and task state.",
    "If the move is a handoff, clearly state what is done and what needs the recipient.",
    "If the move is a question, make it crisp and answerable.",
    `Keep the message under ${maxWords} words unless the context requires a short structured summary.`,
    "Return JSON only with keys: content, intent, thinking, mood, to_agent_id, task_id, task_title, thread_id, requires_ack, mentions.",
  ].join(" ");
}

function draftUserPrompt(context: CollaborationContext, move: ConversationMove): string {
  return [
    `Objective: ${context.objective}`,
    `Current agent: ${context.currentAgentId}`,
    `Planned move: ${move.action}`,
    `Reason: ${move.reason}`,
    move.toAgentId ? `Recipient: ${move.toAgentId}` : "",
    `Intent: ${move.intent}`,
    context.taskTitle ? `Task title: ${context.taskTitle}` : "",
    context.taskId ? `Task id: ${context.taskId}` : "",
    context.threadId ? `Thread id: ${context.threadId}` : "",
    "",
    "Participants:",
    formatParticipants(context.participants, context.currentAgentId),
    "",
    "Recent events:",
    formatRecentEvents(context.events),
  ]
    .filter(Boolean)
    .join("\n");
}

function digestSystemPrompt(): string {
  return [
    "You compress agent coordination threads into an operational digest.",
    "Capture what has been decided, what is blocked, what remains unclear, and who should act next.",
    "Return JSON only with keys: summary, decisions, blockers, open_questions, next_action, next_owner_agent_id.",
  ].join(" ");
}

function digestUserPrompt(context: CollaborationContext): string {
  return [
    `Objective: ${context.objective}`,
    context.taskTitle ? `Task title: ${context.taskTitle}` : "",
    context.threadId ? `Thread id: ${context.threadId}` : "",
    "",
    "Participants:",
    formatParticipants(context.participants, context.currentAgentId),
    "",
    "Recent events:",
    formatRecentEvents(context.events),
  ]
    .filter(Boolean)
    .join("\n");
}

export async function suggestConversationMove(
  llm: LLMConfig,
  rawContext: CollaborationContext,
): Promise<{ move: ConversationMove; cost: LLMCallResult }> {
  const context = {
    ...rawContext,
    participants: normalizeParticipants(rawContext.participants),
  };
  if (context.participants.length <= 1) {
    return {
      move: {
        action: "wait",
        intent: "summarize",
        reason: "No teammate is available for coordination.",
        confidence: 1,
      },
      cost: emptyCost(llm),
    };
  }

  const { data, cost } = await callLLMJson<{
    action?: ConversationMove["action"];
    to_agent_id?: string;
    intent?: MessageIntent;
    reason?: string;
    requires_ack?: boolean;
    mentions?: string[];
    confidence?: number;
  }>(
    llm,
    moveSystemPrompt(rawContext.maxWords ?? 80),
    moveUserPrompt(context),
    {
      action: "wait",
      intent: "summarize",
      reason: "No additional coordination is needed.",
      confidence: 0.5,
    },
  );

  return {
    move: {
      action: data.action ?? "wait",
      toAgentId: data.to_agent_id,
      intent: data.intent ?? "clarify",
      reason: data.reason ?? "No additional coordination is needed.",
      requiresAck: data.requires_ack ?? false,
      mentions: data.mentions ?? [],
      confidence: data.confidence,
    },
    cost,
  };
}

export async function draftConversationMessage(
  llm: LLMConfig,
  rawContext: CollaborationContext,
  move: ConversationMove,
): Promise<{ draft: MessageDraft | null; message: ACPMessage | null; cost: LLMCallResult }> {
  if (move.action === "wait" || !move.toAgentId) {
    return { draft: null, message: null, cost: emptyCost(llm) };
  }

  const context = {
    ...rawContext,
    participants: normalizeParticipants(rawContext.participants),
  };

  const { data, cost } = await callLLMJson<{
    content?: string;
    intent?: MessageIntent;
    thinking?: string;
    mood?: ACPMessage["mood"];
    to_agent_id?: string;
    task_id?: string;
    task_title?: string;
    thread_id?: string;
    requires_ack?: boolean;
    mentions?: string[];
  }>(
    llm,
    draftSystemPrompt(rawContext.maxWords ?? 80),
    draftUserPrompt(context, move),
    {
      content: "",
      intent: move.intent,
      to_agent_id: move.toAgentId,
      task_id: rawContext.taskId,
      task_title: rawContext.taskTitle,
      thread_id: rawContext.threadId,
      requires_ack: move.requiresAck,
      mentions: move.mentions ?? [],
    },
  );

  const content = String(data.content ?? "").trim();
  if (!content) {
    return { draft: null, message: null, cost };
  }

  const draft: MessageDraft = {
    toAgentId: data.to_agent_id ?? move.toAgentId,
    intent: data.intent ?? move.intent,
    content,
    thinking: data.thinking,
    mood: data.mood,
    taskId: data.task_id ?? rawContext.taskId,
    taskTitle: data.task_title ?? rawContext.taskTitle,
    threadId: data.thread_id ?? rawContext.threadId,
    requiresAck: data.requires_ack ?? move.requiresAck,
    mentions: data.mentions ?? move.mentions ?? [],
  };

  return {
    draft,
    message: buildMessage({
      from: rawContext.currentAgentId,
      to: draft.toAgentId,
      intent: draft.intent,
      content: draft.content,
      thinking: draft.thinking,
      mood: draft.mood,
      inReplyTo: lastMessageId(rawContext.events),
      taskId: draft.taskId,
      taskTitle: draft.taskTitle,
      threadId: draft.threadId,
      requiresAck: draft.requiresAck,
      mentions: draft.mentions,
    }),
    cost,
  };
}

export async function summarizeConversationThread(
  llm: LLMConfig,
  rawContext: CollaborationContext,
): Promise<{ digest: ThreadDigest; cost: LLMCallResult }> {
  const context = {
    ...rawContext,
    participants: normalizeParticipants(rawContext.participants),
  };

  const { data, cost } = await callLLMJson<{
    summary?: string;
    decisions?: string[];
    blockers?: string[];
    open_questions?: string[];
    next_action?: string;
    next_owner_agent_id?: string;
  }>(
    llm,
    digestSystemPrompt(),
    digestUserPrompt(context),
    {
      summary: "",
      decisions: [],
      blockers: [],
      open_questions: [],
    },
  );

  return {
    digest: {
      summary: data.summary ?? "",
      decisions: data.decisions ?? [],
      blockers: data.blockers ?? [],
      openQuestions: data.open_questions ?? [],
      nextAction: data.next_action,
      nextOwnerAgentId: data.next_owner_agent_id,
    },
    cost,
  };
}
