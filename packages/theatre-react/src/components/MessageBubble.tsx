/**
 * MessageBubble - renders a single agent message in the team thread.
 * Shows sender/recipient context, delivery state, task metadata, and reply links.
 */
import React from "react";
import type { ACPCapabilities, ACPEvent, ACPMessage } from "@maia/acp";
import { AgentAvatar } from "./AgentAvatar";
import { resolveTheatreTheme } from "../theme";
import type { TheatreThemeOverride } from "../theme";

export interface MessageBubbleProps {
  event: ACPEvent<ACPMessage>;
  agents?: Map<string, ACPCapabilities>;
  showThinking?: boolean;
  compact?: boolean;
  replyLookup?: Map<string, ACPMessage>;
  theme?: TheatreThemeOverride;
}

const INTENT_BADGE: Record<string, { label: string; className: string }> = {
  propose: { label: "Proposal", className: "bg-sky-500/10 text-sky-700 dark:text-sky-300" },
  challenge: { label: "Challenge", className: "bg-rose-500/10 text-rose-700 dark:text-rose-300" },
  clarify: { label: "Question", className: "bg-amber-500/10 text-amber-700 dark:text-amber-300" },
  review: { label: "Review", className: "bg-violet-500/10 text-violet-700 dark:text-violet-300" },
  handoff: { label: "Handoff", className: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" },
  summarize: { label: "Summary", className: "bg-slate-500/10 text-slate-700 dark:text-slate-300" },
  agree: { label: "Alignment", className: "bg-teal-500/10 text-teal-700 dark:text-teal-300" },
  escalate: { label: "Escalation", className: "bg-orange-500/10 text-orange-700 dark:text-orange-300" },
};

const DELIVERY_BADGE: Record<string, string> = {
  draft: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  queued: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  sent: "bg-sky-500/10 text-sky-700 dark:text-sky-300",
  delivered: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  acknowledged: "bg-teal-500/10 text-teal-700 dark:text-teal-300",
  failed: "bg-rose-500/10 text-rose-700 dark:text-rose-300",
};

function formatTime(timestamp: string): string {
  try {
    return new Date(timestamp).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function agentLabel(agentId: string | undefined, agents?: Map<string, ACPCapabilities>): string {
  if (!agentId) {
    return "Unknown";
  }
  return agents?.get(agentId)?.name ?? agentId.replace("agent://", "");
}

function compactText(input: string | undefined, maxLength = 120): string {
  const text = String(input ?? "").trim();
  if (!text) {
    return "";
  }
  return text.length > maxLength ? `${text.slice(0, maxLength - 3)}...` : text;
}

export function MessageBubble({
  event,
  agents,
  showThinking,
  compact,
  replyLookup,
  theme,
}: MessageBubbleProps) {
  const resolvedTheme = resolveTheatreTheme(theme);
  const msg = event.payload;
  const context = msg.context ?? {};
  const agentId = msg.from ?? event.agent_id;
  const caps = agents?.get(agentId);
  const recipientCaps = msg.to ? agents?.get(msg.to) : undefined;
  const recipientLabel = msg.to === "agent://broadcast"
    ? "everyone"
    : recipientCaps?.name ?? msg.to?.replace("agent://", "");
  const badge = INTENT_BADGE[msg.intent] ?? INTENT_BADGE.propose;
  const deliveryStatus = context.delivery_status;
  const replyMessage = context.in_reply_to ? replyLookup?.get(context.in_reply_to) : undefined;
  const taskLabel = context.task_title ?? context.task_id;
  const showMetaRow = Boolean(recipientLabel || taskLabel || context.requires_ack || context.thread_id);

  return (
    <div className={resolvedTheme.bubble.row}>
      {!compact && (
        <div className="flex-shrink-0 pt-0.5">
          <AgentAvatar
            agentId={agentId}
            name={caps?.name}
            emoji={caps?.personality?.avatar_emoji}
            color={caps?.personality?.avatar_color}
            size="md"
            mood={msg.mood ?? undefined}
            activity={msg.intent === "review" ? "reviewing" : "writing"}
            availability={caps?.presence?.availability}
            activeTaskCount={caps?.presence?.active_task_count}
          />
        </div>
      )}

      <div className="min-w-0 flex-1">
        <div className={resolvedTheme.bubble.card}>
          <div className="flex flex-wrap items-center gap-2">
            <span className={resolvedTheme.bubble.name}>
              {caps?.name ?? agentId.replace("agent://", "")}
            </span>
            {caps?.role && (
              <span className={resolvedTheme.bubble.role}>
                {caps.role}
              </span>
            )}
            <span
              className={`${resolvedTheme.bubble.badgeBase} ${badge.className}`}
            >
              {badge.label}
            </span>
            {deliveryStatus && (
              <span
                className={`${resolvedTheme.bubble.badgeBase} ${
                  DELIVERY_BADGE[deliveryStatus] ?? DELIVERY_BADGE.queued
                }`}
              >
                {deliveryStatus.replace("_", " ")}
              </span>
            )}
            <span className={resolvedTheme.bubble.time}>
              {formatTime(event.timestamp)}
            </span>
          </div>

          {showMetaRow && (
            <div className={resolvedTheme.bubble.metaRow}>
              {recipientLabel && (
                <span className={resolvedTheme.bubble.metaChip}>
                  To {recipientLabel}
                </span>
              )}
              {taskLabel && (
                <span className={resolvedTheme.bubble.metaChip}>
                  Task {taskLabel}
                </span>
              )}
              {context.thread_id && (
                <span className={resolvedTheme.bubble.metaChip}>
                  Thread {context.thread_id}
                </span>
              )}
              {context.requires_ack && (
                <span className={resolvedTheme.bubble.ackChip}>
                  Ack required
                </span>
              )}
            </div>
          )}

          {replyMessage && (
            <div className={resolvedTheme.bubble.replyCard}>
              <span className={resolvedTheme.bubble.replyTitle}>
                Replying to {agentLabel(replyMessage.from, agents)}
              </span>
              <div className="mt-0.5">{compactText(replyMessage.content, 96)}</div>
            </div>
          )}

          {showThinking && msg.thinking && (
            <div className={resolvedTheme.bubble.thinkingCard}>
              {msg.thinking}
            </div>
          )}

          <div className={resolvedTheme.bubble.content}>
            {msg.content}
          </div>

          {msg.artifacts && msg.artifacts.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {msg.artifacts.map((artifact) => (
                <span
                  key={artifact.artifact_id}
                  className={resolvedTheme.bubble.artifactChip}
                >
                  {artifact.title ?? artifact.kind}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


