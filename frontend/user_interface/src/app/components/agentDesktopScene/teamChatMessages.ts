import type { AgentActivityEvent } from "../../types";
import {
  deriveFromEvents,
  filterConversationRows,
  mergeRows,
  type ConversationRow,
} from "../agentActivityPanel/teamConversationModel";
import type { TeamChatMessage } from "./skins/TeamChatSkin";

function avatarSeed(name: string): string {
  let hash = 0;
  for (let index = 0; index < name.length; index += 1) {
    hash = (hash << 5) - hash + name.charCodeAt(index);
    hash |= 0;
  }
  return `hsl(${Math.abs(hash) % 360} 70% 62%)`;
}

function initials(name: string): string {
  const tokens = String(name || "")
    .trim()
    .split(/[\s_\-.]+/)
    .filter(Boolean);
  if (!tokens.length) return "A";
  if (tokens.length === 1) return tokens[0].slice(0, 2).toUpperCase();
  return `${tokens[0][0] || ""}${tokens[1][0] || ""}`.toUpperCase();
}

function messageTypeForRow(row: ConversationRow): string {
  const metadata =
    row.metadata && typeof row.metadata === "object"
      ? (row.metadata as Record<string, unknown>)
      : {};
  const explicitType = String(metadata.message_type || "").trim().toLowerCase();
  if (explicitType) {
    return explicitType;
  }
  if (row.entry_type === "summary") {
    return "summary";
  }
  return "message";
}

function toTeamChatMessage(row: ConversationRow): TeamChatMessage {
  const metadata =
    row.metadata && typeof row.metadata === "object"
      ? (row.metadata as Record<string, unknown>)
      : {};
  const speakerName = String(metadata.speaker_name || row.from_agent || "Agent").trim() || "Agent";
  const speakerId = String(metadata.speaker_id || metadata.from_agent || row.from_agent || "agent").trim() || "agent";
  return {
    message_id:
      String(metadata.message_id || metadata.event_id || `${row.timestamp}-${speakerName}`)
        .trim() || `${row.timestamp}-${speakerName}`,
    speaker_id: speakerId,
    speaker_name: speakerName,
    speaker_role: String(metadata.speaker_role || metadata.role || metadata.agent_role || "").trim(),
    speaker_avatar: String(metadata.speaker_avatar || initials(speakerName)).trim() || initials(speakerName),
    speaker_color: String(metadata.speaker_color || avatarSeed(speakerName)).trim() || avatarSeed(speakerName),
    content: String(row.message || "").trim(),
    timestamp: Math.round(Number(row.timestamp || Date.now())),
    message_type: messageTypeForRow(row),
    mood: String(metadata.mood || "").trim().toLowerCase() || undefined,
    reply_to_id: String(metadata.reply_to_id || "").trim() || undefined,
    reaction: String(metadata.reaction || "").trim() || undefined,
  };
}

function singleMessageFallback(
  activeSceneData: Record<string, unknown>,
  activeDetail: string,
): TeamChatMessage[] {
  const speakerName = String(activeSceneData.speaker_name || "").trim();
  if (!speakerName) {
    return [];
  }
  const content = String(activeSceneData.content || activeDetail || "").trim();
  if (!content) {
    return [];
  }
  return [
    {
      message_id: String(activeSceneData.message_id || `${Date.now()}-${speakerName}`).trim(),
      speaker_id: String(activeSceneData.speaker_id || speakerName).trim() || speakerName,
      speaker_name: speakerName,
      speaker_role: String(activeSceneData.speaker_role || "").trim(),
      speaker_avatar: String(activeSceneData.speaker_avatar || initials(speakerName)).trim() || initials(speakerName),
      speaker_color: String(activeSceneData.speaker_color || avatarSeed(speakerName)).trim() || avatarSeed(speakerName),
      content,
      timestamp: Math.round(Number(activeSceneData.timestamp || Date.now() / 1000)),
      message_type: String(activeSceneData.message_type || "message").trim().toLowerCase() || "message",
      mood: String(activeSceneData.mood || "").trim().toLowerCase() || undefined,
      reply_to_id: String(activeSceneData.reply_to_id || "").trim() || undefined,
      reaction: String(activeSceneData.reaction || "").trim() || undefined,
    },
  ];
}

export function buildTeamChatMessages(
  visibleEvents: AgentActivityEvent[],
  activeSceneData: Record<string, unknown>,
  activeDetail: string,
): TeamChatMessage[] {
  const fallbackRows = deriveFromEvents(visibleEvents);
  const rows = filterConversationRows(mergeRows([], fallbackRows));
  if (rows.length > 0) {
    return rows.map(toTeamChatMessage);
  }
  return singleMessageFallback(activeSceneData, activeDetail);
}
