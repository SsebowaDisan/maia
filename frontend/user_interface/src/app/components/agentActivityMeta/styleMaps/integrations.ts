import {
  Activity,
  CheckCircle2,
  Eye,
  FileSearch,
  Search,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import type { EventStyle } from "../types";

const integrationEventStyles: Record<string, EventStyle> = {
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
  "drive.share_started": {
    label: "Share Link",
    icon: Activity,
    accent: "text-[#4c4c50]",
  },
  "drive.share_completed": {
    label: "Shared",
    icon: CheckCircle2,
    accent: "text-[#2f6a3f]",
  },
  "drive.share_failed": {
    label: "Share Failed",
    icon: TriangleAlert,
    accent: "text-[#9b1c1c]",
  },
  "llm.context_summary": {
    label: "Context Summary",
    icon: Sparkles,
    accent: "text-[#4c4c50]",
  },
  "llm.research_depth_profile": {
    label: "Depth Profile",
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

export { integrationEventStyles };
