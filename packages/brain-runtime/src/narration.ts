/**
 * Narration — the bridge between Theatre (actions) and TeamChat (conversations).
 *
 * Every agent action produces TWO synchronized events:
 * 1. Activity event → Theatre shows what the agent is DOING
 * 2. Message event  → TeamChat shows what the agent is SAYING about it
 *
 * Both share the same timestamp so they appear synchronized.
 * This is the ONLY place that emits paired events.
 */

import type { ACPEvent } from "@maia/acp";

interface NarrationContext {
  agentId: string;
  agentRole: string;
  runId: string;
}

/**
 * Narrate a step starting — agent announces what they're about to do.
 * Theatre: "thinking" activity. TeamChat: natural announcement.
 */
export function narrateStepStart(ctx: NarrationContext, task: string): ACPEvent[] {
  const ts = new Date().toISOString();
  const line = PRE_LINES[ctx.agentRole]?.start ?? `Working on this now...`;

  return [
    makeActivity(ctx, "thinking", `Working on: ${task.slice(0, 80)}`, ts),
    makeMessage(ctx, line, "propose", "focused", ts),
  ];
}

/**
 * Narrate a tool being used — "Let me search for..." + searching activity.
 */
export function narrateToolUse(ctx: NarrationContext, toolName: string, detail: string): ACPEvent[] {
  const ts = new Date().toISOString();
  const act = mapToolToActivity(toolName);
  const line = getPreToolLine(ctx.agentRole, act, detail);

  return [
    makeActivity(ctx, act, detail.slice(0, 100), ts),
    ...(line ? [makeMessage(ctx, line, "propose", "focused", ts)] : []),
  ];
}

/**
 * Narrate a tool completing — result activity + natural summary.
 */
export function narrateToolDone(
  ctx: NarrationContext,
  toolName: string,
  summary: string,
  success: boolean,
): ACPEvent[] {
  const ts = new Date().toISOString();
  const act = mapToolToActivity(toolName);
  const line = getPostToolLine(ctx.agentRole, summary, success);

  return [
    makeActivity(ctx, act, summary.slice(0, 100), ts, success ? "completed" : "failed"),
    ...(line ? [makeMessage(ctx, line, "propose", success ? "confident" : "concerned", ts)] : []),
  ];
}

/**
 * Narrate a conversation response — agent reacts to what just happened.
 * Activity: "thinking". Message: their actual response.
 */
export function narrateReply(
  ctx: NarrationContext,
  content: string,
  intent: string,
  thinking: string | undefined,
  mood: string,
): ACPEvent[] {
  const ts = new Date().toISOString();
  return [
    makeActivity(ctx, "thinking", `Responding: ${content.slice(0, 60)}`, ts),
    makeMessage(ctx, content, intent, mood, ts, thinking),
  ];
}

/**
 * Narrate Brain reviewing — activity + message synchronized.
 */
export function narrateReview(
  ctx: NarrationContext,
  authorId: string,
  round: number,
): ACPEvent[] {
  const ts = new Date().toISOString();
  const author = authorId.replace("agent://", "");
  return [
    makeActivity(ctx, "reviewing", `Reviewing ${author}'s output (round ${round})`, ts),
  ];
}

/**
 * Narrate Brain's review verdict — activity + message.
 */
export function narrateVerdict(
  ctx: NarrationContext,
  verdict: string,
  feedback: string,
): ACPEvent[] {
  const ts = new Date().toISOString();
  const line = verdict === "approve" ? "Looks good."
    : verdict === "revise" ? feedback.slice(0, 100) || "Needs revision."
    : verdict === "question" ? feedback.slice(0, 100) || "I have a question."
    : "Stopping here.";

  return [
    makeMessage(ctx, line, verdict === "approve" ? "agree" : "review", verdict === "approve" ? "confident" : "concerned", ts),
  ];
}

/**
 * Narrate an agent revising their work.
 */
export function narrateRevision(ctx: NarrationContext, feedback: string): ACPEvent[] {
  const ts = new Date().toISOString();
  const line = REVISE_LINES[ctx.agentRole] ?? "Revising now...";
  return [
    makeActivity(ctx, "writing", `Revising based on feedback`, ts),
    makeMessage(ctx, line, "propose", "focused", ts),
  ];
}

/**
 * Narrate a handoff between agents.
 */
export function narrateHandoff(
  fromCtx: NarrationContext,
  toAgentId: string,
  task: string,
): ACPEvent[] {
  const ts = new Date().toISOString();
  const toName = toAgentId.replace("agent://", "");
  const line = `@${toName} — ${task.slice(0, 60)}`;
  return [
    makeMessage(fromCtx, line, "handoff", "confident", ts),
  ];
}

// ── Internal Helpers ─────────────────────────────────────────────────────────

function makeActivity(
  ctx: NarrationContext, act: string, detail: string, ts: string, status?: string,
): ACPEvent {
  const payload: Record<string, any> = { agent_id: ctx.agentId, activity: act, detail };
  if (status) payload.tool = { tool_id: act, tool_name: act, status };
  return { acp_version: "1.0", run_id: ctx.runId, agent_id: ctx.agentId, event_type: "event", timestamp: ts, payload };
}

function makeMessage(
  ctx: NarrationContext, content: string, intent: string, mood: string, ts: string, thinking?: string,
): ACPEvent {
  return {
    acp_version: "1.0", run_id: ctx.runId, agent_id: ctx.agentId, event_type: "message", timestamp: ts,
    payload: { from: ctx.agentId, to: "agent://broadcast", intent, content, mood, thinking },
  };
}

function mapToolToActivity(tool: string): string {
  const l = tool.toLowerCase();
  if (l.includes("search") || l.includes("google")) return "searching";
  if (l.includes("read") || l.includes("document") || l.includes("pdf")) return "reading";
  if (l.includes("write") || l.includes("draft")) return "writing";
  if (l.includes("browse") || l.includes("navigate")) return "browsing";
  if (l.includes("code") || l.includes("execute")) return "coding";
  if (l.includes("analy") || l.includes("calculat")) return "analyzing";
  return "tool_calling";
}

function getPreToolLine(role: string, act: string, _detail: string): string {
  const m: Record<string, Record<string, string>> = {
    researcher: { searching: "Let me look that up...", reading: "Reading through this...", default: "Pulling the data..." },
    analyst: { searching: "Let me verify that...", analyzing: "Running the numbers...", default: "Checking..." },
    writer: { writing: "Drafting now...", default: "Working on the text..." },
    browser: { browsing: "Navigating to the page...", default: "Opening the site..." },
    coder: { coding: "Writing the code...", default: "Let me code that up..." },
    reviewer: { default: "Checking this..." },
  };
  const roleMap = m[role] ?? {};
  return roleMap[act] ?? roleMap.default ?? "";
}

function getPostToolLine(role: string, summary: string, success: boolean): string {
  if (!success) {
    const f: Record<string, string> = {
      researcher: "Couldn't find what I needed.",
      analyst: "The data isn't available.",
      browser: "Page didn't load.",
      coder: "Hit an error.",
      default: "That didn't work.",
    };
    return f[role] ?? f.default;
  }
  // Only narrate short results — long ones speak for themselves
  if (summary.length <= 80) return summary;
  return "";
}

const PRE_LINES: Record<string, { start: string }> = {
  researcher: { start: "On it. Let me find the data..." },
  analyst: { start: "Looking at the numbers..." },
  writer: { start: "Starting the draft..." },
  reviewer: { start: "Let me review this..." },
  browser: { start: "Opening the page..." },
  coder: { start: "Writing the code..." },
  supervisor: { start: "Evaluating..." },
};

const REVISE_LINES: Record<string, string> = {
  writer: "Got it. Revising the draft...",
  coder: "Fixing that now...",
  analyst: "Recalculating with the correction...",
  researcher: "Pulling the updated data...",
  default: "Revising now...",
};