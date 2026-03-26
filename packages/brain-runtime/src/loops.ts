/**
 * Conversation and review loops - extracted from Brain for LOC compliance.
 * These are the two most complex operations: agent-to-agent conversations
 * and multi-round Brain review with revision.
 */

import type { ACPEvent } from "@maia/acp";
import { envelope, message, review } from "@maia/acp";
import type {
  AgentDefinition, BrainStep, ConversationThread, LLMConfig,
} from "./types";
import { callLLMJson, callLLM } from "./llm";
import type { LLMCallResult } from "./llm";
import * as prompts from "./prompts";
import {
  draftConversationMessage,
  suggestConversationMove,
  summarizeConversationThread,
} from "./collaboration";

interface LoopContext {
  agents: AgentDefinition[];
  llm: LLMConfig;
  runId: string;
  maxConversationTurns: number;
  maxReviewRounds: number;
  emit: (event: ACPEvent) => void;
  emitActivity: (agentId: string, type: string, detail: string) => void;
  trackCost: (result: LLMCallResult) => void;
  findAgent: (agentId: string) => AgentDefinition;
}

function appendThreadTurn(
  thread: ConversationThread,
  event: ACPEvent,
  taskId: string,
  taskTitle: string,
): void {
  if (event.event_type !== "message") {
    return;
  }
  const payload = event.payload as ReturnType<typeof message>;
  thread.turns.push({
    agentId: payload.from,
    toAgentId: payload.to,
    intent: payload.intent,
    content: payload.content,
    thinking: payload.thinking,
    mood: payload.mood,
    messageId: payload.context?.message_id,
    threadId: payload.context?.thread_id ?? thread.threadId,
    taskId: payload.context?.task_id ?? taskId,
    taskTitle: payload.context?.task_title ?? taskTitle,
    requiresAck: payload.context?.requires_ack,
    timestamp: event.timestamp,
  });
}

/**
 * Run the conversation loop after an agent produces output.
 * The move selection and message drafting are both LLM-driven through
 * collaboration helpers, not hardcoded branching rules.
 */
export async function runConversation(
  step: BrainStep,
  ctx: LoopContext,
): Promise<ConversationThread> {
  const threadId = `thread_step_${step.index}`;
  const taskId = `task_step_${step.index}`;
  const thread: ConversationThread = { threadId, stepIndex: step.index, turns: [] };

  const seedEvent = envelope(step.agentId, ctx.runId, "message", message({
    from: step.agentId,
    to: "agent://brain",
    intent: "propose",
    content: step.output ?? "",
    mood: "confident",
    threadId,
    taskId,
    taskTitle: step.task,
  }));
  const threadEvents: ACPEvent[] = [seedEvent];
  appendThreadTurn(thread, seedEvent, taskId, step.task);

  if (ctx.agents.length <= 1) {
    return thread;
  }

  const participants = ctx.agents.map((agent) => ({
    agentId: agent.id,
    name: agent.name,
    role: agent.role,
    description: agent.instructions,
    skills: agent.tools ?? [],
  }));

  let nextSpeakerId = step.agentId;

  for (let turn = 0; turn < ctx.maxConversationTurns; turn++) {
    const currentAgentId = nextSpeakerId;
    const currentAgent = ctx.findAgent(currentAgentId);

    const { move, cost: moveCost } = await suggestConversationMove(
      ctx.llm,
      {
        objective: step.task,
        currentAgentId,
        participants,
        events: threadEvents,
        threadId,
        taskId,
        taskTitle: step.task,
        maxWords: 80,
      },
    );
    ctx.trackCost(moveCost);
    step.costUsd = (step.costUsd ?? 0) + moveCost.costUsd;
    step.tokensUsed = (step.tokensUsed ?? 0) + moveCost.tokensUsed;

    if (move.action === "wait") {
      if (thread.turns.length >= 2) {
        const { digest, cost: digestCost } = await summarizeConversationThread(
          ctx.llm,
          {
            objective: step.task,
            currentAgentId,
            participants,
            events: threadEvents,
            threadId,
            taskId,
            taskTitle: step.task,
          },
        );
        ctx.trackCost(digestCost);
        step.costUsd = (step.costUsd ?? 0) + digestCost.costUsd;
        step.tokensUsed = (step.tokensUsed ?? 0) + digestCost.tokensUsed;

        if (digest.summary.trim()) {
          const summaryEvent = envelope("agent://brain", ctx.runId, "message", message({
            from: "agent://brain",
            to: "agent://broadcast",
            intent: "summarize",
            content: digest.summary,
            mood: "focused",
            threadId,
            taskId,
            taskTitle: step.task,
          }));
          threadEvents.push(summaryEvent);
          appendThreadTurn(thread, summaryEvent, taskId, step.task);
          ctx.emit(summaryEvent);
        }
      }
      break;
    }

    ctx.emitActivity(
      currentAgent.id,
      "thinking",
      `Planning ${move.action}: ${move.reason.slice(0, 80)}`,
    );

    const { draft, message: draftedMessage, cost: draftCost } = await draftConversationMessage(
      ctx.llm,
      {
        objective: step.task,
        currentAgentId,
        participants,
        events: threadEvents,
        threadId,
        taskId,
        taskTitle: step.task,
        maxWords: 80,
      },
      move,
    );
    ctx.trackCost(draftCost);
    step.costUsd = (step.costUsd ?? 0) + draftCost.costUsd;
    step.tokensUsed = (step.tokensUsed ?? 0) + draftCost.tokensUsed;

    if (!draft || !draftedMessage) {
      break;
    }

    const event = envelope(currentAgent.id, ctx.runId, "message", draftedMessage);
    threadEvents.push(event);
    appendThreadTurn(thread, event, taskId, step.task);
    ctx.emit(event);

    if (event.payload.to && event.payload.to !== "agent://broadcast") {
      nextSpeakerId = event.payload.to;
    } else {
      break;
    }
  }

  return thread;
}

/**
 * Run the Brain review loop - approve, revise (with re-execution), reject, or escalate.
 * Max rounds controlled by maxReviewRounds.
 */
export async function runReviewLoop(
  step: BrainStep,
  thread: ConversationThread,
  ctx: LoopContext,
): Promise<void> {
  for (let round = 1; round <= ctx.maxReviewRounds; round++) {
    ctx.emitActivity(
      "agent://brain",
      "reviewing",
      `Reviewing ${step.agentId.replace("agent://", "")}'s output (round ${round})`,
    );

    const { data: rev, cost } = await callLLMJson<{
      verdict: string;
      score?: number;
      feedback?: string;
      revision_instructions?: string;
      strengths?: string[];
      issues?: Array<{ severity: string; description: string }>;
    }>(
      ctx.llm,
      prompts.reviewSystemPrompt(),
      prompts.reviewUserPrompt(step, thread.turns, round),
      { verdict: "approve" },
    );
    ctx.trackCost(cost);
    step.costUsd = (step.costUsd ?? 0) + cost.costUsd;
    step.tokensUsed = (step.tokensUsed ?? 0) + cost.tokensUsed;

    const verdict = rev.verdict || "approve";

    ctx.emit(envelope("agent://brain", ctx.runId, "review", review({
      reviewer: "agent://brain",
      author: step.agentId,
      verdict: verdict as any,
      score: rev.score,
      feedback: rev.feedback,
      revisionInstructions: rev.revision_instructions,
      strengths: rev.strengths,
      issues: rev.issues as any,
      round,
    })));

    step.reviewVerdict = verdict as BrainStep["reviewVerdict"];
    step.reviewRound = round;

    if (verdict === "approve" || verdict === "reject" || verdict === "escalate") {
      break;
    }

    if (verdict === "question" && rev.feedback && round < ctx.maxReviewRounds) {
      ctx.emit(envelope("agent://brain", ctx.runId, "message", message({
        from: "agent://brain",
        to: step.agentId,
        intent: "clarify" as any,
        content: rev.feedback,
        mood: "focused" as any,
        threadId: `thread_step_${step.index}`,
      })));

      const agent = ctx.findAgent(step.agentId);
      ctx.emitActivity(step.agentId, "thinking", "Answering Brain's question...");
      const answerResult = await callLLM(
        ctx.llm,
        `You are ${agent.name}. The Brain asked you a follow-up question about your work. Answer concisely.`,
        `Your previous output:\n${(step.output ?? "").slice(0, 1500)}\n\nBrain's question: ${rev.feedback}`,
      );
      ctx.trackCost(answerResult);
      step.costUsd = (step.costUsd ?? 0) + answerResult.costUsd;
      step.tokensUsed = (step.tokensUsed ?? 0) + answerResult.tokensUsed;

      step.output = `${step.output ?? ""}\n\n[Follow-up answer]: ${answerResult.text}`;
      ctx.emit(envelope(step.agentId, ctx.runId, "message", message({
        from: step.agentId,
        to: "agent://brain",
        intent: "clarify" as any,
        content: answerResult.text,
        mood: "focused" as any,
        threadId: `thread_step_${step.index}`,
      })));
      continue;
    }

    if ((verdict === "revise" || verdict === "question") && round < ctx.maxReviewRounds) {
      const agent = ctx.findAgent(step.agentId);
      ctx.emitActivity(step.agentId, "writing", "Revising based on Brain's feedback...");

      const reviseResult = await callLLM(
        ctx.llm,
        prompts.reviseSystemPrompt(agent),
        prompts.reviseUserPrompt(
          step.output ?? "",
          rev.feedback ?? "",
          rev.revision_instructions ?? "Improve the output.",
        ),
      );
      ctx.trackCost(reviseResult);
      step.costUsd = (step.costUsd ?? 0) + reviseResult.costUsd;
      step.tokensUsed = (step.tokensUsed ?? 0) + reviseResult.tokensUsed;

      step.output = reviseResult.text;

      ctx.emit(envelope(step.agentId, ctx.runId, "message", message({
        from: step.agentId,
        to: "agent://brain",
        intent: "propose",
        content: reviseResult.text,
        mood: "focused",
        threadId: `thread_step_${step.index}`,
      })));
    }
  }
}
