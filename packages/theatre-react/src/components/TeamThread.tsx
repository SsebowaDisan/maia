/**
 * TeamThread - communication-first Theatre panel with thread grouping,
 * presence, handoffs, and review loops.
 */
import React, { useEffect, useMemo, useRef } from "react";
import type {
  ACPCapabilities,
  ACPEvent,
  ACPHandoff,
  ACPMessage,
  ACPReview,
} from "@maia/acp";
import { AgentAvatar } from "./AgentAvatar";
import { MessageBubble } from "./MessageBubble";
import { resolveTheatreTheme } from "../theme";
import type { TheatreTheme, TheatreThemeOverride } from "../theme";

export interface TeamThreadProps {
  /** Communication events to render. */
  messages: ACPEvent[];
  /** Known agent capabilities for avatar/personality info. */
  agents?: Map<string, ACPCapabilities>;
  /** Currently typing agent IDs (for typing indicators). */
  typingAgents?: string[];
  /** Show thinking text (agent reasoning). */
  showThinking?: boolean;
  /** Compact mode - smaller bubbles, no avatars. */
  compact?: boolean;
  /** Custom class name. */
  className?: string;
  /** Override Maia default theme tokens. */
  theme?: TheatreThemeOverride;
}

interface ThreadSection {
  id: string;
  title: string;
  subtitle?: string;
  events: ACPEvent[];
}

function TypingIndicator({
  agentId,
  agents,
  theme,
}: {
  agentId: string;
  agents?: Map<string, ACPCapabilities>;
  theme: TheatreTheme;
}) {
  const caps = agents?.get(agentId);
  const name = caps?.name ?? agentId.replace("agent://", "");

  return (
    <div className={theme.thread.typing}>
      <AgentAvatar
        agentId={agentId}
        name={caps?.name}
        emoji={caps?.personality?.avatar_emoji}
        color={caps?.personality?.avatar_color}
        size="sm"
        activity="thinking"
        availability={caps?.presence?.availability}
        activeTaskCount={caps?.presence?.active_task_count}
      />
      <span className="italic">
        {name} is drafting a response
        <span className="inline-flex w-8">
          <span className="animate-pulse">...</span>
        </span>
      </span>
    </div>
  );
}

function agentName(agentId: string, agents?: Map<string, ACPCapabilities>): string {
  return agents?.get(agentId)?.name ?? agentId.replace("agent://", "");
}

function presenceSummary(agents?: Map<string, ACPCapabilities>): ACPCapabilities[] {
  if (!agents) {
    return [];
  }
  return Array.from(agents.values())
    .sort((left, right) => {
      const leftLoad = left.presence?.active_task_count ?? 0;
      const rightLoad = right.presence?.active_task_count ?? 0;
      return leftLoad - rightLoad;
    })
    .slice(0, 6);
}

function getThreadId(event: ACPEvent): string {
  if (event.event_type === "message") {
    const message = event.payload as ACPMessage;
    return message.context?.thread_id ?? message.context?.task_id ?? "general";
  }
  if (event.event_type === "handoff") {
    const handoff = event.payload as ACPHandoff;
    return handoff.task.thread_id ?? handoff.task.task_id ?? "handoffs";
  }
  if (event.event_type === "review") {
    const review = event.payload as ACPReview;
    return review.artifact_id ?? `review-${review.author}`;
  }
  return "general";
}

function getThreadLabel(event: ACPEvent): { title: string; subtitle?: string } {
  if (event.event_type === "message") {
    const message = event.payload as ACPMessage;
    return {
      title: message.context?.task_title ?? message.context?.task_id ?? "General coordination",
      subtitle: message.context?.thread_id ? `Thread ${message.context.thread_id}` : undefined,
    };
  }
  if (event.event_type === "handoff") {
    const handoff = event.payload as ACPHandoff;
    return {
      title: handoff.task.description,
      subtitle: handoff.task.status ? `Status ${handoff.task.status.replace("_", " ")}` : undefined,
    };
  }
  if (event.event_type === "review") {
    const review = event.payload as ACPReview;
    return {
      title: `Review round ${review.round ?? 1}`,
      subtitle: review.artifact_id ? `Artifact ${review.artifact_id}` : undefined,
    };
  }
  return { title: "General coordination" };
}

function HandoffCard({
  event,
  agents,
}: {
  event: ACPEvent<ACPHandoff>;
  agents?: Map<string, ACPCapabilities>;
}) {
  const handoff = event.payload;
  const fromLabel = agentName(handoff.from, agents);
  const toLabel = agentName(handoff.to, agents);
  const status = handoff.status ?? handoff.task.status ?? "proposed";

  return (
    <div className="rounded-2xl border border-emerald-200 bg-emerald-500/5 px-4 py-3 dark:border-emerald-900/70">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[13px] font-semibold text-slate-900 dark:text-slate-100">
          {fromLabel} handed work to {toLabel}
        </span>
        <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-700 dark:text-emerald-300">
          {status.replace("_", " ")}
        </span>
        {handoff.requires_ack && (
          <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:text-amber-300">
            Ack required
          </span>
        )}
      </div>
      <div className="mt-2 text-[13px] text-slate-700 dark:text-slate-300">
        {handoff.task.description}
      </div>
      <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-500 dark:text-slate-400">
        {handoff.task.priority && (
          <span className="rounded-full bg-slate-100 px-2 py-0.5 dark:bg-slate-800">
            Priority {handoff.task.priority}
          </span>
        )}
        {handoff.task.definition_of_done && (
          <span className="rounded-full bg-slate-100 px-2 py-0.5 dark:bg-slate-800">
            Done when {handoff.task.definition_of_done}
          </span>
        )}
        {handoff.task.blockers && handoff.task.blockers.length > 0 && (
          <span className="rounded-full bg-rose-500/10 px-2 py-0.5 text-rose-700 dark:text-rose-300">
            Blockers {handoff.task.blockers.join(", ")}
          </span>
        )}
      </div>
    </div>
  );
}

function ReviewCard({
  event,
  agents,
}: {
  event: ACPEvent<ACPReview>;
  agents?: Map<string, ACPCapabilities>;
}) {
  const review = event.payload;
  const reviewer = agentName(review.reviewer, agents);
  const author = agentName(review.author, agents);

  return (
    <div className="rounded-2xl border border-violet-200 bg-violet-500/5 px-4 py-3 dark:border-violet-900/70">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[13px] font-semibold text-slate-900 dark:text-slate-100">
          {reviewer} reviewed {author}
        </span>
        <span className="rounded-full bg-violet-500/10 px-2 py-0.5 text-[10px] font-medium text-violet-700 dark:text-violet-300">
          {review.verdict}
        </span>
        {typeof review.score === "number" && (
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            Score {review.score}
          </span>
        )}
      </div>
      {review.feedback && (
        <div className="mt-2 text-[13px] text-slate-700 dark:text-slate-300">
          {review.feedback}
        </div>
      )}
      {review.revision_instructions && (
        <div className="mt-2 rounded-xl bg-white/70 px-3 py-2 text-[12px] text-slate-600 dark:bg-slate-950/60 dark:text-slate-300">
          Next pass: {review.revision_instructions}
        </div>
      )}
    </div>
  );
}

export function TeamThread({
  messages,
  agents,
  typingAgents = [],
  showThinking = false,
  compact = false,
  className = "",
  theme,
}: TeamThreadProps) {
  const resolvedTheme = resolveTheatreTheme(theme);
  const bottomRef = useRef<HTMLDivElement>(null);

  const communicationEvents = useMemo(
    () =>
      messages.filter(
        (event) =>
          event.event_type === "message" ||
          event.event_type === "handoff" ||
          event.event_type === "review",
      ),
    [messages],
  );

  const replyLookup = useMemo(() => {
    const lookup = new Map<string, ACPMessage>();
    for (const event of communicationEvents) {
      if (event.event_type !== "message") {
        continue;
      }
      const message = event.payload as ACPMessage;
      const messageId = message.context?.message_id;
      if (messageId) {
        lookup.set(messageId, message);
      }
    }
    return lookup;
  }, [communicationEvents]);

  const threads = useMemo<ThreadSection[]>(() => {
    const grouped = new Map<string, ThreadSection>();
    for (const event of communicationEvents) {
      const id = getThreadId(event);
      const label = getThreadLabel(event);
      const existing = grouped.get(id);
      if (existing) {
        existing.events.push(event);
        if (existing.title === "General coordination" && label.title !== "General coordination") {
          existing.title = label.title;
        }
        existing.subtitle ??= label.subtitle;
        continue;
      }
      grouped.set(id, {
        id,
        title: label.title,
        subtitle: label.subtitle,
        events: [event],
      });
    }
    return Array.from(grouped.values());
  }, [communicationEvents]);

  const roster = useMemo(() => presenceSummary(agents), [agents]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [communicationEvents.length]);

  return (
    <div className={`${resolvedTheme.thread.root} ${className}`}>
      {roster.length > 0 && (
        <div className={resolvedTheme.thread.rosterWrap}>
          <div className={resolvedTheme.thread.rosterTitle}>
            Team status
          </div>
          <div className="flex flex-wrap gap-2">
            {roster.map((agent) => (
              <div
                key={agent.agent_id}
                className={resolvedTheme.thread.rosterChip}
              >
                <AgentAvatar
                  agentId={agent.agent_id}
                  name={agent.name}
                  emoji={agent.personality?.avatar_emoji}
                  color={agent.personality?.avatar_color}
                  size="sm"
                  availability={agent.presence?.availability}
                  activeTaskCount={agent.presence?.active_task_count}
                />
                <div className="min-w-0">
                  <div className={resolvedTheme.thread.rosterName}>
                    {agent.name}
                  </div>
                  <div className={resolvedTheme.thread.rosterMeta}>
                    {agent.presence?.current_focus ??
                      agent.presence?.status_text ??
                      agent.role ??
                      "Standing by"}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {communicationEvents.length === 0 && (
        <div className={resolvedTheme.thread.emptyState}>
          Waiting for agents to start coordinating work...
        </div>
      )}

      <div className={resolvedTheme.thread.sections}>
        {threads.map((thread) => (
          <section key={thread.id} className={resolvedTheme.thread.section}>
            <div className={resolvedTheme.thread.sectionHeader}>
              <h4 className={resolvedTheme.thread.sectionTitle}>
                {thread.title}
              </h4>
              {thread.subtitle && (
                <span className={resolvedTheme.thread.sectionSubtitle}>{thread.subtitle}</span>
              )}
            </div>

            <div className={resolvedTheme.thread.threadCard}>
              {thread.events.map((event, index) => {
                if (event.event_type === "message") {
                  return (
                    <MessageBubble
                      key={`${thread.id}_${event.timestamp}_${index}`}
                      event={event as ACPEvent<ACPMessage>}
                      agents={agents}
                      showThinking={showThinking}
                      compact={compact}
                      theme={resolvedTheme}
                      replyLookup={replyLookup}
                    />
                  );
                }
                if (event.event_type === "handoff") {
                  return (
                    <HandoffCard
                      key={`${thread.id}_${event.timestamp}_${index}`}
                      event={event as ACPEvent<ACPHandoff>}
                      agents={agents}
                    />
                  );
                }
                return (
                  <ReviewCard
                    key={`${thread.id}_${event.timestamp}_${index}`}
                    event={event as ACPEvent<ACPReview>}
                    agents={agents}
                  />
                );
              })}
            </div>
          </section>
        ))}

        {typingAgents.map((id) => (
          <TypingIndicator key={id} agentId={id} agents={agents} theme={resolvedTheme} />
        ))}
      </div>

      <div ref={bottomRef} />
    </div>
  );
}
