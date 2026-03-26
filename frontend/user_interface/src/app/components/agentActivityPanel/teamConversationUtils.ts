import type { CollaborationEntry } from "../../../api/client";
import { sanitizeComputerUseText } from "../../utils/userFacingComputerUse";

import type { ConversationRow } from "./teamConversationTypes";

export function toTimestamp(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value > 10_000_000_000 ? value : value * 1000;
  }
  const parsed = new Date(String(value || "")).getTime();
  return Number.isFinite(parsed) ? parsed : Date.now();
}

export function metadataMap(row: CollaborationEntry): Record<string, unknown> {
  return row.metadata && typeof row.metadata === "object"
    ? (row.metadata as Record<string, unknown>)
    : {};
}

export function humanizeToken(value: unknown, fallback = ""): string {
  const raw = sanitizeComputerUseText(value).toLowerCase();
  if (!raw) {
    return fallback;
  }
  return raw.replace(/[_\-]+/g, " ").replace(/\s+/g, " ").trim();
}

export function speakerName(value: unknown, fallback: string): string {
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

export function normalizeEntryType(row: CollaborationEntry): string {
  const raw = String(row.entry_type || "").trim().toLowerCase();
  if (raw === "chat" || raw === "summary" || raw === "reaction") return raw;
  if (raw === "thinking") return "status";
  if (raw === "response") return "answer";
  if (raw === "request") return "question";
  if (raw === "integration") return "dialogue";
  if (raw === "disagreement") return "challenge";
  return raw || "message";
}

export function canonicalAgentId(row: CollaborationEntry, side: "from" | "to"): string {
  const metadata = metadataMap(row);
  const candidates =
    side === "from"
      ? [metadata.speaker_id, metadata.from_agent, row.from_agent, metadata.speaker_name]
      : [metadata.to_agent, metadata.audience, row.to_agent];
  for (const candidate of candidates) {
    const normalized = sanitizeComputerUseText(candidate).trim().toLowerCase();
    if (normalized) {
      return normalized;
    }
  }
  return side === "from" ? "agent" : "team";
}

export function displayAgentName(row: CollaborationEntry, side: "from" | "to"): string {
  const metadata = metadataMap(row);
  const candidates =
    side === "from"
      ? [metadata.speaker_name, row.from_agent, metadata.speaker_id, metadata.from_agent]
      : [row.to_agent, metadata.audience, metadata.to_agent];
  for (const candidate of candidates) {
    const humanized = speakerName(candidate, "");
    if (humanized) {
      return humanized;
    }
  }
  return side === "from" ? "Agent" : "Team";
}

export function avatarSeed(name: string): string {
  let hash = 0;
  for (let index = 0; index < name.length; index += 1) {
    hash = (hash << 5) - hash + name.charCodeAt(index);
    hash |= 0;
  }
  return `hsl(${Math.abs(hash) % 360} 70% 92%)`;
}

export function initials(name: string): string {
  const tokens = String(name || "").trim().split(/[\s_\-.]+/).filter(Boolean);
  if (!tokens.length) return "A";
  if (tokens.length === 1) return tokens[0].slice(0, 2).toUpperCase();
  return `${tokens[0][0] || ""}${tokens[1][0] || ""}`.toUpperCase();
}

function entryLabel(entryType: string): string {
  if (["handoff", "question", "answer", "challenge", "revision", "review", "dialogue", "summary", "chat"].includes(entryType)) {
    return entryType;
  }
  return "message";
}

export function badgeLabel(row: ConversationRow): string {
  const metadata = metadataMap(row);
  const interactionLabel = humanizeToken(metadata.interaction_label || metadata.turn_type, "");
  return interactionLabel || entryLabel(row.entry_type);
}

export function threadLabel(row: ConversationRow): { threadId: string; threadLabel: string; taskLabel: string } {
  const metadata = metadataMap(row);
  const threadId = String(metadata.thread_id || metadata.conversation_id || "").trim();
  const taskLabel = sanitizeComputerUseText(metadata.task_title || metadata.task_id || "").trim();
  const resolvedThreadLabel = taskLabel || sanitizeComputerUseText(threadId).trim() || "General thread";
  return {
    threadId: threadId || resolvedThreadLabel.toLowerCase().replace(/\s+/g, "-"),
    threadLabel: resolvedThreadLabel,
    taskLabel,
  };
}

export function actionLabel(row: ConversationRow): string {
  const metadata = metadataMap(row);
  const operation = sanitizeComputerUseText(metadata.operation_label || metadata.action_label || metadata.tool_label || "").trim();
  if (operation && operation.length <= 44) {
    return operation;
  }
  const family = humanizeToken(metadata.scene_family, "");
  if (family === "chat" || family === "team chat") {
    return "";
  }
  return family;
}

export function speakerRoleLabel(row: ConversationRow): string {
  const metadata = metadataMap(row);
  return humanizeToken(metadata.speaker_role || metadata.role || metadata.agent_role, "");
}

export function audienceLabel(from: string, to: string): string {
  const source = String(from || "").trim().toLowerCase();
  const target = String(to || "").trim();
  if (!target) return "";
  if (source === target.toLowerCase()) return "self";
  if (target.toLowerCase() === "team") return "to team";
  return `to ${target}`;
}

export function moodLabel(row: ConversationRow): string {
  const mood = humanizeToken(metadataMap(row).mood, "");
  return mood && mood !== "neutral" ? mood : "";
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
