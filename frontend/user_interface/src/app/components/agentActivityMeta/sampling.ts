import type { AgentActivityEvent } from "../../types";
import { EVT_INTERACTION_SUGGESTION } from "../../constants/eventTypes";

function sampleFilmstripEvents(
  events: AgentActivityEvent[],
  activeIndex: number,
  maxItems = 72,
): Array<{ event: AgentActivityEvent; index: number }> {
  void activeIndex;
  void maxItems;
  return events
    .filter(
      (event) =>
        String(event.event_type || "").trim().toLowerCase() !== EVT_INTERACTION_SUGGESTION,
    )
    .map((event, index) => ({ event, index }));
}

export { sampleFilmstripEvents };
