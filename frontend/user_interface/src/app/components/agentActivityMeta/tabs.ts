import type { PreviewTab } from "./types";

function tabForEventType(eventType: string): PreviewTab {
  const normalized = String(eventType || "").toLowerCase();
  if (
    normalized.startsWith("browser_") ||
    normalized.startsWith("browser.") ||
    normalized.startsWith("web_") ||
    normalized.startsWith("web.") ||
    normalized.startsWith("brave.") ||
    normalized.startsWith("bing.") ||
    normalized.includes("search")
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
