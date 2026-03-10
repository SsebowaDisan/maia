import type { AgentActivityEvent } from "../../types";

type ReplayMode = "fast" | "balanced" | "full_theatre";
type TimelineRow = { event: AgentActivityEvent; index: number };

const WORKSPACE_RENDER_MODE_STORAGE_KEY = "maia.info-panel.workspace-render-mode.v1";

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

function timelineRowsForMode(options: {
  visibleEvents: AgentActivityEvent[];
  safeCursor: number;
  replayMode: ReplayMode;
}): TimelineRow[] {
  const { visibleEvents } = options;
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
  normalizeReplayMode,
  readReplayMode,
  timelineRowsForMode,
};
export type { ReplayMode, TimelineRow };
