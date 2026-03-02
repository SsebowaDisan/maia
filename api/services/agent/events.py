from __future__ import annotations

from typing import Any, Literal

from api.services.agent.models import AgentActivityEvent, new_id

EVENT_SCHEMA_VERSION = "1.0"

EventStage = Literal["system", "plan", "tool", "ui_action", "preview", "result", "error"]
EventStatus = Literal[
    "pending",
    "in_progress",
    "completed",
    "failed",
    "blocked",
    "waiting",
    "info",
]

_STAGE_OVERRIDES: dict[str, EventStage] = {
    "desktop_starting": "system",
    "desktop_ready": "system",
    "task_understanding_started": "plan",
    "task_understanding_ready": "plan",
    "preflight_started": "system",
    "preflight_check": "system",
    "preflight_completed": "system",
    "planning_started": "plan",
    "plan_candidate": "plan",
    "plan_refined": "plan",
    "plan_ready": "plan",
    "llm.task_rewrite_started": "plan",
    "llm.task_rewrite_completed": "plan",
    "llm.task_contract_started": "plan",
    "llm.task_contract_completed": "plan",
    "llm.clarification_requested": "plan",
    "llm.clarification_resolved": "plan",
    "llm.context_memory": "plan",
    "llm.plan_decompose_started": "plan",
    "llm.plan_decompose_completed": "plan",
    "llm.capability_plan": "plan",
    "llm.web_routing_decision": "plan",
    "llm.plan_step": "plan",
    "llm.plan_fact_coverage": "plan",
    "llm.delivery_check_started": "result",
    "llm.delivery_check_completed": "result",
    "llm.delivery_check_failed": "result",
    "retrieval_query_rewrite": "plan",
    "retrieval_fused": "tool",
    "retrieval_quality_assessed": "result",
    "api_call_started": "tool",
    "api_call_completed": "tool",
    "verification_started": "result",
    "verification_check": "result",
    "verification_completed": "result",
    "web_kpi_summary": "result",
    "web_evidence_summary": "result",
    "web_release_gate": "result",
    "action_prepared": "ui_action",
    "approval_required": "system",
    "approval_granted": "system",
    "policy_blocked": "error",
    "synthesis_started": "result",
    "synthesis_completed": "result",
    "response_writing": "result",
    "response_written": "result",
    "event_coverage": "result",
}

EVENT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "desktop_starting": {"description": "Secure desktop boot sequence begins", "user_visible": True},
    "desktop_ready": {"description": "Desktop is ready for live execution", "user_visible": True},
    "task_understanding_started": {"description": "Task understanding begins", "user_visible": True},
    "task_understanding_ready": {"description": "Task understanding completed", "user_visible": True},
    "preflight_started": {"description": "Preflight validation started", "user_visible": True},
    "preflight_check": {"description": "Single preflight check result", "user_visible": True},
    "preflight_completed": {"description": "Preflight validation completed", "user_visible": True},
    "planning_started": {"description": "Planner starts evaluating intent", "user_visible": True},
    "plan_candidate": {"description": "Planner produced a candidate plan", "user_visible": True},
    "plan_refined": {"description": "Planner refined execution order", "user_visible": True},
    "plan_ready": {"description": "Final execution plan is available", "user_visible": True},
    "llm.task_rewrite_started": {"description": "LLM rewrite of user task started", "user_visible": True},
    "llm.task_rewrite_completed": {"description": "LLM rewrite of user task completed", "user_visible": True},
    "llm.task_contract_started": {"description": "LLM task contract build started", "user_visible": True},
    "llm.task_contract_completed": {"description": "LLM task contract build completed", "user_visible": True},
    "llm.clarification_requested": {"description": "Clarification is required before execution", "user_visible": True},
    "llm.clarification_resolved": {"description": "Clarification requirements resolved", "user_visible": True},
    "llm.plan_decompose_started": {"description": "LLM step decomposition started", "user_visible": True},
    "llm.plan_decompose_completed": {"description": "LLM step decomposition completed", "user_visible": True},
    "llm.capability_plan": {"description": "Capability-based planning analysis completed", "user_visible": True},
    "llm.web_routing_decision": {"description": "LLM web routing decision selected", "user_visible": True},
    "llm.plan_step": {"description": "Planned execution step generated", "user_visible": True},
    "llm.plan_fact_coverage": {"description": "Required-fact coverage was checked for the plan", "user_visible": True},
    "llm.location_brief": {"description": "LLM location finding synthesized from evidence", "user_visible": True},
    "llm.delivery_check_started": {"description": "Task contract verification started", "user_visible": True},
    "llm.delivery_check_completed": {"description": "Task contract verification passed", "user_visible": True},
    "llm.delivery_check_failed": {"description": "Task contract verification failed", "user_visible": True},
    "retrieval_query_rewrite": {"description": "Generated rewritten search queries", "user_visible": True},
    "retrieval_fused": {"description": "Search runs fused into final ranking", "user_visible": True},
    "retrieval_quality_assessed": {"description": "Retrieval quality evaluated", "user_visible": True},
    "tool_queued": {"description": "Tool scheduled for execution", "user_visible": True},
    "tool_started": {"description": "Tool execution started", "user_visible": True},
    "tool_progress": {"description": "Tool reports progress", "user_visible": True},
    "tool_completed": {"description": "Tool execution completed", "user_visible": True},
    "tool_failed": {"description": "Tool execution failed", "user_visible": True},
    "web_search_started": {"description": "Web search query issued", "user_visible": True},
    "web_result_opened": {"description": "Top web result opened", "user_visible": True},
    "api_call_started": {"description": "External API call started", "user_visible": True},
    "api_call_completed": {"description": "External API call completed", "user_visible": True},
    "browser_open": {"description": "Browser session opened", "user_visible": True},
    "browser_navigate": {"description": "Browser navigates to target URL", "user_visible": True},
    "browser_scroll": {"description": "Browser scrolling page", "user_visible": True},
    "browser_extract": {"description": "Extracting content from page", "user_visible": True},
    "browser_find_in_page": {"description": "Searching terms inside current page", "user_visible": True},
    "browser_cookie_accept": {"description": "Cookie consent accepted", "user_visible": True},
    "browser_cookie_check": {"description": "Cookie consent check completed", "user_visible": True},
    "browser_interaction_started": {"description": "Browser interaction step started", "user_visible": True},
    "browser_interaction_completed": {"description": "Browser interaction step completed", "user_visible": True},
    "browser_interaction_failed": {"description": "Browser interaction step failed", "user_visible": True},
    "browser_interaction_policy": {"description": "Browser interaction safety policy evaluated", "user_visible": True},
    "browser_contact_form_detected": {
        "description": "Contact form detected on target website",
        "user_visible": True,
    },
    "browser_contact_fill_name": {
        "description": "Contact form name field populated",
        "user_visible": True,
    },
    "browser_contact_fill_email": {
        "description": "Contact form email field populated",
        "user_visible": True,
    },
    "browser_contact_fill_subject": {
        "description": "Contact form subject field populated",
        "user_visible": True,
    },
    "browser_contact_fill_message": {
        "description": "Contact form message field populated",
        "user_visible": True,
    },
    "browser_contact_submit": {
        "description": "Contact form submitted",
        "user_visible": True,
    },
    "browser_contact_confirmation": {
        "description": "Post-submit confirmation evaluated",
        "user_visible": True,
    },
    "document_opened": {"description": "Document opened from indexed files", "user_visible": True},
    "document_scanned": {"description": "Document sections scanned", "user_visible": True},
    "highlights_detected": {"description": "Relevant highlights detected", "user_visible": True},
    "pdf_open": {"description": "PDF opened in preview stage", "user_visible": True},
    "pdf_page_change": {"description": "PDF page changed in preview", "user_visible": True},
    "pdf_scan_region": {"description": "Scanning region on PDF page", "user_visible": True},
    "pdf_evidence_linked": {"description": "Evidence linked to response claim", "user_visible": True},
    "action_prepared": {"description": "Action payload prepared", "user_visible": True},
    "email_draft_create": {"description": "Draft email started", "user_visible": True},
    "email_set_to": {"description": "Recipient applied to email draft", "user_visible": True},
    "email_set_subject": {"description": "Subject applied to email draft", "user_visible": True},
    "email_type_body": {"description": "Body text typed incrementally", "user_visible": True},
    "email_set_body": {"description": "Body applied to email draft", "user_visible": True},
    "email_ready_to_send": {"description": "Draft ready to send", "user_visible": True},
    "email_auth_required": {"description": "Gmail web session requires authentication", "user_visible": True},
    "email_sent": {"description": "Email was sent", "user_visible": True},
    "doc_open": {"description": "Editable document opened", "user_visible": True},
    "doc_locate_anchor": {"description": "Anchor located in document", "user_visible": True},
    "doc_insert_text": {"description": "Text inserted into document", "user_visible": True},
    "doc_save": {"description": "Document saved", "user_visible": True},
    "docs.create_started": {"description": "Google Doc creation started", "user_visible": True},
    "docs.create_completed": {"description": "Google Doc creation completed", "user_visible": True},
    "docs.copy_started": {"description": "Google Doc template copy started", "user_visible": True},
    "docs.copy_completed": {"description": "Google Doc template copy completed", "user_visible": True},
    "docs.replace_started": {"description": "Google Doc placeholder replacement started", "user_visible": True},
    "docs.replace_completed": {"description": "Google Doc placeholder replacement completed", "user_visible": True},
    "docs.insert_started": {"description": "Google Doc text insertion started", "user_visible": True},
    "docs.insert_completed": {"description": "Google Doc text insertion completed", "user_visible": True},
    "docs.export_started": {"description": "Google Doc export started", "user_visible": True},
    "docs.export_completed": {"description": "Google Doc export completed", "user_visible": True},
    "sheets.create_started": {"description": "Google Sheet creation started", "user_visible": True},
    "sheets.create_completed": {"description": "Google Sheet creation completed", "user_visible": True},
    "sheets.read_started": {"description": "Google Sheet read started", "user_visible": True},
    "sheets.read_completed": {"description": "Google Sheet read completed", "user_visible": True},
    "sheets.append_started": {"description": "Google Sheet append started", "user_visible": True},
    "sheets.append_completed": {"description": "Google Sheet append completed", "user_visible": True},
    "sheets.update_started": {"description": "Google Sheet update started", "user_visible": True},
    "sheets.update_completed": {"description": "Google Sheet update completed", "user_visible": True},
    "drive.go_to_doc": {"description": "Navigate to Google Doc URL", "user_visible": True},
    "drive.go_to_sheet": {"description": "Navigate to Google Sheet URL", "user_visible": True},
    "llm.context_summary": {"description": "LLM conversation context summary generated", "user_visible": True},
    "llm.context_memory": {"description": "Memory context snippets loaded for planning", "user_visible": True},
    "llm.intent_tags": {"description": "LLM intent tags generated", "user_visible": True},
    "llm.step_summary": {"description": "LLM step summary generated", "user_visible": True},
    "synthesis_started": {"description": "Answer synthesis started", "user_visible": True},
    "response_writing": {"description": "Final response is being written", "user_visible": True},
    "response_written": {"description": "Final response writing completed", "user_visible": True},
    "synthesis_completed": {"description": "Final response finalized", "user_visible": True},
    "verification_started": {"description": "Post-run verification started", "user_visible": True},
    "verification_check": {"description": "Verification check evaluated", "user_visible": True},
    "verification_completed": {"description": "Post-run verification completed", "user_visible": True},
    "web_kpi_summary": {"description": "Web scraping KPI summary generated", "user_visible": True},
    "web_evidence_summary": {"description": "Web evidence summary generated", "user_visible": True},
    "web_release_gate": {"description": "Web release gate thresholds evaluated", "user_visible": True},
    "event_coverage": {"description": "Coverage report for expected events", "user_visible": False},
    "approval_required": {"description": "Action requires human approval", "user_visible": True},
    "approval_granted": {"description": "Approval granted for action", "user_visible": True},
    "policy_blocked": {"description": "Policy blocked an action", "user_visible": True},
}

CORE_EVENT_TYPES: tuple[str, ...] = (
    "desktop_starting",
    "planning_started",
    "plan_ready",
    "tool_started",
    "tool_completed",
    "synthesis_started",
    "synthesis_completed",
)


def infer_stage(event_type: str) -> EventStage:
    if event_type in _STAGE_OVERRIDES:
        return _STAGE_OVERRIDES[event_type]
    if event_type.startswith(("web_", "browser_")):
        return "preview"
    if event_type.startswith(("document_", "pdf_", "email_", "doc_", "docs.", "sheet_", "sheets.", "drive.")):
        return "ui_action"
    if event_type.startswith("tool_"):
        return "tool"
    if event_type.startswith(("error_", "failed_")) or event_type.endswith("_failed"):
        return "error"
    return "system"


def infer_status(event_type: str) -> EventStatus:
    if event_type.endswith("_started") or event_type in {
        "desktop_starting",
        "response_writing",
        "planning_started",
    }:
        return "in_progress"
    if event_type.endswith("_queued"):
        return "pending"
    if event_type.endswith("_ready"):
        return "pending"
    if event_type.endswith("_completed") or event_type in {"desktop_ready", "response_written"}:
        return "completed"
    if event_type == "verification_check":
        return "info"
    if event_type.endswith("_failed"):
        return "failed"
    return "info"


def coverage_report(
    *,
    observed_event_types: list[str],
    expected_event_types: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    expected_unique = list(dict.fromkeys([item for item in expected_event_types if item]))
    observed_unique = list(dict.fromkeys([item for item in observed_event_types if item]))
    expected_set = set(expected_unique)
    observed_set = set(observed_unique)
    covered = sorted(expected_set.intersection(observed_set))
    missing = sorted(expected_set - observed_set)
    coverage_ratio = 1.0 if not expected_set else len(covered) / float(len(expected_set))
    return {
        "expected_total": len(expected_set),
        "observed_total": len(observed_set),
        "covered": covered,
        "missing": missing,
        "coverage_ratio": round(coverage_ratio, 4),
        "coverage_percent": round(coverage_ratio * 100.0, 2),
    }


class RunEventEmitter:
    """Builds schema-stable events with monotonically increasing sequence IDs."""

    def __init__(
        self,
        *,
        run_id: str,
        start_seq: int = 0,
        schema_version: str = EVENT_SCHEMA_VERSION,
    ) -> None:
        self.run_id = run_id
        self.seq = max(0, int(start_seq))
        self.schema_version = schema_version

    def emit(
        self,
        *,
        event_type: str,
        title: str,
        detail: str = "",
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        stage: EventStage | None = None,
        status: EventStatus | None = None,
        snapshot_ref: str | None = None,
    ) -> AgentActivityEvent:
        self.seq += 1
        payload_data = dict(data or {})
        if metadata:
            payload_data.update(metadata)
        return AgentActivityEvent(
            event_id=new_id("evt"),
            run_id=self.run_id,
            event_type=event_type,
            title=title,
            detail=detail,
            metadata=payload_data,
            data=payload_data,
            seq=self.seq,
            stage=stage or infer_stage(event_type),
            status=status or infer_status(event_type),
            event_schema_version=self.schema_version,
            snapshot_ref=snapshot_ref,
        )
