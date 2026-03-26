/**
 * All LLM prompts for the Brain runtime — extracted into one file.
 * No hardcoded prompt strings anywhere else.
 */

import type { AgentDefinition, BrainStep, ConversationTurn } from "./types";

// ── Plan Decomposition ───────────────────────────────────────────────────────

export function planSystemPrompt(): string {
  return (
    "You are Brain, an AI orchestrator that decomposes goals into sequential agent steps. "
    + "Analyze the goal and assign each step to the best-suited agent. "
    + "Return a JSON array: [{\"agent_id\": \"agent://name\", \"task\": \"specific task description\"}]. "
    + "Keep tasks focused — one clear objective per step. "
    + "Order steps logically — research before analysis, analysis before writing."
  );
}

export function planUserPrompt(goal: string, agents: AgentDefinition[]): string {
  const agentList = agents
    .map((a) => `- ${a.id}: ${a.name} (${a.role}) — ${a.instructions.slice(0, 150)}`)
    .join("\n");
  return `Goal: ${goal}\n\nAvailable agents:\n${agentList}`;
}

// ── Step Execution ───────────────────────────────────────────────────────────

export function executeSystemPrompt(agent: AgentDefinition, threadContext: string): string {
  return (
    `You are ${agent.name}, a ${agent.role} agent. ${agent.instructions}\n\n`
    + "Respond directly with your work output. Be thorough but concise.\n"
    + (threadContext ? `\nContext from the team so far:\n${threadContext}` : "")
  );
}

export function executeUserPrompt(task: string): string {
  return task;
}

// ── Conversation Trigger ─────────────────────────────────────────────────────

export function shouldRespondSystemPrompt(): string {
  return (
    "You are Brain, deciding whether another agent should respond to what was just said. "
    + "Consider: Does the output need verification? Is a claim questionable? "
    + "Would another agent's expertise add value? Is clarification needed?\n\n"
    + "Return JSON: {\"should_respond\": true/false, \"agent_id\": \"agent://...\", \"reason\": \"brief reason\"}\n"
    + "Only trigger a response when it genuinely adds value. Not every output needs discussion."
  );
}

export function shouldRespondUserPrompt(
  lastMessage: ConversationTurn,
  availableAgents: AgentDefinition[],
  thread: ConversationTurn[],
): string {
  const agentList = availableAgents
    .map((a) => `- ${a.id}: ${a.name} (${a.role})`)
    .join("\n");

  const threadText = thread.length > 0
    ? thread.map((t) => `${t.agentId}: [${t.intent}] ${t.content.slice(0, 200)}`).join("\n")
    : "(no prior conversation)";

  return (
    `Last message from ${lastMessage.agentId}:\n`
    + `[${lastMessage.intent}] ${lastMessage.content.slice(0, 500)}\n\n`
    + `Conversation so far:\n${threadText}\n\n`
    + `Available agents who could respond:\n${agentList}`
  );
}

// ── Agent Reply Generation ───────────────────────────────────────────────────

export function replySystemPrompt(agent: AgentDefinition): string {
  return (
    `You are ${agent.name}, a ${agent.role} agent. ${agent.instructions}\n\n`
    + "You are in a team conversation. Respond naturally and concisely (under 100 words). "
    + "Be direct. If you disagree, say so clearly. If you agree, add value — don't just echo.\n\n"
    + "Return JSON: {\"content\": \"your response\", \"intent\": \"propose|challenge|clarify|agree|escalate\", "
    + "\"thinking\": \"your brief internal reasoning\", \"mood\": \"confident|uncertain|concerned|focused\"}"
  );
}

export function replyUserPrompt(
  thread: ConversationTurn[],
  reason: string,
): string {
  const threadText = thread
    .map((t) => `${t.agentId.replace("agent://", "")}: [${t.intent}] ${t.content}`)
    .join("\n\n");

  return (
    `Team conversation:\n${threadText}\n\n`
    + `You were asked to respond because: ${reason}\n\n`
    + "What is your response?"
  );
}

// ── Brain Review ─────────────────────────────────────────────────────────────

export function reviewSystemPrompt(): string {
  return (
    "You are Brain, reviewing an agent's work output. Evaluate quality, accuracy, and completeness.\n\n"
    + "Return JSON: {\n"
    + "  \"verdict\": \"approve|revise|reject|escalate\",\n"
    + "  \"score\": 0.0-1.0,\n"
    + "  \"feedback\": \"what's good and what needs work\",\n"
    + "  \"revision_instructions\": \"specific changes needed (if revise)\",\n"
    + "  \"strengths\": [\"list of strengths\"],\n"
    + "  \"issues\": [{\"severity\": \"minor|major|critical\", \"description\": \"...\"}]\n"
    + "}\n\n"
    + "Standards: approve if output is accurate and complete. "
    + "Revise if fixable issues exist. Reject only if fundamentally wrong. "
    + "Escalate if human judgment needed."
  );
}

export function reviewUserPrompt(
  step: BrainStep,
  conversationThread: ConversationTurn[],
  round: number,
): string {
  const threadText = conversationThread.length > 0
    ? "\n\nTeam discussion:\n" + conversationThread
        .map((t) => `${t.agentId.replace("agent://", "")}: [${t.intent}] ${t.content.slice(0, 200)}`)
        .join("\n")
    : "";

  return (
    `Task: ${step.task}\n\n`
    + `Agent: ${step.agentId}\n`
    + `Review round: ${round}\n\n`
    + `Output:\n${(step.output ?? "").slice(0, 3000)}`
    + threadText
  );
}

// ── Revision ─────────────────────────────────────────────────────────────────

export function reviseSystemPrompt(agent: AgentDefinition): string {
  return (
    `You are ${agent.name}. Your previous output was reviewed and needs revision.\n\n`
    + `${agent.instructions}\n\n`
    + "Address the feedback specifically. Do not repeat the entire output — "
    + "provide the corrected/improved version."
  );
}

export function reviseUserPrompt(
  previousOutput: string,
  feedback: string,
  revisionInstructions: string,
): string {
  return (
    `Your previous output:\n${previousOutput.slice(0, 2000)}\n\n`
    + `Feedback: ${feedback}\n\n`
    + `Specific instructions: ${revisionInstructions}\n\n`
    + "Provide your revised output:"
  );
}

// ── Final Synthesis ──────────────────────────────────────────────────────────

export function synthesizeSystemPrompt(): string {
  return (
    "You are Brain. Synthesize the team's work into a final, cohesive response for the user. "
    + "Integrate all findings, respect corrections made during review, and present a polished result. "
    + "Do not mention the internal team process — deliver as if from a single expert."
  );
}

export function synthesizeUserPrompt(
  goal: string,
  steps: BrainStep[],
  conversations: ConversationTurn[],
): string {
  const stepSummaries = steps
    .map((s, i) => {
      const verdict = s.reviewVerdict ? ` [${s.reviewVerdict}]` : "";
      return `Step ${i + 1} (${s.agentId})${verdict}:\n${(s.output ?? "").slice(0, 800)}`;
    })
    .join("\n\n");

  const convText = conversations.length > 0
    ? "\n\nKey team discussions:\n" + conversations
        .filter((t) => t.intent === "challenge" || t.intent === "agree" || t.intent === "clarify")
        .map((t) => `${t.agentId.replace("agent://", "")} [${t.intent}]: ${t.content.slice(0, 200)}`)
        .join("\n")
    : "";

  return `Goal: ${goal}\n\nTeam outputs:\n${stepSummaries}${convText}`;
}

// ── Quick-Fire Exchanges ─────────────────────────────────────────────────────

export function quickFireInstruction(): string {
  return (
    "\nWhen you agree or the point is simple, respond in under 8 words. "
    + "Examples: 'Verified.', 'Good. Next.', 'On it.', 'Checks out.', "
    + "'Numbers are right.', 'Done — here it is.'\n"
    + "Not every response needs to be a paragraph."
  );
}

// ── Constructive Friction ────────────────────────────────────────────────────

export function frictionInstruction(): string {
  return (
    "\nWhen you disagree, be specific and direct. Don't soften with 'I think maybe...' "
    + "Instead: state the problem, cite evidence, propose the fix.\n"
    + "Example: 'That 12% is wrong. Bessemer's appendix shows Enterprise +8%, SMB -18%. Split by segment.'\n"
    + "Disagreements should take 2-3 exchanges to resolve, not 1."
  );
}

// ── Proactive Sharing ────────────────────────────────────────────────────────

export function proactiveInstruction(): string {
  return (
    "\nIf you notice something relevant that wasn't asked for, share it.\n"
    + "Example: 'By the way — the dataset also has churn rates. Want me to include that?'\n"
    + "Good teammates volunteer information."
  );
}

// ── Natural Handoff ──────────────────────────────────────────────────────────

export function handoffInstruction(): string {
  return (
    "\nWhen your part is done, hand off naturally to the next person.\n"
    + "Instead of: 'My task is complete.'\n"
    + "Say: '@Analyst — can you verify the growth numbers?' or "
    + "'That\\'s everything. Writer, it\\'s yours.'"
  );
}

// ── Decision Anchoring ───────────────────────────────────────────────────────

export function decisionAnchoringInstruction(decisions: string[]): string {
  if (!decisions.length) return "";
  return (
    "\nDecisions made so far (reference these naturally):\n"
    + decisions.slice(-5).map((d) => `- ${d}`).join("\n")
    + "\n\nUse phrases like 'per our earlier decision', 'as we agreed', 'like we discussed'."
  );
}

// ── Conversation Compression ─────────────────────────────────────────────────

export function compressionInstruction(): string {
  return (
    "\nWhen summarizing a discussion, use this format:\n"
    + "'We\\'ve settled: (1) [decision], (2) [decision], (3) [decision]. Moving on.'\n"
    + "Keep summaries under 3 bullet points. Don\\'t recap — compress."
  );
}