import type { AgentActivityEvent } from "../../types";
import { EVT_APPROVAL_GRANTED, EVT_APPROVAL_REQUIRED } from "../../constants/eventTypes";

function latestOpenApprovalEvent(events: AgentActivityEvent[]): AgentActivityEvent | null {
  let latestRequiredIndex = -1;
  let latestGrantedIndex = -1;

  for (let index = 0; index < events.length; index += 1) {
    const type = String(events[index]?.event_type || "").trim().toLowerCase();
    if (type === EVT_APPROVAL_REQUIRED) {
      latestRequiredIndex = index;
    } else if (type === EVT_APPROVAL_GRANTED) {
      latestGrantedIndex = index;
    }
  }

  if (latestRequiredIndex < 0 || latestGrantedIndex > latestRequiredIndex) {
    return null;
  }
  return events[latestRequiredIndex] || null;
}

export { latestOpenApprovalEvent };
