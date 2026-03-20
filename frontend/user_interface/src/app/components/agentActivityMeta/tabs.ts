import type { PreviewTab } from "./types";
import {
  EVT_AGENT_DIALOGUE_RESOLVED,
  EVT_AGENT_DIALOGUE_STARTED,
  EVT_AGENT_DIALOGUE_TURN,
  EVT_AGENT_HANDOFF,
  EVT_AGENT_WAITING,
  EVT_APPROVAL_GRANTED,
  EVT_APPROVAL_REQUIRED,
  EVT_ASSEMBLY_COMPLETED,
  EVT_ASSEMBLY_COMPLETE,
  EVT_ASSEMBLY_EDGE_ADDED,
  EVT_ASSEMBLY_ERROR,
  EVT_ASSEMBLY_STARTED,
  EVT_ASSEMBLY_STEP_ADDED,
  EVT_BRAIN_ANSWER_RECEIVED,
  EVT_BRAIN_QUESTION,
  EVT_BRAIN_REVIEW_DECISION,
  EVT_BRAIN_REVIEW_STARTED,
  EVT_BRAIN_REVISION_REQUESTED,
  EVT_EVENT_COVERAGE,
  EVT_EXECUTION_STARTING,
  EVT_HANDOFF_PAUSED,
  EVT_HANDOFF_RESUMED,
  EVT_POLICY_BLOCKED,
  EVT_WEB_EVIDENCE_SUMMARY,
  EVT_WEB_KPI_SUMMARY,
  EVT_WEB_RELEASE_GATE,
} from "../../constants/eventTypes";

function tabForEventType(eventType: string): PreviewTab {
  const normalized = String(eventType || "").toLowerCase();
  if (
    normalized === EVT_WEB_KPI_SUMMARY ||
    normalized === EVT_WEB_EVIDENCE_SUMMARY ||
    normalized === EVT_WEB_RELEASE_GATE
  ) {
    return "system";
  }
  if (
    normalized === EVT_APPROVAL_REQUIRED ||
    normalized === EVT_APPROVAL_GRANTED ||
    normalized === EVT_POLICY_BLOCKED ||
    normalized === EVT_HANDOFF_PAUSED ||
    normalized === EVT_HANDOFF_RESUMED ||
    normalized === EVT_AGENT_WAITING ||
    normalized === EVT_AGENT_HANDOFF ||
    normalized === EVT_EVENT_COVERAGE ||
    normalized === EVT_BRAIN_REVIEW_STARTED ||
    normalized === EVT_BRAIN_REVIEW_DECISION ||
    normalized === EVT_BRAIN_REVISION_REQUESTED ||
    normalized === EVT_BRAIN_QUESTION ||
    normalized === EVT_BRAIN_ANSWER_RECEIVED ||
    normalized === EVT_AGENT_DIALOGUE_TURN ||
    normalized === EVT_AGENT_DIALOGUE_STARTED ||
    normalized === EVT_AGENT_DIALOGUE_RESOLVED ||
    normalized === EVT_ASSEMBLY_STARTED ||
    normalized === EVT_ASSEMBLY_STEP_ADDED ||
    normalized === EVT_ASSEMBLY_EDGE_ADDED ||
    normalized === EVT_ASSEMBLY_COMPLETE ||
    normalized === EVT_ASSEMBLY_COMPLETED ||
    normalized === EVT_ASSEMBLY_ERROR ||
    normalized === EVT_EXECUTION_STARTING
  ) {
    return "system";
  }
  if (
    normalized.startsWith("browser_") ||
    normalized.startsWith("browser.") ||
    normalized.startsWith("web_") ||
    normalized.startsWith("web.") ||
    normalized.startsWith("brave.") ||
    normalized.startsWith("bing.")
  ) {
    return "browser";
  }
  if (
    normalized.startsWith("email_") ||
    normalized.startsWith("email.") ||
    normalized.startsWith("gmail.") ||
    normalized.startsWith("gmail_")
  ) {
    return "email";
  }
  if (
    normalized.startsWith("document_") ||
    normalized.startsWith("document.") ||
    normalized.startsWith("pdf_") ||
    normalized.startsWith("pdf.") ||
    normalized.startsWith("doc_") ||
    normalized.startsWith("doc.") ||
    normalized.startsWith("docs.") ||
    normalized.startsWith("sheet_") ||
    normalized.startsWith("sheet.") ||
    normalized.startsWith("sheets.") ||
    normalized.startsWith("drive.")
  ) {
    return "document";
  }
  return "system";
}

export { tabForEventType };
