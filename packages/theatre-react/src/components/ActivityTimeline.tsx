/**
 * ActivityTimeline — vertical timeline of all agent activities.
 * Shows tool calls, browser actions, searches, file reads, etc.
 */
import React from "react";
import type { ACPActivity, ACPEvent } from "@maia/acp";

import { resolveTheatreTheme } from "../theme";
import type { TheatreTheme, TheatreThemeOverride } from "../theme";

export interface ActivityTimelineProps {
  events: ACPEvent[];
  className?: string;
  theme?: TheatreThemeOverride;
}

const ACTIVITY_ICONS: Record<string, string> = {
  thinking: "\u{1F914}",
  searching: "\u{1F50D}",
  reading: "\u{1F4D6}",
  writing: "\u{270F}",
  browsing: "\u{1F310}",
  coding: "\u{1F4BB}",
  analyzing: "\u{1F4CA}",
  tool_calling: "\u{1F527}",
  waiting: "\u{23F3}",
  reviewing: "\u{1F50E}",
  idle: "\u{1F4A4}",
  error: "\u{26A0}",
};

const ACTIVITY_COLORS: Record<string, string> = {
  thinking: "border-yellow-300 bg-yellow-50",
  searching: "border-blue-300 bg-blue-50",
  reading: "border-indigo-300 bg-indigo-50",
  writing: "border-green-300 bg-green-50",
  browsing: "border-cyan-300 bg-cyan-50",
  coding: "border-violet-300 bg-violet-50",
  analyzing: "border-orange-300 bg-orange-50",
  tool_calling: "border-gray-300 bg-gray-50",
  waiting: "border-gray-200 bg-gray-50",
  reviewing: "border-purple-300 bg-purple-50",
  error: "border-red-300 bg-red-50",
};

function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return "";
  }
}

function ActivityItem({ event, theme }: { event: ACPEvent; theme: TheatreTheme }) {
  const act = event.payload as ACPActivity;
  const icon = ACTIVITY_ICONS[act.activity] ?? "\u{2022}";
  const color = ACTIVITY_COLORS[act.activity] ?? "border-gray-300 bg-gray-50";
  const agentName = (act.agent_id ?? event.agent_id).replace("agent://", "");

  return (
    <div className={theme.activity.item}>
      <div className="flex flex-col items-center">
        <div className={`flex h-6 w-6 items-center justify-center rounded-full border text-[12px] ${color}`}>
          {icon}
        </div>
        <div className="w-px flex-1 bg-[#e4e7ec]" />
      </div>

      <div className="min-w-0 flex-1 pb-2">
        <div className="flex items-center gap-2">
          <span className={theme.activity.actor}>{agentName}</span>
          <span className={theme.activity.action}>{act.activity.replace("_", " ")}</span>
          <span className={theme.activity.time}>{formatTime(event.timestamp)}</span>
        </div>

        {act.detail && <p className={theme.activity.detail}>{act.detail}</p>}

        {act.tool && (
          <div className={theme.activity.toolChip}>
            {act.tool.tool_name ?? act.tool.tool_id}
            {act.tool.status && (
              <span className={`ml-2 ${act.tool.status === "failed" ? "text-red-500" : "text-green-500"}`}>
                ({act.tool.status})
              </span>
            )}
          </div>
        )}

        {act.browser && (
          <div className={theme.activity.browserChip}>
            <span>{act.browser.action ?? "navigate"}</span>
            <span className="truncate">{act.browser.url}</span>
          </div>
        )}

        {act.progress && act.progress.total > 0 && (
          <div className="mt-1 h-1.5 w-32 overflow-hidden rounded-full bg-[#eaecf0]">
            <div
              className="h-full rounded-full bg-[#175cd3] transition-all"
              style={{
                width: `${act.progress.percentage ?? (act.progress.current / act.progress.total) * 100}%`,
              }}
            />
          </div>
        )}

        {act.cost && act.cost.cost_usd > 0 && (
          <span className={theme.activity.cost}>
            ${act.cost.cost_usd.toFixed(4)} ({act.cost.tokens_used} tokens)
          </span>
        )}
      </div>
    </div>
  );
}

export function ActivityTimeline({ events, className = "", theme }: ActivityTimelineProps) {
  const resolvedTheme = resolveTheatreTheme(theme);
  const activityEvents = events.filter((event) => event.event_type === "event");

  return (
    <div className={`${resolvedTheme.activity.root} ${className}`}>
      {activityEvents.length === 0 && (
        <div className={resolvedTheme.activity.emptyState}>No activity yet</div>
      )}
      {activityEvents.map((event, index) => (
        <ActivityItem key={`${event.timestamp}_${index}`} event={event} theme={resolvedTheme} />
      ))}
    </div>
  );
}
