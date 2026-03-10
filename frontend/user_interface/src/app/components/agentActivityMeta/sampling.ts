import type { AgentActivityEvent } from "../../types";

function sampleFilmstripEvents(
  events: AgentActivityEvent[],
  activeIndex: number,
  maxItems = 72,
): Array<{ event: AgentActivityEvent; index: number }> {
  void activeIndex;
  void maxItems;
  return events.map((event, index) => ({ event, index }));
}

export { sampleFilmstripEvents };
