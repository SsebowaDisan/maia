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
import type { EventStyle } from "../types";

const coreEventStyles: Record<string, EventStyle> = {
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
  "llm.plan_fact_coverage": {
    label: "Fact Coverage",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
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
  browser_contact_required_scan: {
    label: "Scan Required",
    icon: FileSearch,
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
  browser_contact_fill_company: {
    label: "Fill Company",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  browser_contact_fill_phone: {
    label: "Fill Phone",
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
  browser_contact_llm_fill: {
    label: "LLM Fill",
    icon: Sparkles,
    accent: "text-[#4c4c50]",
  },
  "llm.form_field_mapping": {
    label: "LLM Field Map",
    icon: Sparkles,
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
};

export { coreEventStyles };
