import type { AgentActivityEvent } from "../../types";

function replayImportanceRank(event: AgentActivityEvent): number {
  const payload = (event.data || event.metadata || {}) as Record<string, unknown>;
  const importance = String(
    event.replay_importance ||
      event.event_replay_importance ||
      payload.replay_importance ||
      payload.event_replay_importance ||
      "",
  )
    .trim()
    .toLowerCase();
  if (importance === "critical") {
    return 4;
  }
  if (importance === "high") {
    return 3;
  }
  if (importance === "normal") {
    return 2;
  }
  if (importance === "low") {
    return 1;
  }
  return 0;
}

function sampleFilmstripEvents(
  events: AgentActivityEvent[],
  activeIndex: number,
  maxItems = 72,
): Array<{ event: AgentActivityEvent; index: number }> {
  if (events.length <= maxItems) {
    return events.map((event, index) => ({ event, index }));
  }
  const step = Math.max(1, Math.floor(events.length / maxItems));
  const sampled: Array<{ event: AgentActivityEvent; index: number }> = [];
  for (let index = 0; index < events.length; index += step) {
    sampled.push({ event: events[index], index });
  }
  for (let index = 0; index < events.length; index += 1) {
    const event = events[index];
    if (replayImportanceRank(event) < 3) {
      continue;
    }
    if (sampled.some((item) => item.index === index)) {
      continue;
    }
    sampled.push({ event, index });
  }
  const lastIndex = events.length - 1;
  if (!sampled.some((item) => item.index === lastIndex)) {
    sampled.push({ event: events[lastIndex], index: lastIndex });
  }
  if (!sampled.some((item) => item.index === activeIndex)) {
    sampled.push({ event: events[activeIndex], index: activeIndex });
  }
  sampled.sort((left, right) => left.index - right.index);
  return sampled;
}

export { sampleFilmstripEvents };
