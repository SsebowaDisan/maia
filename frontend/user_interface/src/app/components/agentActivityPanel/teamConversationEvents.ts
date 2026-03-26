import type { CollaborationEntry } from "../../../api/client";
import { readEventPayload } from "../../utils/eventPayload";
import { sanitizeComputerUseText } from "../../utils/userFacingComputerUse";
import type { AgentActivityEvent } from "../../types";
import { EVT_AGENT_DIALOGUE_TURN } from "../../constants/eventTypes";
import { fromAgentActivityEvent } from "@maia/theatre";

import {
  CONVERSATION_ENTRY_TYPES,
  FALLBACK_EVENT_TYPES,
  PRIMARY_CONVERSATION_ENTRY_TYPES,
  type ConversationRow,
} from "./teamConversationTypes";
import {
  canonicalAgentId,
  displayAgentName,
  metadataMap,
  normalizeEntryType,
  speakerName,
  toTimestamp,
} from "./teamConversationUtils";

function isConversationFallbackType(type: string): boolean {
  const normalized = String(type || "").trim().toLowerCase();
  return Boolean(normalized) && (FALLBACK_EVENT_TYPES.has(normalized) || normalized === EVT_AGENT_DIALOGUE_TURN);
}

function rowTypeFromEvent(type: string, data: Record<string, unknown>): string {
  if (type === "team_chat_message") {
    return String(data.entry_type || "").trim().toLowerCase() === "summary" ? "summary" : "chat";
  }
  if (!type.startsWith("agent_dialogue")) return "message";
  const turnRole = String(data.turn_role || "").trim().toLowerCase();
  if (turnRole === "request") return "question";
  if (turnRole === "response") return "answer";
  if (turnRole === "integration") return "dialogue";
  if (turnRole === "handoff") return "handoff";
  if (turnRole === "review") return "review";
  const turnType = String(data.turn_type || "").trim().toLowerCase();
  if (turnType === "question" || turnType.endsWith("_request") || turnType.endsWith("_question")) return "question";
  if (turnType === "answer" || turnType === "response" || turnType.endsWith("_response") || turnType.endsWith("_answer")) return "answer";
  if (turnType === "handoff") return "handoff";
  return "dialogue";
}

function sourceAgentForEvent(type: string, data: Record<string, unknown>, event: AgentActivityEvent): string {
  if (type.startsWith("assembly_") || type.startsWith("brain_")) return "Brain";
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
  if (type === "assembly_step_added") return speakerName(data.agent_role || data.step_agent_id || data.step_role, "Agent");
  if (type === "assembly_connector_needed") return "Connector setup";
  if (type.startsWith("tool_")) {
    const toolLabel = String(data.tool_label || data.tool_id || data.tool || "").trim();
    if (toolLabel) return speakerName(toolLabel, "Tool");
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
    if (!isConversationFallbackType(type)) continue;
    const data = readEventPayload(event);
    const sdkEvent = fromAgentActivityEvent({
      event_id: String(event.event_id || "").trim(),
      run_id: String(event.run_id || "").trim(),
      seq: event.seq,
      ts: typeof event.ts === "string" ? event.ts : undefined,
      stage: event.stage,
      status: event.status,
      event_type: String(event.event_type || event.type || "").trim(),
      title: String(event.title || "").trim(),
      detail: String(event.detail || "").trim(),
      timestamp: String(event.timestamp || event.ts || ""),
      data: event.data,
      event_family: event.event_family,
      event_render_mode: event.event_render_mode,
      event_replay_importance: event.event_replay_importance,
      replay_importance: event.replay_importance,
      event_index: event.event_index,
      graph_node_id: event.graph_node_id,
      scene_ref: event.scene_ref,
      snapshot_ref: event.snapshot_ref,
      metadata: event.metadata,
    });
    const execution = sdkEvent.payload.execution;
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
        acp_agent_id: sdkEvent.agent_id,
        acp_sequence: sdkEvent.sequence,
        acp_timestamp: sdkEvent.timestamp,
        execution_stage: execution?.stage,
        execution_status: execution?.status,
        scene_surface: execution?.scene_surface ?? data.scene_surface,
        scene_family: execution?.scene_family ?? data.scene_family,
        ui_target: execution?.ui_target,
        browser_url: execution?.browser_state?.url,
        browser_title: execution?.browser_state?.title,
        email_recipient: execution?.email_state?.recipient ?? data.email_recipient,
        email_subject: execution?.email_state?.subject ?? data.email_subject,
        document_url: execution?.document_state?.document_url ?? data.document_url,
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
  if (!normalized) return false;
  if (normalized.includes(".") || normalized.includes("/") || normalized.includes(":")) return true;
  const tokens = normalized.split(/[\s._:/-]+/).map((token) => token.trim()).filter(Boolean);
  const toolishTokens = new Set(["playwright", "browser", "tool", "connector", "provider"]);
  return tokens.some((token) => toolishTokens.has(token));
}

export function filterConversationRows(rows: ConversationRow[]): ConversationRow[] {
  const filtered = rows.filter((row) => {
    const message = String(row.message || "").trim();
    if (!message || looksLikeMachineIdentifier(message) || message.toLowerCase().startsWith("provider:")) return false;
    const fromAgent = String(row.from_agent || "").trim().toLowerCase();
    const toAgent = String(row.to_agent || "").trim().toLowerCase();
    if (looksLikeToolOrRuntimeIdentifier(fromAgent) || looksLikeToolOrRuntimeIdentifier(toAgent)) return false;
    if (fromAgent && toAgent && fromAgent === toAgent) return false;
    const metadata = metadataMap(row);
    const eventType = String(metadata.event_type || "").trim().toLowerCase();
    const turnType = String(metadata.turn_type || "").trim().toLowerCase();
    const interactionLabel = String(metadata.interaction_label || "").trim().toLowerCase();
    const isConversationEventType = eventType === "team_chat_message" || eventType === EVT_AGENT_DIALOGUE_TURN;
    const messageType = String(metadata.message_type || "").trim().toLowerCase();
    if (!CONVERSATION_ENTRY_TYPES.has(row.entry_type)) return false;
    if (turnType === "status" || turnType === "update") return false;
    if (messageType === "thinking" || row.entry_type === "status") return false;
    if (interactionLabel === "status" || interactionLabel === "update") return false;
    if (metadata.narration === true) return false;
    if (eventType.startsWith("assembly_") || eventType.startsWith("workflow_") || eventType.startsWith("tool_") || eventType.startsWith("api_call_")) return false;
    const isPlanningMarker = !isConversationEventType && (metadata.from_step != null || metadata.to_step != null || metadata.connector_id != null);
    if (isPlanningMarker) return false;
    if (row.entry_type === "message" && eventType !== "team_chat_message") return false;
    return true;
  });

  const hasPrimaryRows = filtered.some((row) => {
    const eventType = String(metadataMap(row).event_type || "").trim().toLowerCase();
    return PRIMARY_CONVERSATION_ENTRY_TYPES.has(row.entry_type) || eventType === "team_chat_message" || eventType === EVT_AGENT_DIALOGUE_TURN;
  });

  if (!hasPrimaryRows) return filtered;
  return filtered.filter((row) => {
    const eventType = String(metadataMap(row).event_type || "").trim().toLowerCase();
    return eventType === "team_chat_message" || eventType === EVT_AGENT_DIALOGUE_TURN || PRIMARY_CONVERSATION_ENTRY_TYPES.has(row.entry_type);
  });
}
