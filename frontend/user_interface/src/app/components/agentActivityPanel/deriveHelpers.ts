import type { AgentActivityEvent } from "../../types";

const EMAIL_SCENE_EVENT_TYPES = new Set([
  "email_open_compose",
  "email_draft_create",
  "email_set_to",
  "email_set_subject",
  "email_set_body",
  "email_type_body",
  "email_ready_to_send",
  "email_click_send",
  "email_sent",
]);

function readEventIndex(event: AgentActivityEvent, fallback: number): number {
  const direct = Number(event.event_index);
  if (Number.isFinite(direct) && direct > 0) {
    return direct;
  }
  const data = event.data || event.metadata || {};
  const payloadIndex = Number((data as Record<string, unknown>).event_index);
  if (Number.isFinite(payloadIndex) && payloadIndex > 0) {
    return payloadIndex;
  }
  const seq = Number(event.seq);
  if (Number.isFinite(seq) && seq > 0) {
    return seq;
  }
  return fallback;
}

export { EMAIL_SCENE_EVENT_TYPES, readEventIndex };
