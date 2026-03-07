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

function replayImportance(event: AgentActivityEvent): string {
  const payload = (event.data || event.metadata || {}) as Record<string, unknown>;
  return String(
    event.replay_importance ||
      event.event_replay_importance ||
      payload.replay_importance ||
      payload.event_replay_importance ||
      "",
  )
    .trim()
    .toLowerCase();
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
  const { visibleEvents, safeCursor, replayMode } = options;
  const rows = visibleEvents.map((event, index) => ({ event, index }));
  if (replayMode !== "fast") {
    return rows;
  }
  if (rows.length <= 18) {
    return rows;
  }
  const stride = Math.max(2, Math.floor(rows.length / 18));
  const filtered: TimelineRow[] = [];
  for (const row of rows) {
    const status = String(row.event.status || "").trim().toLowerCase();
    const importance = replayImportance(row.event);
    const keepBySignal =
      importance === "critical" ||
      importance === "high" ||
      status === "failed" ||
      status === "blocked" ||
      status === "waiting";
    const keepByPosition =
      row.index === 0 ||
      row.index === safeCursor ||
      row.index === rows.length - 1 ||
      row.index % stride === 0;
    if (keepBySignal || keepByPosition) {
      filtered.push(row);
    }
  }
  const deduped: TimelineRow[] = [];
  const seen = new Set<number>();
  for (const row of filtered) {
    if (seen.has(row.index)) {
      continue;
    }
    seen.add(row.index);
    deduped.push(row);
  }
  return deduped.sort((left, right) => left.index - right.index);
}

function filmstripRowsForMode(options: {
  filmstripRows: Array<{ event: AgentActivityEvent; index: number }>;
  safeCursor: number;
  replayMode: ReplayMode;
}): Array<{ event: AgentActivityEvent; index: number }> {
  const { filmstripRows, safeCursor, replayMode } = options;
  if (replayMode === "full_theatre") {
    return filmstripRows;
  }
  if (replayMode === "balanced") {
    return filmstripRows;
  }
  const max = 12;
  if (filmstripRows.length <= max) {
    return filmstripRows;
  }
  const step = Math.max(1, Math.floor(filmstripRows.length / max));
  const sampled: Array<{ event: AgentActivityEvent; index: number }> = [];
  for (let index = 0; index < filmstripRows.length; index += step) {
    sampled.push(filmstripRows[index]);
  }
  const active = filmstripRows.find((row) => row.index === safeCursor);
  if (active && !sampled.some((row) => row.index === active.index)) {
    sampled.push(active);
  }
  sampled.sort((left, right) => left.index - right.index);
  return sampled.slice(-max);
}

export {
  filmstripRowsForMode,
  normalizeReplayMode,
  readReplayMode,
  timelineRowsForMode,
};
export type { ReplayMode, TimelineRow };
