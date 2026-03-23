import type { CollaborationEntry } from "../../../api/client";
import { readEventPayload } from "../../utils/eventPayload";
import { sanitizeComputerUseText } from "../../utils/userFacingComputerUse";
import type { AgentActivityEvent } from "../../types";
import { EVT_AGENT_DIALOGUE_TURN } from "../../constants/eventTypes";

const FALLBACK_EVENT_TYPES = new Set<string>([
  "team_chat_message",
  EVT_AGENT_DIALOGUE_TURN,
]);

const CONVERSATION_ENTRY_TYPES = new Set<string>([
  "chat",
  "question",
  "answer",
  "challenge",
  "revision",
  "dialogue",
  "disagreement",
  "handoff",
  "review",
  "summary",
  "message",
]);

const PRIMARY_CONVERSATION_ENTRY_TYPES = new Set<string>([
  "chat",
  "question",
  "answer",
  "challenge",
  "revision",
  "summary",
]);

export type ConversationRow = CollaborationEntry & {
  entry_type: string;
  timestamp: number;
};

export type ConversationBubble = {
  id: string;
  messageId: string;
  text: string;
  entryType: string;
  badge: string;
  action: string;
  timestamp: number;
  replyPreview: string;
};

export type ConversationGroup = {
  id: string;
  from: string;
  to: string;
  role: string;
  avatarLabel: string;
  avatarColor: string;
  mood: string;
  startedAt: number;
  lastAt: number;
  audience: string;
  bubbles: ConversationBubble[];
};

function isConversationFallbackType(type: string): boolean {
  const normalized = String(type || "").trim().toLowerCase();
  if (!normalized) {
    return false;
  }
  if (FALLBACK_EVENT_TYPES.has(normalized)) {
    return true;
  }
  return normalized === "team_chat_message" || normalized === EVT_AGENT_DIALOGUE_TURN;
}

export function toTimestamp(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value > 10_000_000_000 ? value : value * 1000;
  }
  const parsed = new Date(String(value || "")).getTime();
  return Number.isFinite(parsed) ? parsed : Date.now();
}

function normalizeEntryType(row: CollaborationEntry): string {
  const raw = String(row.entry_type || "").trim().toLowerCase();
  if (raw === "chat" || raw === "summary" || raw === "reaction") {
    return raw;
  }
  if (raw === "thinking") {
    return "status";
  }
  if (raw === "response") {
    return "answer";
  }
  if (raw === "request") {
    return "question";
  }
  if (raw === "integration") {
    return "dialogue";
  }
  if (raw === "disagreement") {
    return "challenge";
  }
  return raw || "message";
}

function metadataMap(row: CollaborationEntry): Record<string, unknown> {
  return row.metadata && typeof row.metadata === "object"
    ? (row.metadata as Record<string, unknown>)
    : {};
}

function canonicalAgentId(row: CollaborationEntry, side: "from" | "to"): string {
  const metadata = metadataMap(row);
  const candidates =
    side === "from"
      ? [
          metadata.speaker_id,
          metadata.from_agent,
          row.from_agent,
          metadata.speaker_name,
        ]
      : [
          metadata.to_agent,
          metadata.audience,
          row.to_agent,
        ];
  for (const candidate of candidates) {
    const normalized = sanitizeComputerUseText(candidate).trim().toLowerCase();
    if (normalized) {
      return normalized;
    }
  }
  return side === "from" ? "agent" : "team";
}

function displayAgentName(row: CollaborationEntry, side: "from" | "to"): string {
  const metadata = metadataMap(row);
  const candidates =
    side === "from"
      ? [
          metadata.speaker_name,
          row.from_agent,
          metadata.speaker_id,
          metadata.from_agent,
        ]
      : [
          row.to_agent,
          metadata.audience,
          metadata.to_agent,
        ];
  for (const candidate of candidates) {
    const humanized = speakerName(candidate, "");
    if (humanized) {
      return humanized;
    }
  }
  return side === "from" ? "Agent" : "Team";
}

function rowTypeFromEvent(type: string, data: Record<string, unknown>): string {
  if (type === "team_chat_message") {
    return String(data.entry_type || "").trim().toLowerCase() === "summary" ? "summary" : "chat";
  }
  if (!type.startsWith("agent_dialogue")) {
    return "message";
  }
  const turnRole = String(data.turn_role || "").trim().toLowerCase();
  if (turnRole === "request") return "question";
  if (turnRole === "response") return "answer";
  if (turnRole === "integration") return "dialogue";
  if (turnRole === "handoff") return "handoff";
  if (turnRole === "review") return "review";
  const turnType = String(data.turn_type || "").trim().toLowerCase();
  if (turnType === "question" || turnType.endsWith("_request") || turnType.endsWith("_question")) {
    return "question";
  }
  if (turnType === "answer" || turnType === "response" || turnType.endsWith("_response") || turnType.endsWith("_answer")) {
    return "answer";
  }
  if (turnType === "handoff") return "handoff";
  return "dialogue";
}

function humanizeToken(value: unknown, fallback = ""): string {
  const raw = sanitizeComputerUseText(value).toLowerCase();
  if (!raw) {
    return fallback;
  }
  return raw.replace(/[_\-]+/g, " ").replace(/\s+/g, " ").trim();
}

function speakerName(value: unknown, fallback: string): string {
  const raw = sanitizeComputerUseText(value);
  if (!raw) {
    return fallback;
  }
  if (raw.toLowerCase() === "brain") {
    return "Brain";
  }
  const tokens = raw.split(/[_.\- ]+/).map((token) => token.trim()).filter(Boolean);
  if (!tokens.length) {
    return fallback;
  }
  return tokens.map((token) => `${token.charAt(0).toUpperCase()}${token.slice(1)}`).join(" ");
}

function sourceAgentForEvent(type: string, data: Record<string, unknown>, event: AgentActivityEvent): string {
  if (type.startsWith("assembly_") || type.startsWith("brain_")) {
    return "Brain";
  }
  return speakerName(
    data.speaker_name ||
      data.speaker_id ||
      data.from_agent ||
      data.source_agent ||
      data.from_role ||
      data.owner_role ||
      data.agent_role ||
      data.agent_id ||
      data.role ||
      event.metadata?.owner_role ||
      event.metadata?.from_agent ||
      event.metadata?.agent_role ||
      event.metadata?.step_agent_id ||
      event.metadata?.agent_id ||
      event.data?.owner_role ||
      event.data?.from_agent ||
      event.data?.agent_role ||
      event.data?.agent_id,
    "Agent",
  );
}

function targetAgentForEvent(type: string, data: Record<string, unknown>, fromAgent: string): string {
  if (type === "assembly_step_added") {
    return speakerName(data.agent_role || data.step_agent_id || data.step_role, "Agent");
  }
  if (type === "assembly_connector_needed") {
    return "Connector setup";
  }
  if (type.startsWith("tool_")) {
    const toolLabel = String(data.tool_label || data.tool_id || data.tool || "").trim();
    if (toolLabel) {
      return speakerName(toolLabel, "Tool");
    }
  }
  return speakerName(
    data.to_agent ||
      data.audience ||
      data.recipient ||
      data.target_agent ||
      data.child_agent_id ||
      data.next_agent ||
      data.next_role ||
      data.agent_role ||
      data.to_role,
    fromAgent.toLowerCase() === "brain" ? "Team" : "Agent",
  );
}

function messageForEvent(type: string, data: Record<string, unknown>, event: AgentActivityEvent): string {
  return sanitizeComputerUseText(
    data.message || data.content || data.question || data.answer || data.summary || event.detail || event.title || "",
  ).trim();
}

export function deriveFromEvents(events: AgentActivityEvent[]): CollaborationEntry[] {
  const rows: CollaborationEntry[] = [];
  for (const event of events) {
    const type = String(event.event_type || event.type || "").trim().toLowerCase();
    if (!isConversationFallbackType(type)) {
      continue;
    }
    const data = readEventPayload(event);
    const fromAgent = sourceAgentForEvent(type, data, event);
    const resolvedToAgent = targetAgentForEvent(type, data, fromAgent);
    rows.push({
      run_id: event.run_id,
      from_agent: fromAgent,
      to_agent: resolvedToAgent,
      message: messageForEvent(type, data, event),
      entry_type: rowTypeFromEvent(type, data),
      timestamp: toTimestamp(data.timestamp || event.ts || event.timestamp),
      metadata: {
        ...data,
        event_id: event.event_id,
        event_type: type,
        speaker_id: String(data.speaker_id || data.from_agent || fromAgent).trim(),
        speaker_name: String(data.speaker_name || fromAgent).trim(),
        from_agent: String(data.from_agent || fromAgent).trim(),
        to_agent: String(data.to_agent || resolvedToAgent).trim(),
      },
    });
  }
  return rows;
}

export function mergeRows(remoteRows: CollaborationEntry[], fallbackRows: CollaborationEntry[]): ConversationRow[] {
  const merged = new Map<string, ConversationRow>();
  for (const row of [...remoteRows, ...fallbackRows]) {
    const timestamp = toTimestamp(row.timestamp);
    const metadata = metadataMap(row);
    const eventId = String(metadata.event_id || "").trim();
    const messageId = String(metadata.message_id || "").trim();
    const key = messageId
      ? `${String(row.run_id || "").trim()}|${messageId}|${normalizeEntryType(row)}`
      : [
          canonicalAgentId(row, "from"),
          canonicalAgentId(row, "to"),
          String(row.message || "").trim().toLowerCase(),
          normalizeEntryType(row),
          String(timestamp),
          eventId,
        ].join("|");
    merged.set(key, {
      ...row,
      from_agent: displayAgentName(row, "from"),
      to_agent: displayAgentName(row, "to"),
      entry_type: normalizeEntryType(row),
      timestamp,
      metadata,
    });
  }
  return [...merged.values()].sort((left, right) => left.timestamp - right.timestamp);
}

function looksLikeMachineIdentifier(text: string): boolean {
  const normalized = String(text || "").trim();
  return Boolean(normalized && !/\s/.test(normalized) && /[._:/-]/.test(normalized) && /^[a-z0-9._:/-]+$/i.test(normalized));
}

function looksLikeToolOrRuntimeIdentifier(text: string): boolean {
  const normalized = String(text || "").trim().toLowerCase();
  if (!normalized) {
    return false;
  }
  if (normalized.includes(".") || normalized.includes("/") || normalized.includes(":")) {
    return true;
  }
  const tokens = normalized.split(/[\s._:/-]+/).map((token) => token.trim()).filter(Boolean);
  const toolishTokens = new Set(["playwright", "browser", "tool", "connector", "provider"]);
  return tokens.some((token) => toolishTokens.has(token));
}

export function filterConversationRows(rows: ConversationRow[]): ConversationRow[] {
  const filtered = rows.filter((row) => {
    const message = String(row.message || "").trim();
    if (!message || looksLikeMachineIdentifier(message) || message.toLowerCase().startsWith("provider:")) {
      return false;
    }
    const fromAgent = String(row.from_agent || "").trim().toLowerCase();
    const toAgent = String(row.to_agent || "").trim().toLowerCase();
    if (looksLikeToolOrRuntimeIdentifier(fromAgent) || looksLikeToolOrRuntimeIdentifier(toAgent)) {
      return false;
    }
    if (fromAgent && toAgent && fromAgent === toAgent) {
      return false;
    }
    const normalizedType = row.entry_type;
    const metadata = (row.metadata || {}) as Record<string, unknown>;
    const eventType = String(metadata.event_type || "").trim().toLowerCase();
    const turnType = String(metadata.turn_type || "").trim().toLowerCase();
    const interactionLabel = String(metadata.interaction_label || "").trim().toLowerCase();
    const isConversationEventType = eventType === "team_chat_message" || eventType === EVT_AGENT_DIALOGUE_TURN;
    const messageType = String(metadata.message_type || "").trim().toLowerCase();
    if (!CONVERSATION_ENTRY_TYPES.has(normalizedType)) return false;
    if (turnType === "status" || turnType === "update") return false;
    if (messageType === "thinking" || normalizedType === "status") return false;
    if (interactionLabel === "status" || interactionLabel === "update") return false;
    if (metadata.narration === true) return false;
    if (eventType.startsWith("assembly_") || eventType.startsWith("workflow_") || eventType.startsWith("tool_") || eventType.startsWith("api_call_")) {
      return false;
    }
    const isPlanningMarker = !isConversationEventType && (metadata.from_step != null || metadata.to_step != null || metadata.connector_id != null);
    if (isPlanningMarker) return false;
    if (normalizedType === "message" && eventType !== "team_chat_message") return false;
    return true;
  });

  const hasPrimaryRows = filtered.some((row) => {
    const eventType = String(((row.metadata || {}) as Record<string, unknown>).event_type || "").trim().toLowerCase();
    return PRIMARY_CONVERSATION_ENTRY_TYPES.has(row.entry_type) || eventType === "team_chat_message" || eventType === EVT_AGENT_DIALOGUE_TURN;
  });

  if (!hasPrimaryRows) {
    return filtered;
  }
  return filtered.filter((row) => {
    const eventType = String(((row.metadata || {}) as Record<string, unknown>).event_type || "").trim().toLowerCase();
    return eventType === "team_chat_message" || eventType === EVT_AGENT_DIALOGUE_TURN || PRIMARY_CONVERSATION_ENTRY_TYPES.has(row.entry_type);
  });
}

function avatarSeed(name: string): string {
  let hash = 0;
  for (let index = 0; index < name.length; index += 1) {
    hash = (hash << 5) - hash + name.charCodeAt(index);
    hash |= 0;
  }
  return `hsl(${Math.abs(hash) % 360} 70% 92%)`;
}

function initials(name: string): string {
  const tokens = String(name || "").trim().split(/[\s_\-.]+/).filter(Boolean);
  if (!tokens.length) return "A";
  if (tokens.length === 1) return tokens[0].slice(0, 2).toUpperCase();
  return `${tokens[0][0] || ""}${tokens[1][0] || ""}`.toUpperCase();
}

export function bubbleClass(entryType: string, fromAgent: string): string {
  const from = String(fromAgent || "").trim().toLowerCase();
  if (from === "brain") return "border-[#c7d2fe] bg-[#eef2ff]";
  if (entryType === "handoff") return "border-[#fde68a] bg-[#fffbeb]";
  if (entryType === "question") return "border-[#bfdbfe] bg-[#eff6ff]";
  if (entryType === "answer") return "border-[#bbf7d0] bg-[#ecfdf3]";
  if (entryType === "challenge" || entryType === "revision") return "border-[#fed7aa] bg-[#fff7ed]";
  if (entryType === "review") return "border-[#ddd6fe] bg-[#f5f3ff]";
  if (entryType === "summary") return "border-[#bfdbfe] bg-[#ecfeff]";
  return "border-[#e4e7ec] bg-[#f8fafc]";
}

function entryLabel(entryType: string): string {
  if (["handoff", "question", "answer", "challenge", "revision", "review", "dialogue", "summary", "chat"].includes(entryType)) {
    return entryType;
  }
  return "message";
}

function badgeLabel(row: ConversationRow): string {
  const metadata = row.metadata as Record<string, unknown> | undefined;
  const interactionLabel = humanizeToken(metadata?.interaction_label || metadata?.turn_type, "");
  return interactionLabel || entryLabel(row.entry_type);
}

function actionLabel(row: ConversationRow): string {
  const metadata = row.metadata as Record<string, unknown> | undefined;
  const operation = sanitizeComputerUseText(metadata?.operation_label || metadata?.action_label || metadata?.tool_label || "").trim();
  if (operation && operation.length <= 44) {
    return operation;
  }
  const family = humanizeToken(metadata?.scene_family, "");
  if (family === "chat" || family === "team chat") {
    return "";
  }
  return family;
}

function speakerRoleLabel(row: ConversationRow): string {
  const metadata = row.metadata as Record<string, unknown> | undefined;
  return humanizeToken(metadata?.speaker_role || metadata?.role || metadata?.agent_role, "");
}

function audienceLabel(from: string, to: string): string {
  const source = String(from || "").trim().toLowerCase();
  const target = String(to || "").trim();
  if (!target) return "";
  if (source === target.toLowerCase()) return "self";
  if (target.toLowerCase() === "team") return "to team";
  return `to ${target}`;
}

function moodLabel(row: ConversationRow): string {
  const mood = humanizeToken(((row.metadata || {}) as Record<string, unknown>).mood, "");
  return mood && mood !== "neutral" ? mood : "";
}

function replyPreviewMap(rows: ConversationRow[]): Map<string, string> {
  const previewMap = new Map<string, string>();
  const messageMap = new Map<string, string>();
  for (const row of rows) {
    const metadata = (row.metadata || {}) as Record<string, unknown>;
    const messageId = String(metadata.message_id || metadata.event_id || "").trim();
    if (messageId) {
      messageMap.set(messageId, String(row.message || "").trim());
    }
  }
  for (const row of rows) {
    const metadata = (row.metadata || {}) as Record<string, unknown>;
    const rowId = String(metadata.message_id || metadata.event_id || "").trim();
    const replyToId = String(metadata.reply_to_id || "").trim();
    if (!rowId || !replyToId) {
      continue;
    }
    const preview = messageMap.get(replyToId);
    if (preview) {
      previewMap.set(rowId, preview.slice(0, 88));
    }
  }
  return previewMap;
}

export function toConversationGroups(rows: ConversationRow[]): ConversationGroup[] {
  const groups: ConversationGroup[] = [];
  const replies = replyPreviewMap(rows);
  rows.forEach((row, rowIndex) => {
    const from = sanitizeComputerUseText(row.from_agent || "Agent") || "Agent";
    const to = sanitizeComputerUseText(row.to_agent || "Agent") || "Agent";
    const metadata = (row.metadata || {}) as Record<string, unknown>;
    const bubbleMessageId = String(metadata.message_id || metadata.event_id || `${row.timestamp}-${rowIndex}`);
    const bubble: ConversationBubble = {
      id: bubbleMessageId,
      messageId: bubbleMessageId,
      text: sanitizeComputerUseText(row.message || "") || "Update",
      entryType: row.entry_type,
      badge: badgeLabel(row),
      action: actionLabel(row),
      timestamp: row.timestamp,
      replyPreview: replies.get(bubbleMessageId) || "",
    };
    const last = groups[groups.length - 1];
    const role = speakerRoleLabel(row);
    const mood = moodLabel(row);
    const sameSpeaker = last && last.from.toLowerCase() === from.toLowerCase();
    const sameAudience = last && last.to.toLowerCase() === to.toLowerCase();
    const closeInTime = last && row.timestamp - last.lastAt <= 90_000;
    if (last && sameSpeaker && sameAudience && closeInTime) {
      last.bubbles.push(bubble);
      last.lastAt = row.timestamp;
      return;
    }
    groups.push({
      id: `group-${groups.length}-${row.timestamp}`,
      from,
      to,
      role,
      avatarLabel: initials(from),
      avatarColor: avatarSeed(from),
      mood,
      startedAt: row.timestamp,
      lastAt: row.timestamp,
      audience: audienceLabel(from, to),
      bubbles: [bubble],
    });
  });
  return groups;
}
