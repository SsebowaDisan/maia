/**
 * Team chat guidance — anti-repetition rules, intent definitions,
 * and conversation quality enforcement.
 * Mirrors platform's team_chat_guidance.py.
 */

import type { ConversationTurn } from "./types";

/** The 8 chat intents agents can use in team conversations. */
export const CHAT_INTENTS = {
  clarify: "Ask for more detail or context on a specific point",
  challenge: "Disagree with or question a claim, finding, or approach",
  propose: "Suggest an idea, approach, or course of action",
  verify: "Confirm a fact, number, or claim from another agent",
  request_evidence: "Ask for supporting data or sources",
  handoff: "Transfer a subtask to a more appropriate teammate",
  summarize: "Recap key findings or decisions so far",
  flag_risk: "Highlight a risk, concern, or potential problem",
} as const;

export type ChatIntent = keyof typeof CHAT_INTENTS;

/** Conversation rules injected into agent system prompts. */
export const CONVERSATION_RULES =
  "Rules for team conversation:\n"
  + "- Sound like teammates, not assistants. Be direct and natural.\n"
  + "- Keep messages short: 1-2 sentences, under 24 words.\n"
  + "- If you disagree, say so clearly with a reason.\n"
  + "- If you agree, add value — don't just echo.\n"
  + "- Don't repeat what was already said.\n"
  + "- Don't start with 'I think' or 'In my opinion' — just state it.\n"
  + "- Reference specific data, not vague impressions.";

/**
 * Extract recent message opening words to prevent repetition.
 * Returns the first 4 words of each recent message.
 */
export function recentMessageOpenings(turns: ConversationTurn[], count: number = 5): string[] {
  return turns
    .slice(-count)
    .map((t) => t.content.split(/\s+/).slice(0, 4).join(" "))
    .filter((s) => s.length > 0);
}

/**
 * Build an anti-repetition prompt based on recent conversation.
 * Tells the agent what sentence openings to avoid.
 */
export function antiRepetitionPrompt(turns: ConversationTurn[]): string {
  const openings = recentMessageOpenings(turns, 6);
  if (openings.length === 0) return "";

  return (
    "\nAvoid starting your message with any of these openings (already used):\n"
    + openings.map((o) => `- "${o}..."`).join("\n")
    + "\n\nUse a fresh sentence structure."
  );
}

/**
 * Build a mood-appropriate response instruction.
 * Guides the agent to respond with the right emotional tone.
 */
export function moodInstruction(mood: string): string {
  const instructions: Record<string, string> = {
    neutral: "Respond factually and evenly.",
    curious: "Show genuine interest. Ask a probing question.",
    confident: "State your position clearly and back it with evidence.",
    skeptical: "Express doubt constructively. Ask for proof.",
    excited: "Show enthusiasm but stay grounded in data.",
    concerned: "Flag the issue clearly. Suggest what to do about it.",
  };
  return instructions[mood] ?? instructions.neutral;
}

/**
 * Check if a conversation is getting repetitive.
 * Returns true if the last 3+ messages share similar openings.
 */
export function isConversationRepetitive(turns: ConversationTurn[]): boolean {
  if (turns.length < 3) return false;
  const recent = turns.slice(-4);
  const openings = recent.map((t) =>
    t.content.toLowerCase().split(/\s+/).slice(0, 3).join(" "),
  );
  const unique = new Set(openings);
  return unique.size <= Math.ceil(openings.length / 2);
}

/**
 * Suggest a conversation pivot when discussion stalls.
 */
export function suggestPivot(turns: ConversationTurn[]): string {
  if (turns.length < 2) return "";
  const intentsUsed = new Set(turns.map((t) => t.intent));

  // Suggest an intent not yet used
  const unused = Object.keys(CHAT_INTENTS).filter((i) => !intentsUsed.has(i));
  if (unused.length > 0) {
    const suggested = unused[0] as ChatIntent;
    return `Try a different angle: ${CHAT_INTENTS[suggested]}`;
  }
  return "Consider summarizing the key decisions and moving on.";
}