import { sanitizeComputerUseText } from "../../utils/userFacingComputerUse";

import type {
  ConversationBubble,
  ConversationGroup,
  ConversationRosterMember,
  ConversationRow,
} from "./teamConversationTypes";
import { toACPConversationEvent } from "./teamConversationACP";
import {
  actionLabel,
  audienceLabel,
  avatarSeed,
  badgeLabel,
  canonicalAgentId,
  displayAgentName,
  humanizeToken,
  initials,
  metadataMap,
  moodLabel,
  speakerRoleLabel,
  threadLabel,
} from "./teamConversationUtils";

function replyPreviewMap(rows: ConversationRow[]): Map<string, string> {
  const previewMap = new Map<string, string>();
  const messageMap = new Map<string, string>();
  for (const row of rows) {
    const metadata = metadataMap(row);
    const messageId = String(metadata.message_id || metadata.event_id || "").trim();
    if (messageId) {
      messageMap.set(messageId, String(row.message || "").trim());
    }
  }
  for (const row of rows) {
    const metadata = metadataMap(row);
    const rowId = String(metadata.message_id || metadata.event_id || "").trim();
    const replyToId = String(metadata.reply_to_id || "").trim();
    if (!rowId || !replyToId) continue;
    const preview = messageMap.get(replyToId);
    if (preview) previewMap.set(rowId, preview.slice(0, 88));
  }
  return previewMap;
}

function toBubble(row: ConversationRow, rowIndex: number, replies: Map<string, string>): ConversationBubble {
  const metadata = metadataMap(row);
  const acpEvent = toACPConversationEvent(row);
  const bubbleMessageId =
    (acpEvent.event_type === "message" && acpEvent.payload.context?.message_id) ||
    String(metadata.message_id || metadata.event_id || `${row.timestamp}-${rowIndex}`);
  const deliveryStatus =
    acpEvent.event_type === "message"
      ? String(acpEvent.payload.context?.delivery_status || "").trim().toLowerCase()
      : "";
  const requiresAck =
    acpEvent.event_type === "message"
      ? acpEvent.payload.context?.requires_ack === true
      : acpEvent.event_type === "handoff"
        ? acpEvent.payload.requires_ack === true
        : false;
  const mentions =
    acpEvent.event_type === "message"
      ? (acpEvent.payload.context?.mentions || []).map((value) => String(value).trim()).filter(Boolean)
      : [];

  return {
    id: bubbleMessageId,
    messageId: bubbleMessageId,
    text: sanitizeComputerUseText(row.message || "") || "Update",
    entryType: row.entry_type,
    badge: badgeLabel(row),
    action: actionLabel(row),
    timestamp: row.timestamp,
    replyPreview: replies.get(bubbleMessageId) || "",
    deliveryStatus,
    requiresAck,
    mentions,
  };
}

export function toConversationGroups(rows: ConversationRow[]): ConversationGroup[] {
  const groups: ConversationGroup[] = [];
  const replies = replyPreviewMap(rows);
  rows.forEach((row, rowIndex) => {
    const from = sanitizeComputerUseText(row.from_agent || "Agent") || "Agent";
    const to = sanitizeComputerUseText(row.to_agent || "Agent") || "Agent";
    const threadInfo = threadLabel(row);
    const bubble = toBubble(row, rowIndex, replies);
    const last = groups[groups.length - 1];
    const sameSpeaker = last && last.from.toLowerCase() === from.toLowerCase();
    const sameAudience = last && last.to.toLowerCase() === to.toLowerCase();
    const sameThread = last && last.threadId === threadInfo.threadId;
    const closeInTime = last && row.timestamp - last.lastAt <= 90_000;
    if (last && sameSpeaker && sameAudience && sameThread && closeInTime) {
      last.bubbles.push(bubble);
      last.lastAt = row.timestamp;
      return;
    }
    groups.push({
      id: `group-${groups.length}-${row.timestamp}`,
      threadId: threadInfo.threadId,
      threadLabel: threadInfo.threadLabel,
      taskLabel: threadInfo.taskLabel,
      from,
      to,
      role: speakerRoleLabel(row),
      avatarLabel: initials(from),
      avatarColor: avatarSeed(from),
      mood: moodLabel(row),
      startedAt: row.timestamp,
      lastAt: row.timestamp,
      audience: audienceLabel(from, to),
      bubbles: [bubble],
    });
  });
  return groups;
}

export function toConversationRoster(rows: ConversationRow[]): ConversationRosterMember[] {
  const now = Date.now();
  const roster = new Map<
    string,
    {
      id: string;
      name: string;
      role: string;
      lastAt: number;
      threadIds: Set<string>;
      sentCount: number;
      receivedCount: number;
      pendingAckCount: number;
      mentionCount: number;
      focusLabel: string;
    }
  >();

  const ensureMember = (id: string, name: string, role: string) => {
    const key = String(id || "").trim().toLowerCase();
    if (!key || key === "team") return null;
    let current = roster.get(key);
    if (!current) {
      current = {
        id: key,
        name: name || "Agent",
        role,
        lastAt: 0,
        threadIds: new Set<string>(),
        sentCount: 0,
        receivedCount: 0,
        pendingAckCount: 0,
        mentionCount: 0,
        focusLabel: "",
      };
      roster.set(key, current);
    } else {
      if (name && (!current.name || current.name === "Agent")) current.name = name;
      if (role && !current.role) current.role = role;
    }
    return current;
  };

  rows.forEach((row) => {
    const metadata = metadataMap(row);
    const acpEvent = toACPConversationEvent(row);
    const source = ensureMember(canonicalAgentId(row, "from"), displayAgentName(row, "from"), speakerRoleLabel(row));
    const target = ensureMember(canonicalAgentId(row, "to"), displayAgentName(row, "to"), humanizeToken(metadata.target_role || metadata.to_role, ""));
    const threadInfo = threadLabel(row);

    if (source) {
      source.lastAt = Math.max(source.lastAt, row.timestamp);
      source.threadIds.add(threadInfo.threadId);
      source.sentCount += 1;
      if (threadInfo.taskLabel) source.focusLabel = threadInfo.taskLabel;
    }
    if (target) {
      target.lastAt = Math.max(target.lastAt, row.timestamp);
      target.threadIds.add(threadInfo.threadId);
      target.receivedCount += 1;
      if (!target.focusLabel && threadInfo.taskLabel) target.focusLabel = threadInfo.taskLabel;
    }

    const mentions =
      acpEvent.event_type === "message"
        ? (acpEvent.payload.context?.mentions || []).map((value) => sanitizeComputerUseText(value).trim().toLowerCase()).filter(Boolean)
        : [];
    if (mentions.length > 0) {
      for (const [memberId, member] of roster.entries()) {
        const memberName = member.name.trim().toLowerCase();
        if (mentions.includes(memberId) || (memberName && mentions.includes(memberName))) {
          member.mentionCount += 1;
          member.lastAt = Math.max(member.lastAt, row.timestamp);
        }
      }
    }

    const requiresAck =
      acpEvent.event_type === "message"
        ? acpEvent.payload.context?.requires_ack === true
        : acpEvent.event_type === "handoff"
          ? acpEvent.payload.requires_ack === true
          : false;
    if (requiresAck && target) {
      const ackedBy =
        acpEvent.event_type === "message"
          ? (acpEvent.payload.context?.acked_by || []).map((value) => sanitizeComputerUseText(value).trim().toLowerCase()).filter(Boolean)
          : acpEvent.event_type === "handoff" && acpEvent.payload.accepted_by
            ? [sanitizeComputerUseText(acpEvent.payload.accepted_by).trim().toLowerCase()].filter(Boolean)
            : [];
      const targetMatched = ackedBy.includes(target.id) || ackedBy.includes(target.name.trim().toLowerCase());
      if (!targetMatched) target.pendingAckCount += 1;
    }
  });

  return [...roster.values()]
    .map((member) => {
      const ageMs = now - member.lastAt;
      let status: ConversationRosterMember["status"] = "idle";
      if (ageMs < 45_000) status = "active";
      else if (member.pendingAckCount > 0) status = "engaged";
      else if (member.mentionCount > 0 || member.threadIds.size > 1) status = "watching";
      return {
        id: member.id,
        name: member.name,
        role: member.role,
        avatarLabel: initials(member.name),
        avatarColor: avatarSeed(member.name),
        status,
        lastAt: member.lastAt,
        threadCount: member.threadIds.size,
        sentCount: member.sentCount,
        receivedCount: member.receivedCount,
        pendingAckCount: member.pendingAckCount,
        mentionCount: member.mentionCount,
        focusLabel: member.focusLabel,
      };
    })
    .sort((left, right) => {
      const statusOrder = { active: 0, engaged: 1, watching: 2, idle: 3 };
      return statusOrder[left.status] - statusOrder[right.status] || right.threadCount - left.threadCount || right.lastAt - left.lastAt;
    });
}
