import type { CollaborationEntry } from "../../../api/client";

export const FALLBACK_EVENT_TYPES = new Set<string>([
  "team_chat_message",
  "agent_dialogue_turn",
]);

export const CONVERSATION_ENTRY_TYPES = new Set<string>([
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

export const PRIMARY_CONVERSATION_ENTRY_TYPES = new Set<string>([
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
  deliveryStatus: string;
  requiresAck: boolean;
  mentions: string[];
};

export type ConversationGroup = {
  id: string;
  threadId: string;
  threadLabel: string;
  taskLabel: string;
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

export type ConversationRosterMember = {
  id: string;
  name: string;
  role: string;
  avatarLabel: string;
  avatarColor: string;
  status: "active" | "engaged" | "watching" | "idle";
  lastAt: number;
  threadCount: number;
  sentCount: number;
  receivedCount: number;
  pendingAckCount: number;
  mentionCount: number;
  focusLabel: string;
};
