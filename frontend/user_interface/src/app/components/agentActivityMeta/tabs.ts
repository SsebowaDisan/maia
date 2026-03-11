import type { PreviewTab } from "./types";
import {
  EVT_AGENT_HANDOFF,
  EVT_AGENT_WAITING,
  EVT_APPROVAL_GRANTED,
  EVT_APPROVAL_REQUIRED,
  EVT_EVENT_COVERAGE,
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
    normalized === EVT_EVENT_COVERAGE
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
