import type { ConversationDetail } from "../../api/client";
import type { AgentActivityEvent, ChatTurn } from "../types";

type ConversationMessageMeta = {
  mode?: "ask" | "company_agent";
  actions_taken?: ChatTurn["actionsTaken"];
  sources_used?: ChatTurn["sourcesUsed"];
  source_usage?: ChatTurn["sourceUsage"];
  attachments?: Array<{ name?: string; file_id?: string; fileId?: string }>;
  next_recommended_steps?: string[];
  needs_human_review?: boolean;
  human_review_notes?: string | null;
  activity_run_id?: string | null;
  web_summary?: Record<string, unknown>;
  info_panel?: Record<string, unknown>;
  mindmap?: Record<string, unknown>;
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

function mapMessageAttachments(
  attachments: ConversationMessageMeta["attachments"],
): ChatTurn["attachments"] {
  if (!Array.isArray(attachments) || attachments.length <= 0) {
    return undefined;
  }
  const normalized = attachments
    .map((item) => {
      if (!item || typeof item !== "object") {
        return null;
      }
      const name = String(item.name || "").trim();
      const fileId = String(item.file_id || item.fileId || "").trim();
      if (!name && !fileId) {
        return null;
      }
      return {
        name: name || fileId || "Uploaded file",
        fileId: fileId || undefined,
      };
    })
    .filter(
      (
        item,
      ): item is {
        name: string;
        fileId?: string;
      } => Boolean(item),
    );
  return normalized.length > 0 ? normalized : undefined;
}

export function buildConversationTurns(
  detail: ConversationDetail,
): { turns: ChatTurn[]; runIds: string[] } {
  const messages = detail.data_source?.messages || [];
  const retrievalMessages = detail.data_source?.retrieval_messages || [];
  const plotHistory = detail.data_source?.plot_history || [];
  const messageMeta = (detail.data_source?.message_meta || []) as ConversationMessageMeta[];
  const turns: ChatTurn[] = messages.map((entry, index) => ({
    user: entry[0] || "",
    assistant: entry[1] || "",
    attachments: mapMessageAttachments(messageMeta[index]?.attachments),
    info: retrievalMessages[index] || "",
    plot: (plotHistory[index] as Record<string, unknown> | null | undefined) ?? null,
    mode: messageMeta[index]?.mode || "ask",
    actionsTaken: messageMeta[index]?.actions_taken || [],
    sourcesUsed: messageMeta[index]?.sources_used || [],
    sourceUsage: messageMeta[index]?.source_usage || [],
    nextRecommendedSteps: messageMeta[index]?.next_recommended_steps || [],
    needsHumanReview: Boolean(messageMeta[index]?.needs_human_review),
    humanReviewNotes: messageMeta[index]?.human_review_notes || null,
    webSummary: messageMeta[index]?.web_summary || {},
    infoPanel: messageMeta[index]?.info_panel || {},
    mindmap:
      messageMeta[index]?.mindmap ||
      ((messageMeta[index]?.info_panel as { mindmap?: Record<string, unknown> } | undefined)
        ?.mindmap || {}),
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
