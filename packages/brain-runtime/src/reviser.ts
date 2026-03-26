/**
 * Plan revision — when coverage gaps remain after a step, LLM proposes
 * 1-3 new steps to fill them. Mirrors platform's reviser.py.
 */

import type { AgentDefinition, BrainStep, LLMConfig } from "./types";
import { callLLMJson } from "./llm";
import type { LLMCallResult } from "./llm";

export interface RevisionResult {
  newSteps: BrainStep[];
  reason: string;
  cost: LLMCallResult;
}

const MAX_REVISION_STEPS = 3;

/**
 * Propose new steps to fill coverage gaps.
 * Returns 0-3 new BrainStep objects to inject into the plan.
 */
export async function buildRevisionSteps(
  llm: LLMConfig,
  goal: string,
  gaps: string[],
  completedSteps: BrainStep[],
  agents: AgentDefinition[],
  nextIndex: number,
): Promise<RevisionResult> {
  if (!gaps.length) {
    return { newSteps: [], reason: "No gaps to fill", cost: emptyCost(llm) };
  }

  const agentList = agents
    .map((a) => `- ${a.id}: ${a.name} (${a.role})`)
    .join("\n");

  const completedList = completedSteps
    .map((s) => `- Step ${s.index + 1}: ${s.agentId} — ${s.task} [${s.reviewVerdict ?? "pending"}]`)
    .join("\n");

  const gapList = gaps.map((g, i) => `${i + 1}. ${g}`).join("\n");

  const systemPrompt =
    "You are Brain, an AI orchestrator. Some required facts or actions were not satisfied "
    + "by the steps executed so far. Propose 1-3 NEW steps to fill the gaps.\n\n"
    + "Return JSON: [{\"agent_id\": \"agent://...\", \"task\": \"specific task\"}]\n\n"
    + "Rules:\n"
    + "- Only propose steps that directly address the listed gaps\n"
    + "- Assign to the most appropriate available agent\n"
    + "- Do not repeat steps already completed\n"
    + "- Maximum 3 new steps";

  const userPrompt =
    `Goal: ${goal}\n\n`
    + `Completed steps:\n${completedList}\n\n`
    + `Remaining gaps:\n${gapList}\n\n`
    + `Available agents:\n${agentList}`;

  const { data, cost } = await callLLMJson<
    Array<{ agent_id: string; task: string }>
  >(llm, systemPrompt, userPrompt, []);

  const newSteps: BrainStep[] = (Array.isArray(data) ? data : [])
    .slice(0, MAX_REVISION_STEPS)
    .map((s, i) => ({
      index: nextIndex + i,
      agentId: s.agent_id ?? agents[0]?.id ?? "agent://unknown",
      task: s.task ?? gaps[i] ?? "Fill remaining gaps",
    }));

  return {
    newSteps,
    reason: newSteps.length > 0
      ? `Proposed ${newSteps.length} step(s) to fill ${gaps.length} gap(s)`
      : "LLM found no additional steps needed",
    cost,
  };
}

function emptyCost(llm: LLMConfig): LLMCallResult {
  return { text: "", tokensUsed: 0, costUsd: 0, model: llm.model ?? "gpt-4o", success: true };
}