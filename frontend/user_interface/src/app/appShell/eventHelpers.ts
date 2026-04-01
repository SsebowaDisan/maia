import type { ConversationDetail } from "../../api/client";
import { EVT_INTERACTION_SUGGESTION } from "../constants/eventTypes";
import {
  normalizeCanvasDocuments,
  normalizeMessageBlocks,
  type CanvasDocumentRecord,
} from "../messageBlocks";
import type { AgentActivityEvent, ChatTurn } from "../types";

type ConversationMessageMeta = {
  mode?: "ask" | "rag" | "company_agent" | "deep_search" | "web_search" | "brain";
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
  nextRecommendedSteps?: string[];
  needs_human_review?: boolean;
  human_review_notes?: string | null;
  activity_run_id?: string | null;
  web_summary?: Record<string, unknown>;
  info_panel?: Record<string, unknown>;
  infoPanel?: Record<string, unknown>;
  mindmap?: Record<string, unknown>;
  blocks?: unknown[];
  documents?: unknown[];
};

const MODE_SCOPE_STATEMENTS: Record<string, string> = {
  rag: "Library mode: I will search, summarize, and answer from Axon Group files and URLs, using citations.",
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
    : rawMode === "ask" && modeVariant === "rag"
      ? "rag"
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

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  return value as Record<string, unknown>;
}

function asString(value: unknown): string {
  if (typeof value === "string") {
    return value.trim();
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value).trim();
  }
  return "";
}

function titleFromEventType(eventType: string): string {
  if (!eventType) {
    return "Activity";
  }
  const compact = eventType.replace(/[._-]+/g, " ").trim();
  if (!compact) {
    return "Activity";
  }
  return compact.replace(/\b\w/g, (char) => char.toUpperCase());
}

function normalizeAgentActivityEvent(payload: unknown): AgentActivityEvent | null {
  const candidate = asRecord(payload);
  if (!candidate) {
    return null;
  }
  const eventId = asString(candidate.event_id);
  const eventType = asString(candidate.event_type).toLowerCase();
  if (!eventId || !eventType) {
    return null;
  }

  const metadataRecord = asRecord(candidate.metadata) || {};
  const dataRecord = asRecord(candidate.data);
  const payloadRecord = asRecord(candidate.payload);
  const runId =
    asString(candidate.run_id) || asString(candidate.runId) || asString(metadataRecord.run_id);
  const title =
    asString(candidate.title) || asString((candidate as Record<string, unknown>).message) || titleFromEventType(eventType);
  const detail =
    asString(candidate.detail) ||
    asString(candidate.status) ||
    asString((candidate as Record<string, unknown>).message);
  const timestamp =
    asString(candidate.timestamp) ||
    asString(candidate.ts) ||
    new Date().toISOString();

  if (!runId || !title || !timestamp) {
    return null;
  }

  return {
    ...(candidate as AgentActivityEvent),
    event_id: eventId,
    event_type: eventType,
    run_id: runId,
    title,
    detail,
    timestamp,
    metadata: metadataRecord,
    data: dataRecord || payloadRecord || undefined,
  };
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

function asCanvasDocumentRecord(value: unknown): CanvasDocumentRecord | null {
  const row = asRecord(value);
  if (!row) {
    return null;
  }
  const id = asString(row.id || row.document_id || row.documentId);
  const title = asString(row.title || row.name || row.document_title || row.documentTitle);
  if (!id || !title) {
    return null;
  }
  return {
    id,
    title,
    content: String(row.content ?? row.markdown ?? row.body ?? ""),
    infoHtml: String(row.info_html ?? row.infoHtml ?? ""),
    userPrompt: String(row.user_prompt ?? row.userPrompt ?? ""),
    modeVariant: String(row.mode_variant ?? row.modeVariant ?? ""),
  };
}

function readCanvasToolId(event: AgentActivityEvent): string {
  const data = asRecord(event.data) || {};
  const metadata = asRecord(event.metadata) || {};
  return asString(data.tool_id || metadata.tool_id || event.event_type).toLowerCase();
}

export function extractCanvasDocumentFromToolEvent(
  event: AgentActivityEvent,
): CanvasDocumentRecord | null {
  const eventType = asString(event.event_type).toLowerCase();
  if (eventType !== "tool_completed") {
    return null;
  }
  const toolId = readCanvasToolId(event);
  if (toolId !== "canvas.create_document") {
    return null;
  }

  const data = asRecord(event.data) || {};
  const metadata = asRecord(event.metadata) || {};
  const candidates: unknown[] = [
    data.document,
    data.result,
    data.output,
    data.created_document,
    data.document_record,
    metadata.document,
    metadata.result,
    metadata.output,
    metadata.created_document,
    metadata.document_record,
    data,
    metadata,
  ];
  for (const candidate of candidates) {
    const normalized = asCanvasDocumentRecord(candidate);
    if (normalized) {
      return normalized;
    }
  }
  return null;
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
    const infoPanelMeta =
      messageMeta[index]?.info_panel && typeof messageMeta[index]?.info_panel === "object"
        ? (messageMeta[index]?.info_panel as Record<string, unknown>)
        : messageMeta[index]?.infoPanel && typeof messageMeta[index]?.infoPanel === "object"
          ? (messageMeta[index]?.infoPanel as Record<string, unknown>)
          : {};
    const rawMode = messageMeta[index]?.mode || "ask";
    const resolvedMode = resolveTurnMode(rawMode, infoPanelMeta);
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
      nextRecommendedSteps:
        messageMeta[index]?.next_recommended_steps || messageMeta[index]?.nextRecommendedSteps || [],
      needsHumanReview: Boolean(messageMeta[index]?.needs_human_review),
      humanReviewNotes: messageMeta[index]?.human_review_notes || null,
      webSummary: messageMeta[index]?.web_summary || {},
      infoPanel: infoPanelMeta,
      mindmap:
        messageMeta[index]?.mindmap ||
        ((infoPanelMeta as { mindmap?: Record<string, unknown> } | undefined)
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
