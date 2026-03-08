import type { AgentActivityEvent, ClarificationPrompt } from "../../types";
import { type AccessMode, type AgentMode, readStringList } from "./constants";

function clarificationPromptFromEvent(options: {
  event: AgentActivityEvent;
  originalRequest: string;
  agentMode: AgentMode;
  accessMode: AccessMode;
}): ClarificationPrompt | null {
  const { event, originalRequest, agentMode, accessMode } = options;
  const eventType = String(event.event_type || "").trim().toLowerCase();
  const title = String(event.title || "").trim().toLowerCase();
  const data =
    (event.data && typeof event.data === "object"
      ? (event.data as Record<string, unknown>)
      : event.metadata && typeof event.metadata === "object"
        ? (event.metadata as Record<string, unknown>)
        : {}) || {};
  const missingRequirements = readStringList(data["missing_requirements"], 8);
  const questions = readStringList(data["questions"], 8);
  const likelyClarificationEvent =
    eventType === "llm.clarification_requested" ||
    (eventType === "policy_blocked" && title.includes("clarification")) ||
    (eventType === "policy_blocked" && (missingRequirements.length > 0 || questions.length > 0));
  if (!likelyClarificationEvent) {
    return null;
  }
  const fallbackRows =
    missingRequirements.length > 0
      ? missingRequirements
      : String(event.detail || "")
          .split(";")
          .map((item) => item.trim())
          .filter((item) => item.length > 0)
          .slice(0, 6);
  const normalizedQuestions = questions.length > 0
    ? questions
    : fallbackRows.map((item) => `Please provide: ${item}`);
  if (!normalizedQuestions.length && !fallbackRows.length) {
    return null;
  }
  return {
    runId: String(event.run_id || "").trim(),
    originalRequest: String(originalRequest || "").trim(),
    questions: normalizedQuestions,
    missingRequirements: fallbackRows,
    agentMode,
    accessMode,
  };
}

export { clarificationPromptFromEvent };
