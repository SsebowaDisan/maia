import type { ConversationDetail } from "../../api/client";
import { EVT_INTERACTION_SUGGESTION } from "../constants/eventTypes";
import { normalizeCanvasDocuments, normalizeMessageBlocks } from "../messageBlocks";
import type { AgentActivityEvent, ChatTurn } from "../types";

type ConversationMessageMeta = {
  mode?: "ask" | "company_agent" | "deep_search" | "web_search";
  mode_requested?: string | null;
  mode_actually_used?: string | null;
  mode_scope_statement?: string | null;
  mode_status_message?: string | null;
  halt_reason?: string | null;
  halt_message?: string | null;
  perf?: Record<string, unknown>;
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
  blocks?: unknown[];
  documents?: unknown[];
};

const MODE_SCOPE_STATEMENTS: Record<string, string> = {
  company_agent: "Agent mode: I will execute tools and complete the workflow end-to-end.",
  deep_search:
    "Deep search: I will query multiple sources, synthesize evidence, and cite each key claim.",
  web_search:
    "Web search: I will browse relevant sources on the web and summarize findings with citations.",
};

function resolveTurnMode(
  rawMode: ConversationMessageMeta["mode"],
  infoPanel: ConversationMessageMeta["info_panel"],
): ChatTurn["mode"] {
  const modeVariant = String(
    (
      infoPanel as {
        mode_variant?: unknown;
      } | undefined
    )?.mode_variant || "",
  )
    .trim()
    .toLowerCase();
  return rawMode === "deep_search" && modeVariant === "web_search"
    ? "web_search"
    : rawMode;
}

function resolveModeStatus({
  index,
  requestedMode,
  actualMode,
  scopeStatement,
  message,
}: {
  index: number;
  requestedMode: string;
  actualMode: string;
  scopeStatement: string | null;
  message: string | null;
}): ChatTurn["modeStatus"] {
  if (requestedMode && actualMode && requestedMode !== actualMode) {
    return {
      state: "downgraded",
      requestedMode,
      actualMode,
      message:
        message ||
        `Mode changed from ${requestedMode.replace(/_/g, " ")} to ${actualMode.replace(/_/g, " ")}.`,
      scopeStatement: scopeStatement || undefined,
    };
  }
  if (index === 0 && requestedMode && requestedMode !== "ask") {
    return {
      state: "committed",
      requestedMode,
      actualMode: actualMode || requestedMode,
      scopeStatement: scopeStatement || MODE_SCOPE_STATEMENTS[requestedMode] || null,
      message: message || null,
    };
  }
  return null;
}

type AgentEventRow = {
  type?: unknown;
  payload?: unknown;
  data?: unknown;
  event?: unknown;
};

function normalizeAgentActivityEvent(payload: unknown): AgentActivityEvent | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const candidate = payload as Record<string, unknown>;
  if (!("event_id" in candidate) || !("event_type" in candidate)) {
    return null;
  }

  const normalized = {
    ...(candidate as AgentActivityEvent),
    metadata:
      candidate.metadata && typeof candidate.metadata === "object"
        ? (candidate.metadata as Record<string, unknown>)
        : {},
  } as AgentActivityEvent;

  if (
    (!normalized.data || typeof normalized.data !== "object") &&
    candidate.payload &&
    typeof candidate.payload === "object"
  ) {
    normalized.data = candidate.payload as Record<string, unknown>;
  }

  return normalized;
}

export function isAgentActivityEvent(payload: unknown): payload is AgentActivityEvent {
  return normalizeAgentActivityEvent(payload) !== null;
}

export function extractAgentEvents(rows: unknown[]): AgentActivityEvent[] {
  const events: AgentActivityEvent[] = [];
  for (const row of rows) {
    const rowRecord = row && typeof row === "object" ? (row as AgentEventRow & Record<string, unknown>) : null;
    const rowType = String(rowRecord?.type ?? "").trim().toLowerCase();
    if (rowType && rowType !== "event") {
      continue;
    }

    let candidate: unknown = row;
    if (rowRecord && rowType === "event") {
      candidate = rowRecord.payload ?? rowRecord.data ?? rowRecord.event ?? null;
    } else if (rowRecord && !("event_id" in rowRecord) && ("payload" in rowRecord || "data" in rowRecord)) {
      candidate = rowRecord.payload ?? rowRecord.data ?? null;
    }

    const event = normalizeAgentActivityEvent(candidate);
    if (event) {
      events.push(event);
    }
  }
  return events;
}

export function splitAgentEventsBySuggestionType(events: AgentActivityEvent[]): {
  primaryEvents: AgentActivityEvent[];
  suggestionEvents: AgentActivityEvent[];
} {
  const primaryEvents: AgentActivityEvent[] = [];
  const suggestionEvents: AgentActivityEvent[] = [];
  for (const event of events) {
    if (String(event.event_type || "").trim().toLowerCase() === EVT_INTERACTION_SUGGESTION) {
      suggestionEvents.push(event);
      continue;
    }
    primaryEvents.push(event);
  }
  return { primaryEvents, suggestionEvents };
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
  const turns: ChatTurn[] = messages.map((entry, index) => {
    const assistant = entry[1] || "";
    const rawMode = messageMeta[index]?.mode || "ask";
    const resolvedMode = resolveTurnMode(rawMode, messageMeta[index]?.info_panel);
    const requestedMode = String(messageMeta[index]?.mode_requested || resolvedMode || "ask")
      .trim()
      .toLowerCase();
    const actualMode = String(messageMeta[index]?.mode_actually_used || resolvedMode || requestedMode || "ask")
      .trim()
      .toLowerCase();
    const haltReason = String(messageMeta[index]?.halt_reason || "").trim();
    const haltMessage = String(messageMeta[index]?.halt_message || "").trim();
    const modeStatus = resolveModeStatus({
      index,
      requestedMode,
      actualMode,
      scopeStatement: messageMeta[index]?.mode_scope_statement || null,
      message: messageMeta[index]?.mode_status_message || null,
    });
    return {
      user: entry[0] || "",
      assistant,
      blocks: normalizeMessageBlocks(messageMeta[index]?.blocks, assistant),
      documents: normalizeCanvasDocuments(messageMeta[index]?.documents),
      attachments: mapMessageAttachments(messageMeta[index]?.attachments),
      info: retrievalMessages[index] || "",
      plot: (plotHistory[index] as Record<string, unknown> | null | undefined) ?? null,
      mode: resolvedMode,
      modeRequested: requestedMode || "ask",
      modeActuallyUsed: actualMode || requestedMode || "ask",
      modeStatus,
      haltReason: haltReason || null,
      haltMessage: haltMessage || null,
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
    };
  });
  const runIds = Array.from(
    new Set(
      turns
        .map((turn) => turn.activityRunId)
        .filter((value): value is string => Boolean(value)),
    ),
  );
  return { turns, runIds };
}
