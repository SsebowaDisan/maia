import type { ConversationDetail } from "../../api/client";
import type { AgentActivityEvent, ChatTurn } from "../types";

type ConversationMessageMeta = {
  mode?: "ask" | "company_agent";
  actions_taken?: ChatTurn["actionsTaken"];
  sources_used?: ChatTurn["sourcesUsed"];
  next_recommended_steps?: string[];
  activity_run_id?: string | null;
};

export function isAgentActivityEvent(payload: unknown): payload is AgentActivityEvent {
  return Boolean(
    payload &&
      typeof payload === "object" &&
      "event_id" in (payload as object) &&
      "event_type" in (payload as object),
  );
}

export function extractAgentEvents(rows: Array<{ type: string; payload: unknown }>) {
  return rows
    .filter((row) => row.type === "event")
    .map((row) => row.payload)
    .filter(isAgentActivityEvent);
}

export function buildConversationTurns(
  detail: ConversationDetail,
): { turns: ChatTurn[]; runIds: string[] } {
  const messages = detail.data_source?.messages || [];
  const retrievalMessages = detail.data_source?.retrieval_messages || [];
  const messageMeta = (detail.data_source?.message_meta || []) as ConversationMessageMeta[];
  const turns: ChatTurn[] = messages.map((entry, index) => ({
    user: entry[0] || "",
    assistant: entry[1] || "",
    info: retrievalMessages[index] || "",
    mode: messageMeta[index]?.mode || "ask",
    actionsTaken: messageMeta[index]?.actions_taken || [],
    sourcesUsed: messageMeta[index]?.sources_used || [],
    nextRecommendedSteps: messageMeta[index]?.next_recommended_steps || [],
    activityRunId: messageMeta[index]?.activity_run_id || null,
  }));
  const runIds = Array.from(
    new Set(
      turns
        .map((turn) => turn.activityRunId)
        .filter((value): value is string => Boolean(value)),
    ),
  );
  return { turns, runIds };
}
