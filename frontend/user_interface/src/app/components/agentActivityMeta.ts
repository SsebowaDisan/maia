import {
  Activity,
  CheckCircle2,
  Eye,
  FileSearch,
  Monitor,
  Search,
  Sparkles,
  TriangleAlert,
  Wrench,
} from "lucide-react";
import type { AgentActivityEvent } from "../types";

export type EventStyle = {
  label: string;
  icon: typeof Activity;
  accent: string;
};

export type PreviewTab = "browser" | "document" | "email" | "system";

const eventStyles: Record<string, EventStyle> = {
  desktop_starting: {
    label: "Desktop Starting",
    icon: Monitor,
    accent: "text-[#4c4c50]",
  },
  desktop_ready: {
    label: "Desktop Ready",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  planning_started: {
    label: "Planning",
    icon: Sparkles,
    accent: "text-[#4c4c50]",
  },
  "llm.task_contract_started": {
    label: "Contract Build",
    icon: Sparkles,
    accent: "text-[#4c4c50]",
  },
  "llm.task_contract_completed": {
    label: "Contract Ready",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  "llm.clarification_requested": {
    label: "Clarification Needed",
    icon: TriangleAlert,
    accent: "text-[#996f22]",
  },
  "llm.clarification_resolved": {
    label: "Clarification Resolved",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  "llm.delivery_check_started": {
    label: "Contract Check",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  "llm.delivery_check_completed": {
    label: "Contract Passed",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  "llm.delivery_check_failed": {
    label: "Contract Gaps",
    icon: TriangleAlert,
    accent: "text-[#996f22]",
  },
  task_understanding_started: {
    label: "Understanding",
    icon: Sparkles,
    accent: "text-[#4c4c50]",
  },
  task_understanding_ready: {
    label: "Task Ready",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  plan_ready: {
    label: "Plan Ready",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  plan_candidate: {
    label: "Plan Candidate",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  plan_refined: {
    label: "Plan Refined",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  web_search_started: {
    label: "Web Search",
    icon: Search,
    accent: "text-[#4c4c50]",
  },
  web_result_opened: {
    label: "Open Source",
    icon: Eye,
    accent: "text-[#4c4c50]",
  },
  document_opened: {
    label: "Open Document",
    icon: FileSearch,
    accent: "text-[#4c4c50]",
  },
  document_scanned: {
    label: "Scan Document",
    icon: FileSearch,
    accent: "text-[#4c4c50]",
  },
  highlights_detected: {
    label: "Highlight Evidence",
    icon: Sparkles,
    accent: "text-[#4c4c50]",
  },
  action_prepared: {
    label: "Prepare Action",
    icon: Wrench,
    accent: "text-[#4c4c50]",
  },
  browser_open: {
    label: "Open Browser",
    icon: Monitor,
    accent: "text-[#4c4c50]",
  },
  browser_navigate: {
    label: "Navigate",
    icon: Search,
    accent: "text-[#4c4c50]",
  },
  browser_scroll: {
    label: "Scroll",
    icon: Eye,
    accent: "text-[#4c4c50]",
  },
  browser_extract: {
    label: "Extract Content",
    icon: FileSearch,
    accent: "text-[#4c4c50]",
  },
  browser_find_in_page: {
    label: "Find In Page",
    icon: Search,
    accent: "text-[#4c4c50]",
  },
  browser_keyword_highlight: {
    label: "Highlight Keywords",
    icon: Sparkles,
    accent: "text-[#4c4c50]",
  },
  browser_copy_selection: {
    label: "Copy Selection",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  browser_cookie_accept: {
    label: "Cookie Consent",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  browser_cookie_check: {
    label: "Cookie Check",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  browser_contact_form_detected: {
    label: "Contact Form",
    icon: Search,
    accent: "text-[#4c4c50]",
  },
  browser_contact_fill_name: {
    label: "Fill Name",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  browser_contact_fill_email: {
    label: "Fill Email",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  browser_contact_fill_subject: {
    label: "Fill Subject",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  browser_contact_fill_message: {
    label: "Fill Message",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  browser_contact_submit: {
    label: "Submit Form",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  browser_contact_confirmation: {
    label: "Confirm Submit",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  clipboard_copy: {
    label: "Copy",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  clipboard_paste: {
    label: "Paste",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  doc_open: {
    label: "Open Document",
    icon: FileSearch,
    accent: "text-[#4c4c50]",
  },
  doc_locate_anchor: {
    label: "Locate Section",
    icon: Search,
    accent: "text-[#4c4c50]",
  },
  doc_insert_text: {
    label: "Insert Text",
    icon: Sparkles,
    accent: "text-[#4c4c50]",
  },
  doc_type_text: {
    label: "Typing",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  doc_copy_clipboard: {
    label: "Copy",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  doc_paste_clipboard: {
    label: "Paste",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  doc_save: {
    label: "Save Document",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  "docs.create_started": {
    label: "Doc Create",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  "docs.create_completed": {
    label: "Doc Ready",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  "docs.copy_started": {
    label: "Copy Template",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  "docs.copy_completed": {
    label: "Template Copied",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  "docs.replace_started": {
    label: "Replace Fields",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  "docs.replace_completed": {
    label: "Fields Replaced",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  "docs.insert_started": {
    label: "Insert Text",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  "docs.insert_completed": {
    label: "Text Inserted",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  "docs.export_started": {
    label: "Export PDF",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  "docs.export_completed": {
    label: "PDF Exported",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  sheet_open: {
    label: "Open Sheet",
    icon: FileSearch,
    accent: "text-[#4c4c50]",
  },
  sheet_cell_update: {
    label: "Update Cell",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  sheet_append_row: {
    label: "Append Row",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  sheet_save: {
    label: "Save Sheet",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  "sheets.create_started": {
    label: "Sheet Create",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  "sheets.create_completed": {
    label: "Sheet Ready",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  "sheets.read_started": {
    label: "Sheet Read",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  "sheets.read_completed": {
    label: "Read Complete",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  "sheets.append_started": {
    label: "Append Rows",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  "sheets.append_completed": {
    label: "Rows Appended",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  "sheets.update_started": {
    label: "Update Range",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  "sheets.update_completed": {
    label: "Range Updated",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  "drive.go_to_doc": {
    label: "Open Doc",
    icon: Eye,
    accent: "text-[#4c4c50]",
  },
  "drive.go_to_sheet": {
    label: "Open Sheet",
    icon: Eye,
    accent: "text-[#4c4c50]",
  },
  "llm.context_summary": {
    label: "Context Summary",
    icon: Sparkles,
    accent: "text-[#4c4c50]",
  },
  "llm.task_rewrite_started": {
    label: "Rewrite Task",
    icon: Sparkles,
    accent: "text-[#4c4c50]",
  },
  "llm.task_rewrite_completed": {
    label: "Task Rewritten",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  "llm.plan_decompose_started": {
    label: "Break Into Steps",
    icon: Sparkles,
    accent: "text-[#4c4c50]",
  },
  "llm.plan_decompose_completed": {
    label: "Steps Ready",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  "llm.plan_step": {
    label: "Plan Step",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  "llm.location_brief": {
    label: "Location Brief",
    icon: Sparkles,
    accent: "text-[#4c4c50]",
  },
  "llm.intent_tags": {
    label: "Intent Tags",
    icon: Sparkles,
    accent: "text-[#4c4c50]",
  },
  "llm.step_summary": {
    label: "Step Summary",
    icon: Sparkles,
    accent: "text-[#4c4c50]",
  },
  email_draft_create: {
    label: "Email Draft",
    icon: Sparkles,
    accent: "text-[#4c4c50]",
  },
  email_open_compose: {
    label: "Open Compose",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  email_set_to: {
    label: "Recipient",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  email_set_subject: {
    label: "Subject",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  email_set_body: {
    label: "Body",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  email_type_body: {
    label: "Typing Body",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  email_ready_to_send: {
    label: "Ready to Send",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  email_auth_required: {
    label: "Gmail Login Required",
    icon: TriangleAlert,
    accent: "text-[#9b1c1c]",
  },
  email_click_send: {
    label: "Click Send",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  email_sent: {
    label: "Email Sent",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  tool_queued: {
    label: "Queued",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  tool_started: {
    label: "Tool Running",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  tool_progress: {
    label: "In Progress",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  tool_completed: {
    label: "Completed",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  tool_failed: {
    label: "Failed",
    icon: TriangleAlert,
    accent: "text-[#9b1c1c]",
  },
  synthesis_started: {
    label: "Synthesis",
    icon: Sparkles,
    accent: "text-[#4c4c50]",
  },
  response_writing: {
    label: "Writing",
    icon: Sparkles,
    accent: "text-[#4c4c50]",
  },
  response_written: {
    label: "Draft Ready",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  synthesis_completed: {
    label: "Done",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  verification_started: {
    label: "Verification",
    icon: Sparkles,
    accent: "text-[#4c4c50]",
  },
  verification_check: {
    label: "Check",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  verification_completed: {
    label: "Verified",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  approval_required: {
    label: "Approval Needed",
    icon: TriangleAlert,
    accent: "text-[#9b1c1c]",
  },
  approval_granted: {
    label: "Approval Granted",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  policy_blocked: {
    label: "Policy Blocked",
    icon: TriangleAlert,
    accent: "text-[#9b1c1c]",
  },
  event_coverage: {
    label: "Coverage",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  status: {
    label: "Status",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  "brave.search.query": {
    label: "Web Query",
    icon: Search,
    accent: "text-[#4c4c50]",
  },
  "brave.search.results": {
    label: "Search Results",
    icon: Eye,
    accent: "text-[#4c4c50]",
  },
  retrieval_query_rewrite: {
    label: "Rewrite Queries",
    icon: Sparkles,
    accent: "text-[#4c4c50]",
  },
  retrieval_fused: {
    label: "Fuse Results",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  retrieval_quality_assessed: {
    label: "Quality Check",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
};

export function styleForEvent(event: AgentActivityEvent | null): EventStyle {
  if (!event) {
    return {
      label: "Activity",
      icon: Activity,
      accent: "text-[#4c4c50]",
    };
  }
  return (
    eventStyles[event.event_type] || {
      label: event.event_type,
      icon: Activity,
      accent: "text-[#4c4c50]",
    }
  );
}

export function eventMetadataString(event: AgentActivityEvent | null, key: string): string {
  if (!event || !event.metadata) {
    return "";
  }
  const value = event.metadata[key];
  return typeof value === "string" ? value.trim() : "";
}

export function findRecentMetadataString(events: AgentActivityEvent[], key: string): string {
  for (let idx = events.length - 1; idx >= 0; idx -= 1) {
    const value = eventMetadataString(events[idx], key);
    if (value) {
      return value;
    }
  }
  return "";
}

export function tabForEventType(eventType: string): PreviewTab {
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

export function sampleFilmstripEvents(
  events: AgentActivityEvent[],
  activeIndex: number,
  maxItems = 72,
): Array<{ event: AgentActivityEvent; index: number }> {
  if (events.length <= maxItems) {
    return events.map((event, index) => ({ event, index }));
  }
  const step = Math.max(1, Math.floor(events.length / maxItems));
  const sampled: Array<{ event: AgentActivityEvent; index: number }> = [];
  for (let index = 0; index < events.length; index += step) {
    sampled.push({ event: events[index], index });
  }
  const lastIndex = events.length - 1;
  if (!sampled.some((item) => item.index === lastIndex)) {
    sampled.push({ event: events[lastIndex], index: lastIndex });
  }
  if (!sampled.some((item) => item.index === activeIndex)) {
    sampled.push({ event: events[activeIndex], index: activeIndex });
  }
  sampled.sort((left, right) => left.index - right.index);
  return sampled;
}
