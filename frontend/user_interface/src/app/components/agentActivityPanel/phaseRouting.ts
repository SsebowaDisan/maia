import type { AgentActivityEvent } from "../../types";
import {
  EVENT_PREFIX_PREFLIGHT,
  EVT_AGENT_HANDOFF,
  EVT_AGENT_RESUME,
  EVT_AGENT_WAITING,
  EVT_APPROVAL_GRANTED,
  EVT_APPROVAL_REQUIRED,
  EVT_EVENT_COVERAGE,
  EVT_HANDOFF_PAUSED,
  EVT_HANDOFF_RESUMED,
  EVT_INTERACTION_SUGGESTION,
  EVT_POLICY_BLOCKED,
  EVT_VERIFICATION_CHECK,
  EVT_VERIFICATION_COMPLETED,
  EVT_VERIFICATION_STARTED,
} from "../../constants/eventTypes";

const PHASE_ORDER = [
  "understanding",
  "contract",
  "clarification",
  "planning",
  "execution",
  "verification",
  "delivery",
] as const;

type ActivityPhaseKey = (typeof PHASE_ORDER)[number];
type ActivityPhaseState = "pending" | "active" | "completed";

type ActivityPhaseRow = {
  key: ActivityPhaseKey;
  label: string;
  state: ActivityPhaseState;
  latestEventId: string;
  latestEventTitle: string;
};

const PHASE_LABELS: Record<ActivityPhaseKey, string> = {
  understanding: "Understanding",
  contract: "Contract",
  clarification: "Clarification",
  planning: "Planning",
  execution: "Execution",
  verification: "Verification",
  delivery: "Delivery",
};

function phaseForEvent(event: AgentActivityEvent | null): ActivityPhaseKey | null {
  if (!event) {
    return null;
  }
  const type = String(event.event_type || "").toLowerCase();
  const title = String(event.title || "").toLowerCase();

  if (type === EVT_INTERACTION_SUGGESTION) {
    return null;
  }

  if (type.startsWith(EVENT_PREFIX_PREFLIGHT)) {
    return "understanding";
  }

  if (
    type === "task_understanding_started" ||
    type === "task_understanding_ready" ||
    type === "llm.context_summary" ||
    type === "llm.intent_tags" ||
    type === "llm.task_rewrite_started" ||
    type === "llm.task_rewrite_completed"
  ) {
    return "understanding";
  }
  if (type === "llm.task_contract_started" || type === "llm.task_contract_completed") {
    return "contract";
  }
  if (type === "llm.clarification_requested" || type === "llm.clarification_resolved") {
    return "clarification";
  }
  if (type === EVT_POLICY_BLOCKED && title.includes("clarification")) {
    return "clarification";
  }
  if (
    type === "planning_started" ||
    type.startsWith("plan_") ||
    type === "llm.plan_decompose_started" ||
    type === "llm.plan_decompose_completed" ||
    type === "llm.web_routing_decision" ||
    type === "llm.plan_step" ||
    type === "llm.plan_fact_coverage"
  ) {
    return "planning";
  }
  if (
    type.startsWith("tool_") ||
    type.startsWith("web_") ||
    type.startsWith("browser_") ||
    type.startsWith("document_") ||
    type.startsWith("pdf_") ||
    type.startsWith("doc_") ||
    type.startsWith("docs.") ||
    type.startsWith("sheet_") ||
    type.startsWith("sheets.") ||
    type.startsWith("drive.") ||
    type === "action_prepared"
  ) {
    return "execution";
  }
  if (
    type === EVT_VERIFICATION_STARTED ||
    type === EVT_VERIFICATION_CHECK ||
    type === EVT_VERIFICATION_COMPLETED ||
    type === EVT_APPROVAL_REQUIRED ||
    type === EVT_APPROVAL_GRANTED ||
    type === EVT_HANDOFF_PAUSED ||
    type === EVT_HANDOFF_RESUMED ||
    type === EVT_AGENT_WAITING ||
    type === EVT_AGENT_HANDOFF ||
    type === EVT_AGENT_RESUME ||
    type === EVT_EVENT_COVERAGE ||
    type === EVT_POLICY_BLOCKED
  ) {
    return "verification";
  }
  if (
    type === "llm.delivery_check_started" ||
    type === "llm.delivery_check_completed" ||
    type === "llm.delivery_check_failed" ||
    type === "email_sent" ||
    type === "browser_contact_submit" ||
    type === "browser_contact_confirmation"
  ) {
    return "delivery";
  }
  return null;
}

function derivePhaseTimeline(
  visibleEvents: AgentActivityEvent[],
  activeEvent: AgentActivityEvent | null,
): ActivityPhaseRow[] {
  const activePhaseRaw = phaseForEvent(activeEvent);
  const hasClarificationSignals =
    activePhaseRaw === "clarification" ||
    visibleEvents.some((event) => phaseForEvent(event) === "clarification");
  const phaseOrder = hasClarificationSignals
    ? PHASE_ORDER
    : PHASE_ORDER.filter((phase): phase is ActivityPhaseKey => phase !== "clarification");

  const latestByPhase: Record<ActivityPhaseKey, AgentActivityEvent | null> = {
    understanding: null,
    contract: null,
    clarification: null,
    planning: null,
    execution: null,
    verification: null,
    delivery: null,
  };

  for (const event of visibleEvents) {
    const phase = phaseForEvent(event);
    if (!phase) {
      continue;
    }
    latestByPhase[phase] = event;
  }

  let furthestSeenPhaseIndex = -1;
  for (let index = 0; index < phaseOrder.length; index += 1) {
    const phase = phaseOrder[index];
    if (latestByPhase[phase]) {
      furthestSeenPhaseIndex = index;
    }
  }
  const activePhaseIndex = Math.max(
    activePhaseRaw ? phaseOrder.indexOf(activePhaseRaw) : -1,
    furthestSeenPhaseIndex,
  );
  const activePhase =
    activePhaseIndex >= 0 && activePhaseIndex < phaseOrder.length
      ? phaseOrder[activePhaseIndex]
      : null;

  return phaseOrder.map((phase) => {
    const latest = latestByPhase[phase];
    let state: ActivityPhaseState = "pending";
    if (latest) {
      state = "completed";
    }
    if (activePhase === phase) {
      state = "active";
    }
    return {
      key: phase,
      label: PHASE_LABELS[phase],
      state,
      latestEventId: String(latest?.event_id || ""),
      latestEventTitle: String(latest?.title || ""),
    };
  });
}

export { derivePhaseTimeline, phaseForEvent };
export type { ActivityPhaseKey, ActivityPhaseRow, ActivityPhaseState };
