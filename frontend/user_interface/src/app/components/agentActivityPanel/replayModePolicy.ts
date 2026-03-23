import type { AgentActivityEvent } from "../../types";

type ReplayMode = "fast" | "balanced" | "full_theatre";
type TimelineRow = { event: AgentActivityEvent; index: number };

const WORKSPACE_RENDER_MODE_STORAGE_KEY = "maia.info-panel.workspace-render-mode.v1";
const HIDDEN_TIMELINE_EVENT_TYPES = new Set<string>([
  "team_chat_message",
  "planning_started",
  "task_understanding_started",
  "task_understanding_ready",
  "plan_ready",
  "plan_candidate",
  "plan_refined",
  "preflight_started",
  "preflight_check",
  "preflight_completed",
  "execution_checkpoint",
  "llm.context_summary",
  "llm.context_session",
  "llm.context_memory",
  "llm.intent_tags",
  "llm.research_depth_profile",
  "llm.task_rewrite_started",
  "llm.task_rewrite_completed",
  "llm.plan_decompose_started",
  "llm.plan_decompose_completed",
  "llm.plan_step",
  "llm.step_summary",
  "llm.location_brief",
  "llm.capability_plan",
  "llm.web_routing_decision",
]);
const HIDDEN_TIMELINE_PREFIXES = ["agent_dialogue_", "brain_", "plan_", "planning_"];

function normalizeReplayMode(raw: unknown): ReplayMode {
  const value = String(raw || "").trim().toLowerCase();
  if (value === "fast") {
    return "fast";
  }
  if (value === "full" || value === "full_theatre") {
    return "full_theatre";
  }
  return "balanced";
}

function readReplayModeFromEvents(events: AgentActivityEvent[]): ReplayMode | null {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    const payload = (event.data || event.metadata || {}) as Record<string, unknown>;
    const candidate = payload.__workspace_render_mode ?? payload.workspace_render_mode;
    if (String(candidate || "").trim()) {
      return normalizeReplayMode(candidate);
    }
  }
  return null;
}

function readReplayMode(events: AgentActivityEvent[]): ReplayMode {
  const fromEvents = readReplayModeFromEvents(events);
  if (fromEvents) {
    return fromEvents;
  }
  if (typeof window === "undefined") {
    return "balanced";
  }
  return normalizeReplayMode(window.localStorage.getItem(WORKSPACE_RENDER_MODE_STORAGE_KEY) || "");
}

function timelineDetailKey(event: AgentActivityEvent): string {
  return String(
    event.title ||
      ((event.data || event.metadata || {}) as Record<string, unknown>).title ||
      "",
  )
    .trim()
    .toLowerCase();
}

function isUserFacingTimelineEvent(event: AgentActivityEvent): boolean {
  const eventType = String(event.event_type || event.type || "").trim().toLowerCase();
  if (!eventType) {
    return true;
  }
  if (HIDDEN_TIMELINE_EVENT_TYPES.has(eventType)) {
    return false;
  }
  if (HIDDEN_TIMELINE_PREFIXES.some((prefix) => eventType.startsWith(prefix))) {
    return false;
  }
  const titleKey = timelineDetailKey(event);
  if (
    titleKey.includes("loaded relevant session context") ||
    titleKey.includes("loaded relevant memory context") ||
    titleKey.includes("checkpoint: task_prepared")
  ) {
    return false;
  }
  return true;
}

function visibleTimelineEvents(events: AgentActivityEvent[]): AgentActivityEvent[] {
  return events.filter(isUserFacingTimelineEvent);
}

function timelineRowsForMode(options: {
  visibleEvents: AgentActivityEvent[];
  safeCursor: number;
  replayMode: ReplayMode;
}): TimelineRow[] {
  const visibleEvents = visibleTimelineEvents(options.visibleEvents);
  void options.safeCursor;
  void options.replayMode;
  return visibleEvents.map((event, index) => ({ event, index }));
}

function filmstripRowsForMode(options: {
  filmstripRows: Array<{ event: AgentActivityEvent; index: number }>;
  safeCursor: number;
  replayMode: ReplayMode;
}): Array<{ event: AgentActivityEvent; index: number }> {
  const { filmstripRows } = options;
  void options.safeCursor;
  void options.replayMode;
  return filmstripRows;
}

export {
  filmstripRowsForMode,
  isUserFacingTimelineEvent,
  normalizeReplayMode,
  readReplayMode,
  timelineRowsForMode,
  visibleTimelineEvents,
};
export type { ReplayMode, TimelineRow };
