/**
 * Step executor — wires ALL subsystems into each step execution.
 * This is the integration layer: narration, coverage, revision,
 * dialogue, memory, guidance all plug in here.
 */

import type { ACPEvent } from "@maia/acp";
import { envelope, message, handoff, activity } from "@maia/acp";
import type {
  BrainStep, AgentDefinition, SharedContext, ConversationThread, LLMConfig,
} from "./types";
import { callLLM } from "./llm";
import type { LLMCallResult } from "./llm";
import * as prompts from "./prompts";
import { runConversation, runReviewLoop } from "./loops";
import { checkCoverage } from "./coverage";
import { buildRevisionSteps } from "./reviser";
import { detectDialogueNeeds, proposeSeedDialogue } from "./dialogue";
import { recallMemories, recordMemory, extractDecisions, memoryContextPrompt } from "./memory";
import type { MemoryStore } from "./memory";
import { personalityPrompt } from "./roles/index";
import { antiRepetitionPrompt, CONVERSATION_RULES } from "./guidance";
import { narrateStepStart, narrateHandoff, narrateVerdict, narrateRevision } from "./narration";
import type { BrainState } from "./state";
import { recordStepOutcome, updateCoverage, raiseSignal, consumeRevisionBudget } from "./state";

export interface ExecutorContext {
  agents: AgentDefinition[];
  llm: LLMConfig;
  runId: string;
  maxConversationTurns: number;
  maxReviewRounds: number;
  memory: MemoryStore;
  state: BrainState;
  emit: (event: ACPEvent) => void;
  trackCost: (result: LLMCallResult) => void;
  findAgent: (agentId: string) => AgentDefinition;
}

/**
 * Execute a single step with ALL subsystems wired in:
 * narration → execute → dialogue → conversation → review → coverage → revision
 */
export async function executeStepFull(
  step: BrainStep,
  context: SharedContext,
  ctx: ExecutorContext,
): Promise<{ revisionsNeeded: BrainStep[] }> {
  const agent = ctx.findAgent(step.agentId);
  const roleId = agent.role ?? step.agentId.replace("agent://", "");

  // ── Narration: announce handoff ─────────────────────────────
  const prevAgent = context.completedSteps.length > 0
    ? context.completedSteps[context.completedSteps.length - 1].agentId
    : "agent://brain";
  for (const ev of narrateHandoff(
    { agentId: prevAgent, agentRole: "brain", runId: ctx.runId },
    step.agentId, step.task,
  )) ctx.emit(ev);

  // ── Handoff event ───────────────────────────────────────────
  ctx.emit(envelope(prevAgent, ctx.runId, "handoff", handoff({
    from: prevAgent,
    to: step.agentId,
    task: { description: step.task, priority: "normal" as const },
    context: { completedSteps: context.completedSteps, decisions: context.decisions },
  })));

  // ── Narration: step start ───────────────────────────────────
  for (const ev of narrateStepStart(
    { agentId: step.agentId, agentRole: roleId, runId: ctx.runId },
    step.task,
  )) ctx.emit(ev);

  // ── Memory: recall relevant past decisions ──────────────────
  const memoryCtx = memoryContextPrompt(ctx.memory, step.task);

  // ── Guidance: anti-repetition + conversation rules ──────────
  const antiRep = antiRepetitionPrompt(context.allConversations);

  // ── Execute: LLM call with personality + memory + guidance ──
  const contextText = buildContextText(context);
  const personality = personalityPrompt(roleId);
  const systemPrompt = prompts.executeSystemPrompt(agent, contextText)
    + personality + memoryCtx + antiRep
    + `\n\n${CONVERSATION_RULES}`;

  const result = await callLLM(ctx.llm, systemPrompt, prompts.executeUserPrompt(step.task));
  ctx.trackCost(result);
  step.output = result.text;
  step.costUsd = (step.costUsd ?? 0) + result.costUsd;
  step.tokensUsed = (step.tokensUsed ?? 0) + result.tokensUsed;

  ctx.emit(envelope(step.agentId, ctx.runId, "message", message({
    from: step.agentId, to: "agent://brain", intent: "propose",
    content: result.text,
    mood: "confident",
    threadId: `thread_step_${step.index}`,
    taskId: `task_step_${step.index}`,
    taskTitle: step.task,
  })));

  // ── Dialogue: detect if teammate input needed ───────────────
  const { result: dialogueNeed, cost: dCost } = await detectDialogueNeeds(
    ctx.llm, step.agentId, step.output ?? "", ctx.agents,
  );
  ctx.trackCost(dCost);

  if (!dialogueNeed.needed) {
    // Try a seed dialogue — low-cost check-in
    const { seed, cost: sCost } = await proposeSeedDialogue(
      ctx.llm, step.agentId, step.task, ctx.agents,
    );
    ctx.trackCost(sCost);
    if (seed) {
      ctx.emit(envelope(seed.fromAgentId, ctx.runId, "message", message({
        from: seed.fromAgentId, to: seed.toAgentId,
        intent: seed.intent as any,
        content: seed.content,
        mood: "uncertain",
        threadId: `thread_step_${step.index}`,
        taskId: `task_step_${step.index}`,
        taskTitle: step.task,
      })));
    }
  }

  // ── Conversation loop ───────────────────────────────────────
  const loopCtx = {
    agents: ctx.agents, llm: ctx.llm, runId: ctx.runId,
    maxConversationTurns: ctx.maxConversationTurns,
    maxReviewRounds: ctx.maxReviewRounds,
    emit: ctx.emit, emitActivity: (a: string, t: string, d: string) => {
      ctx.emit(envelope(a, ctx.runId, "event", activity({ agentId: a, activity: t as any, detail: d })));
    },
    trackCost: ctx.trackCost, findAgent: ctx.findAgent,
  };
  const thread = await runConversation(step, loopCtx);
  step.conversation = thread;

  // ── Review loop ─────────────────────────────────────────────
  await runReviewLoop(step, thread, loopCtx);

  // ── Narration: verdict ──────────────────────────────────────
  for (const ev of narrateVerdict(
    { agentId: "agent://brain", agentRole: "brain", runId: ctx.runId },
    step.reviewVerdict ?? "approve",
    "",
  )) ctx.emit(ev);

  // ── Coverage: check facts/actions satisfied ─────────────────
  const coverageResult = await checkCoverage(
    ctx.llm, step.output ?? "",
    ctx.state.contract.requiredFacts,
    ctx.state.contract.requiredActions,
  );
  ctx.trackCost(coverageResult.cost);
  updateCoverage(ctx.state, coverageResult.facts, coverageResult.actions);

  // ── State: record outcome ───────────────────────────────────
  recordStepOutcome(ctx.state, {
    stepIndex: step.index,
    agentId: step.agentId,
    task: step.task,
    output: step.output ?? "",
    verdict: (step.reviewVerdict ?? "proceed") as any,
    reviewRound: step.reviewRound ?? 1,
    costUsd: step.costUsd ?? 0,
    tokensUsed: step.tokensUsed ?? 0,
  });

  // ── Memory: store decisions from this conversation ──────────
  const newDecisions = extractDecisions(ctx.runId, thread.turns);
  for (const d of newDecisions) recordMemory(ctx.memory, d);

  // ── Revision: inject new steps if coverage gaps remain ──────
  let revisionsNeeded: BrainStep[] = [];
  if (!coverageResult.allSatisfied && consumeRevisionBudget(ctx.state)) {
    raiseSignal(ctx.state, {
      type: "coverage_gap", severity: "medium",
      message: `Gaps remain: ${coverageResult.gaps.join(", ")}`,
    });
    const revision = await buildRevisionSteps(
      ctx.llm, context.goal, coverageResult.gaps,
      context.completedSteps.map((s) => ({
        index: 0, agentId: s.agentId, task: s.task, output: s.output,
      })),
      ctx.agents,
      step.index + 1,
    );
    ctx.trackCost(revision.cost);
    revisionsNeeded = revision.newSteps;
  }

  // ── Update shared context ───────────────────────────────────
  context.completedSteps.push({
    agentId: step.agentId, task: step.task,
    output: (step.output ?? "").slice(0, 500),
    verdict: step.reviewVerdict ?? "approve",
  });
  context.allConversations.push(...thread.turns);
  for (const turn of thread.turns) {
    if (["challenge", "agree", "clarify"].includes(turn.intent)) {
      context.decisions.push(`${turn.agentId}: [${turn.intent}] ${turn.content.slice(0, 150)}`);
    }
  }

  return { revisionsNeeded };
}

function buildContextText(context: SharedContext): string {
  if (context.completedSteps.length === 0) return "";
  const steps = context.completedSteps
    .map((s) => `${s.agentId.replace("agent://", "")} (${s.verdict}): ${s.output.slice(0, 300)}`)
    .join("\n\n");
  const decisions = context.decisions.length > 0
    ? "\n\nKey decisions:\n" + context.decisions.slice(-5).join("\n") : "";
  return `Prior work:\n${steps}${decisions}`;
}
