/**
 * Dialogue detection — LLM decides when agents should ask teammates
 * for help, verification, or input mid-step. Mirrors platform's
 * dialogue_detector.py + dialogue_turns.py.
 */

import type { AgentDefinition, ConversationTurn, LLMConfig } from "./types";
import { callLLMJson } from "./llm";
import type { LLMCallResult } from "./llm";

export interface DialogueNeed {
  needed: boolean;
  targetAgentId: string;
  reason: string;
  suggestedQuestion: string;
}

export interface DialogueSeed {
  fromAgentId: string;
  toAgentId: string;
  content: string;
  intent: string;
}

export interface DialogueFollowUp {
  needed: boolean;
  agentId: string;
  reason: string;
}

/**
 * Detect if the current agent needs to talk to a teammate.
 * Called after each step execution, before review.
 */
export async function detectDialogueNeeds(
  llm: LLMConfig,
  currentAgentId: string,
  stepOutput: string,
  teammates: AgentDefinition[],
): Promise<{ result: DialogueNeed; cost: LLMCallResult }> {
  const teammateList = teammates
    .filter((a) => a.id !== currentAgentId)
    .map((a) => `- ${a.id}: ${a.name} (${a.role}) — ${a.instructions.slice(0, 80)}`)
    .join("\n");

  if (!teammateList) {
    return {
      result: { needed: false, targetAgentId: "", reason: "", suggestedQuestion: "" },
      cost: emptyCost(llm),
    };
  }

  const { data, cost } = await callLLMJson<{
    needed: boolean;
    target_agent_id?: string;
    reason?: string;
    suggested_question?: string;
  }>(
    llm,
    "You are Brain. After an agent completes a step, decide if they need input "
    + "from a teammate before the work is reviewed. Consider:\n"
    + "- Does the output contain claims that need verification?\n"
    + "- Is there ambiguity a specialist could resolve?\n"
    + "- Would another perspective improve quality?\n\n"
    + "Return JSON: {\"needed\": true/false, \"target_agent_id\": \"agent://...\", "
    + "\"reason\": \"why\", \"suggested_question\": \"what to ask\"}",
    `Agent ${currentAgentId} produced:\n${stepOutput.slice(0, 1500)}\n\n`
    + `Available teammates:\n${teammateList}`,
    { needed: false },
  );

  return {
    result: {
      needed: data.needed ?? false,
      targetAgentId: data.target_agent_id ?? "",
      reason: data.reason ?? "",
      suggestedQuestion: data.suggested_question ?? "",
    },
    cost,
  };
}

/**
 * Propose a seed dialogue turn — a useful check-in when no dialogue
 * was explicitly flagged but team input could still add value.
 */
export async function proposeSeedDialogue(
  llm: LLMConfig,
  currentAgentId: string,
  stepTask: string,
  teammates: AgentDefinition[],
): Promise<{ seed: DialogueSeed | null; cost: LLMCallResult }> {
  const others = teammates.filter((a) => a.id !== currentAgentId);
  if (!others.length) return { seed: null, cost: emptyCost(llm) };

  const { data, cost } = await callLLMJson<{
    should_seed: boolean;
    to_agent_id?: string;
    content?: string;
    intent?: string;
  }>(
    llm,
    "You are Brain. Suggest ONE brief check-in message an agent could send "
    + "to a teammate. Only suggest if it genuinely adds value. Keep it natural "
    + "and short (1 sentence).\n\n"
    + "Return JSON: {\"should_seed\": true/false, \"to_agent_id\": \"agent://...\", "
    + "\"content\": \"message\", \"intent\": \"clarify|verify|handoff\"}",
    `Agent ${currentAgentId} is working on: ${stepTask.slice(0, 300)}\n\n`
    + `Teammates: ${others.map((a) => `${a.id} (${a.role})`).join(", ")}`,
    { should_seed: false },
  );

  if (!data.should_seed || !data.content) return { seed: null, cost };

  return {
    seed: {
      fromAgentId: currentAgentId,
      toAgentId: data.to_agent_id ?? others[0].id,
      content: data.content,
      intent: data.intent ?? "clarify",
    },
    cost,
  };
}

/**
 * Evaluate whether a dialogue response needs a follow-up turn.
 */
export async function evaluateFollowUp(
  llm: LLMConfig,
  thread: ConversationTurn[],
  maxTurns: number,
): Promise<{ result: DialogueFollowUp; cost: LLMCallResult }> {
  if (thread.length >= maxTurns || thread.length < 2) {
    return {
      result: { needed: false, agentId: "", reason: "Max turns or too few messages" },
      cost: emptyCost(llm),
    };
  }

  const threadText = thread
    .map((t) => `${t.agentId}: [${t.intent}] ${t.content.slice(0, 200)}`)
    .join("\n");

  const { data, cost } = await callLLMJson<{
    needs_follow_up: boolean;
    agent_id?: string;
    reason?: string;
  }>(
    llm,
    "You are Brain. Given this agent conversation, decide if a follow-up "
    + "turn is needed. A follow-up is needed if:\n"
    + "- A question was asked but not fully answered\n"
    + "- A disagreement needs resolution\n"
    + "- Key information was requested but not provided\n\n"
    + "Return JSON: {\"needs_follow_up\": true/false, \"agent_id\": \"who should speak\", "
    + "\"reason\": \"why\"}",
    `Conversation:\n${threadText}`,
    { needs_follow_up: false },
  );

  return {
    result: {
      needed: data.needs_follow_up ?? false,
      agentId: data.agent_id ?? "",
      reason: data.reason ?? "",
    },
    cost,
  };
}

function emptyCost(llm: LLMConfig): LLMCallResult {
  return { text: "", tokensUsed: 0, costUsd: 0, model: llm.model ?? "gpt-4o", success: true };
}