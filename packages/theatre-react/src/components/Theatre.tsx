/**
 * Theatre — the main component. Drop it in and watch agents collaborate.
 *
 * Usage:
 *   <Theatre streamUrl="/acp/events" />
 *
 * That's it. Works with ACP-native and non-ACP SSE streams.
 */
import React, { useState } from "react";
import type { ACPEvent } from "@maia/acp";
import { useACPStream } from "../hooks/useACPStream";
import { useReplay } from "../hooks/useReplay";
import { TeamThread } from "./TeamThread";
import { ActivityTimeline } from "./ActivityTimeline";
import { CostBar } from "./CostBar";
import { ReplayControls } from "./ReplayControls";
import { resolveTheatreTheme } from "../theme";
import type { TheatreThemeOverride } from "../theme";

export interface TheatreProps {
  /** SSE endpoint URL for live mode. */
  streamUrl?: string | null;
  /** Pre-recorded events for replay mode. */
  recordedEvents?: ACPEvent[];
  /** Budget in USD — shows a budget bar with warning. */
  budgetUsd?: number;
  /** Show agent thinking/reasoning text. */
  showThinking?: boolean;
  /** Initial tab: "chat" or "activity". */
  defaultTab?: "chat" | "activity";
  /** Compact mode — smaller, no avatars. */
  compact?: boolean;
  /** Custom class name for the container. */
  className?: string;
  /** Callback for each event. */
  onEvent?: (event: ACPEvent) => void;
  /** Height of the Theatre (default "100%"). */
  height?: string;
  /** Override Maia default theme tokens. */
  theme?: TheatreThemeOverride;
}

type Tab = "chat" | "activity";

export function Theatre({
  streamUrl = null,
  recordedEvents,
  budgetUsd,
  showThinking = false,
  defaultTab = "chat",
  compact = false,
  className = "",
  onEvent,
  height = "100%",
  theme,
}: TheatreProps) {
  const [tab, setTab] = useState<Tab>(defaultTab);
  const resolvedTheme = resolveTheatreTheme(theme);
  const isReplayMode = !!recordedEvents && !streamUrl;

  // Live mode
  const stream = useACPStream({
    url: streamUrl,
    autoConnect: !!streamUrl,
    onEvent,
  });

  // Replay mode
  const replay = useReplay({
    events: recordedEvents ?? [],
    autoPlay: false,
  });

  // Pick the right event source
  const events = isReplayMode ? replay.visibleEvents : stream.events;
  const communicationEvents = events.filter(
    (event) =>
      event.event_type === "message" ||
      event.event_type === "handoff" ||
      event.event_type === "review",
  );
  const connected = isReplayMode ? true : stream.connected;

  return (
    <div
      className={`${resolvedTheme.theatre.shell} ${className}`}
      style={{ height }}
    >
      {/* Header */}
      <div className={resolvedTheme.theatre.header}>
        <div className="flex items-center gap-3">
          <h3 className={resolvedTheme.theatre.title}>
            Theatre
          </h3>
          <span
            className={`h-2 w-2 rounded-full ${connected ? resolvedTheme.theatre.statusConnected : resolvedTheme.theatre.statusDisconnected}`}
            title={connected ? "Connected" : "Disconnected"}
          />
          {!isReplayMode && stream.runId && (
            <span className={resolvedTheme.theatre.statusMeta}>
              Run: {stream.runId.slice(0, 8)}
            </span>
          )}
        </div>

        {/* Tabs */}
        <div className={resolvedTheme.theatre.tabsWrap}>
          <button
            onClick={() => setTab("chat")}
            className={`${resolvedTheme.theatre.tabBase} ${
              tab === "chat"
                ? resolvedTheme.theatre.tabActive
                : resolvedTheme.theatre.tabInactive
            }`}
          >
            Team Chat
            {communicationEvents.length > 0 && (
              <span className={resolvedTheme.theatre.statusMeta}>
                ({communicationEvents.length})
              </span>
            )}
          </button>
          <button
            onClick={() => setTab("activity")}
            className={`${resolvedTheme.theatre.tabBase} ${
              tab === "activity"
                ? resolvedTheme.theatre.tabActive
                : resolvedTheme.theatre.tabInactive
            }`}
          >
            Activity
          </button>
        </div>
      </div>

      {/* Content */}
      <div className={resolvedTheme.theatre.content}>
        {tab === "chat" ? (
          <TeamThread
            messages={communicationEvents}
            agents={stream.agents}
            showThinking={showThinking}
            compact={compact}
            theme={resolvedTheme}
            className="h-full"
          />
        ) : (
          <ActivityTimeline events={events} theme={resolvedTheme} className="h-full" />
        )}
      </div>

      {/* Cost bar */}
      <CostBar events={events} budgetUsd={budgetUsd} />

      {/* Replay controls (only in replay mode) */}
      {isReplayMode && <ReplayControls replay={replay} />}
    </div>
  );
}
