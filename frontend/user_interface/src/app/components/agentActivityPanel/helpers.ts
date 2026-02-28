import type { AgentActivityEvent } from "../../types";

const URL_PATTERN = /(https?:\/\/[^\s]+)/i;
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

function readStringField(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function readNumberField(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Number(value.trim());
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

function readStringListField(value: unknown, limit = 16): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const cleaned = value
    .map((item) => String(item || "").trim())
    .filter((item) => item.length > 0);
  return Array.from(new Set(cleaned)).slice(0, Math.max(1, limit));
}

function readObjectListField(value: unknown, limit = 16): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
    .slice(0, Math.max(1, limit));
}

function mergeLiveSceneData(
  events: AgentActivityEvent[],
  activeEvent: AgentActivityEvent | null,
): Record<string, unknown> {
  const merged: Record<string, unknown> = {};

  const assignString = (key: string, value: unknown) => {
    const text = readStringField(value);
    if (text) {
      merged[key] = text;
    }
  };

  const applyPayload = (payload: Record<string, unknown>, eventType: string) => {
    const normalizedType = String(eventType || "").toLowerCase();
    const isPlanningEvent =
      normalizedType.startsWith("plan_") ||
      normalizedType === "planning_started" ||
      normalizedType === "task_understanding_ready" ||
      normalizedType === "llm.task_rewrite_started" ||
      normalizedType === "llm.task_rewrite_completed" ||
      normalizedType === "llm.task_contract_started" ||
      normalizedType === "llm.task_contract_completed" ||
      normalizedType === "llm.plan_decompose_started" ||
      normalizedType === "llm.plan_decompose_completed" ||
      normalizedType === "llm.plan_step" ||
      normalizedType === "llm.plan_fact_coverage";
    const isHighlightEvent = normalizedType.includes("highlight");

    [
      "url",
      "source_url",
      "target_url",
      "page_url",
      "final_url",
      "link",
      "highlight_color",
      "find_query",
      "clipboard_text",
      "doc_id",
      "document_id",
      "document_url",
      "spreadsheet_id",
      "spreadsheet_url",
      "range",
      "step_name",
      "status",
      "tool_id",
      "path",
      "pdf_path",
    ].forEach((key) => assignString(key, payload[key]));

    const searchTerms = readStringListField(payload["search_terms"] ?? payload["planned_search_terms"], 12);
    if (searchTerms.length) {
      merged["search_terms"] = searchTerms;
      if (isPlanningEvent || !Array.isArray(merged["planned_search_terms"])) {
        merged["planned_search_terms"] = searchTerms;
      }
    }

    const keywords = readStringListField(payload["keywords"] ?? payload["planned_keywords"], 16);
    if (keywords.length) {
      if (isPlanningEvent || !Array.isArray(merged["planned_keywords"])) {
        merged["planned_keywords"] = keywords;
      }
      if (isHighlightEvent || !Array.isArray(merged["keywords"])) {
        merged["keywords"] = keywords;
      }
    }

    const highlightedKeywords = readStringListField(payload["highlighted_keywords"], 16);
    if (highlightedKeywords.length) {
      merged["highlighted_keywords"] = highlightedKeywords;
      if (!Array.isArray(merged["keywords"])) {
        merged["keywords"] = highlightedKeywords;
      }
    }

    const stepIds = readStringListField(payload["step_ids"], 16);
    if (stepIds.length) {
      merged["step_ids"] = stepIds;
    }

    const copiedSnippets = readStringListField(payload["copied_snippets"], 12);
    if (copiedSnippets.length) {
      merged["copied_snippets"] = copiedSnippets;
    }

    const copiedWords = readStringListField(payload["copied_words"], 12);
    if (copiedWords.length) {
      merged["copied_words"] = copiedWords;
    }

    const highlightedWords = readObjectListField(payload["highlighted_words"], 18);
    if (highlightedWords.length) {
      merged["highlighted_words"] = highlightedWords;
    }

    const highlightRegions = readObjectListField(payload["highlight_regions"], 12);
    if (highlightRegions.length) {
      merged["highlight_regions"] = highlightRegions;
    }

    const matchCount = readNumberField(payload["match_count"]);
    if (matchCount !== null) {
      merged["match_count"] = Math.max(0, matchCount);
    }

    const taskUnderstanding = payload["task_understanding"];
    if (taskUnderstanding && typeof taskUnderstanding === "object") {
      const understanding = taskUnderstanding as Record<string, unknown>;
      const plannedSearchTerms = readStringListField(understanding["planned_search_terms"], 12);
      if (plannedSearchTerms.length) {
        merged["planned_search_terms"] = plannedSearchTerms;
      }
      const plannedKeywords = readStringListField(understanding["planned_keywords"], 16);
      if (plannedKeywords.length) {
        merged["planned_keywords"] = plannedKeywords;
      }
    }
  };

  for (const event of events) {
    const payload =
      event.data && typeof event.data === "object"
        ? (event.data as Record<string, unknown>)
        : event.metadata && typeof event.metadata === "object"
          ? (event.metadata as Record<string, unknown>)
          : null;
    if (!payload) {
      continue;
    }
    applyPayload(payload, event.event_type);
  }

  if (activeEvent?.data && typeof activeEvent.data === "object") {
    applyPayload(activeEvent.data as Record<string, unknown>, activeEvent.event_type);
  }

  return merged;
}

function phaseForEvent(event: AgentActivityEvent | null): ActivityPhaseKey | null {
  if (!event) {
    return null;
  }
  const type = String(event.event_type || "").toLowerCase();
  const title = String(event.title || "").toLowerCase();

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
  if (type === "policy_blocked" && title.includes("clarification")) {
    return "clarification";
  }
  if (
    type === "planning_started" ||
    type.startsWith("plan_") ||
    type === "llm.plan_decompose_started" ||
    type === "llm.plan_decompose_completed" ||
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
    type === "verification_started" ||
    type === "verification_check" ||
    type === "verification_completed"
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

  const activePhase = phaseForEvent(activeEvent);
  return PHASE_ORDER.map((phase) => {
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

function resolveEventSourceUrl(event: AgentActivityEvent): string {
  const candidates = [
    event.data?.["source_url"],
    event.metadata?.["source_url"],
    event.data?.["document_url"],
    event.metadata?.["document_url"],
    event.data?.["spreadsheet_url"],
    event.metadata?.["spreadsheet_url"],
    event.data?.["url"],
    event.metadata?.["url"],
  ];
  for (const value of candidates) {
    const text = readStringField(value);
    if (text.startsWith("http://") || text.startsWith("https://")) {
      return text;
    }
  }
  return "";
}

export {
  derivePhaseTimeline,
  mergeLiveSceneData,
  phaseForEvent,
  readNumberField,
  readObjectListField,
  readStringField,
  readStringListField,
  resolveEventSourceUrl,
  URL_PATTERN,
};
export type { ActivityPhaseKey, ActivityPhaseRow, ActivityPhaseState };
