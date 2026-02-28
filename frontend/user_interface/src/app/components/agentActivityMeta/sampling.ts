import type { AgentActivityEvent } from "../../types";

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
