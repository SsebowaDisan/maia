/**
 * TeamChat — the main conversation panel. Shows agents talking to each other.
 *
 * Usage:
 *   <TeamChat streamUrl="/acp/events" />
 */
import React, { useEffect, useRef, useState } from "react";
import type { ACPEvent, ACPCapabilities } from "@maia/acp";
import { AgentBubble } from "./AgentBubble";
import { ReviewBadge } from "./ReviewBadge";
import { TypingIndicator } from "./TypingIndicator";
import { useConversationStream } from "../hooks/useConversationStream";

export interface TeamChatProps {
  /** SSE endpoint for live mode. */
  streamUrl?: string | null;
  /** Pre-recorded events for replay. */
  recordedEvents?: ACPEvent[];
  /** Show agent thinking/reasoning. */
  showThinking?: boolean;
  /** Custom class name. */
  className?: string;
  /** Height (default "100%"). */
  height?: string;
  /** Event callback. */
  onEvent?: (event: ACPEvent) => void;
}

export function TeamChat({
  streamUrl = null,
  recordedEvents,
  showThinking = false,
  className = "",
  height = "100%",
  onEvent,
}: TeamChatProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const { messages, reviews, agents, typingAgent, connected } = useConversationStream({
    url: streamUrl,
    recordedEvents,
    onEvent,
  });

  // Auto-scroll on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, reviews.length]);

  // Merge messages + reviews by timestamp for correct ordering
  const allEvents = [...messages, ...reviews].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
  );

  return (
    <div
      className={`flex flex-col overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950 ${className}`}
      style={{ height }}
    >
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-gray-100 px-4 py-2.5 dark:border-gray-800">
        <h3 className="text-[13px] font-semibold text-gray-800 dark:text-gray-200">
          Team Chat
        </h3>
        <span
          className={`h-2 w-2 rounded-full ${connected ? "bg-green-400" : "bg-gray-300"}`}
        />
        {messages.length > 0 && (
          <span className="text-[11px] text-gray-400">
            {messages.length} messages
          </span>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-2">
        {allEvents.length === 0 && (
          <div className="flex h-full items-center justify-center text-[13px] text-gray-400">
            Waiting for agents to start talking...
          </div>
        )}

        {allEvents.map((event, i) => {
          if (event.event_type === "review") {
            return <ReviewBadge key={`${event.timestamp}_${i}`} event={event} />;
          }
          // Detect replies — if this message is responding to a different agent
          const prev = i > 0 ? allEvents[i - 1] : null;
          const isReply = prev?.event_type === "message" && event.agent_id !== prev.agent_id;

          return (
            <AgentBubble
              key={`${event.timestamp}_${i}`}
              event={event}
              agents={agents}
              showThinking={showThinking}
              isReply={isReply}
            />
          );
        })}

        {typingAgent && <TypingIndicator agentId={typingAgent} agents={agents} />}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}