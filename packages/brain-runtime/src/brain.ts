/**
 * Brain — orchestration runtime. Plans, delegates, and synthesizes.
 * All subsystem wiring happens in executor.ts.
 */

import type { ACPEvent } from "@maia/acp";
import { envelope, message, capabilities } from "@maia/acp";
import type {
  BrainOptions, BrainResult, BrainStep, AgentDefinition,
  SharedContext, ConversationThread,
} from "./types";
import { callLLM, callLLMJson } from "./llm";
import type { LLMCallResult } from "./llm";
import * as prompts from "./prompts";
import { getRole, formatRoleCatalogForPrompt } from "./roles/index";
import { createBrainState } from "./state";
import { createMemoryStore } from "./memory";
import { executeStepFull } from "./executor";

export class Brain {
  private agents: AgentDefinition[];
  private options: Required<Omit<BrainOptions, "onEvent">> & { onEvent?: BrainOptions["onEvent"] };
  private events: ACPEvent[] = [];
  private runId = "";
  private totalCost = 0;
  private totalTokens = 0;

  constructor(opts: BrainOptions) {
    this.agents = opts.agents;
    this.options = {
      agents: opts.agents,
      llm: opts.llm,
      maxReviewRounds: opts.maxReviewRounds ?? 3,
      maxConversationTurns: opts.maxConversationTurns ?? 8,
      maxSteps: opts.maxSteps ?? 20,
      budgetUsd: opts.budgetUsd ?? Infinity,
      onEvent: opts.onEvent,
    };
  }

  async run(goal: string): Promise<BrainResult> {
    this.runId = `run_${Date.now()}`;
    this.events = [];
    this.totalCost = 0;
    this.totalTokens = 0;

    const context: SharedContext = { goal, completedSteps: [], decisions: [], allConversations: [] };
    const state = createBrainState(goal);
    const memory = createMemoryStore();

    // ── Phase 1: Team Assembly ─────────────────────────────────
    this.announceAgents();
    const plan = await this.planSteps(goal);

    this.emit(envelope("agent://brain", this.runId, "message", message({
      from: "agent://brain", to: "agent://broadcast", intent: "propose",
      content: `Plan:\n${plan.map((s, i) => `${i + 1}. ${s.agentId.replace("agent://", "")} — ${s.task}`).join("\n")}`,
      mood: "confident",
    })));

    // ── Phase 2: Step Execution (all subsystems wired) ─────────
    const completedSteps: BrainStep[] = [];
    const allThreads: ConversationThread[] = [];
    const stepsToRun = [...plan];

    const execCtx = {
      agents: this.agents, llm: this.options.llm, runId: this.runId,
      maxConversationTurns: this.options.maxConversationTurns,
      maxReviewRounds: this.options.maxReviewRounds,
      memory, state,
      emit: (event: ACPEvent) => this.emit(event),
      trackCost: (result: LLMCallResult) => this.trackCost(result),
      findAgent: (agentId: string) => this.findAgent(agentId),
    };

    while (stepsToRun.length > 0) {
      const step = stepsToRun.shift()!;
      if (this.totalCost >= this.options.budgetUsd) {
        this.emit(envelope("agent://brain", this.runId, "message", message({
          from: "agent://brain", to: "agent://broadcast", intent: "escalate",
          content: `Budget reached ($${this.totalCost.toFixed(4)}). Stopping.`, mood: "concerned",
        })));
        break;
      }

      const { revisionsNeeded } = await executeStepFull(step, context, execCtx);
      completedSteps.push(step);
      if (step.conversation) allThreads.push(step.conversation);
      if (revisionsNeeded.length > 0) stepsToRun.unshift(...revisionsNeeded);
    }

    // ── Phase 3: Synthesis ─────────────────────────────────────
    const finalOutput = await this.synthesize(context, completedSteps);
    this.emit(envelope("agent://brain", this.runId, "message", message({
      from: "agent://brain", to: "agent://user", intent: "summarize",
      content: finalOutput, mood: "confident",
    })));

    return {
      steps: completedSteps, output: finalOutput, events: this.events,
      conversations: allThreads, totalCostUsd: this.totalCost,
      totalTokens: this.totalTokens, runId: this.runId,
    };
  }

  private async planSteps(goal: string): Promise<BrainStep[]> {
    const ctx = this.agents.length > 0
      ? prompts.planUserPrompt(goal, this.agents)
      : `Goal: ${goal}\n\nAvailable roles:\n${formatRoleCatalogForPrompt()}`;
    const { data, cost } = await callLLMJson<Array<{ agent_id: string; task: string }>>(
      this.options.llm, prompts.planSystemPrompt(), ctx, [],
    );
    this.trackCost(cost);
    return (Array.isArray(data) ? data : []).slice(0, this.options.maxSteps)
      .map((s, i) => ({ index: i, agentId: s.agent_id ?? "agent://researcher", task: s.task ?? goal }));
  }

  private async synthesize(context: SharedContext, steps: BrainStep[]): Promise<string> {
    const result = await callLLM(this.options.llm, prompts.synthesizeSystemPrompt(),
      prompts.synthesizeUserPrompt(context.goal, steps, context.allConversations));
    this.trackCost(result);
    return result.text;
  }

  private announceAgents(): void {
    for (const agent of this.agents) {
      this.emit(envelope(agent.id, this.runId, "capabilities", capabilities({
        agentId: agent.id, name: agent.name, role: agent.role,
        personality: agent.personality,
        skills: (agent.tools ?? []).map((t) => ({ skill_id: t, description: t })),
      })));
    }
  }

  private findAgent(agentId: string): AgentDefinition {
    const ua = this.agents.find((a) => a.id === agentId);
    if (ua) return ua;
    const r = getRole(agentId.replace("agent://", ""));
    return {
      id: agentId, name: r.role.name, role: r.role.id, instructions: r.role.systemPrompt,
      tools: [], personality: {
        style: r.personality.directness > 0.7 ? "concise" : "detailed",
        traits: r.role.defaultTraits, avatar_color: r.role.avatarColor, avatar_emoji: r.role.avatarEmoji,
      },
    };
  }

  private trackCost(result: LLMCallResult): void {
    this.totalCost += result.costUsd;
    this.totalTokens += result.tokensUsed;
  }

  private emit(event: ACPEvent): void {
    this.events.push(event);
    this.options.onEvent?.(event);
  }
}