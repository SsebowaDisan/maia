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
    "planning_started": "plan",
    "plan_candidate": "plan",
    "plan_refined": "plan",
    "plan_ready": "plan",
    "retrieval_query_rewrite": "plan",
    "retrieval_fused": "tool",
    "retrieval_quality_assessed": "result",
    "verification_started": "result",
    "verification_check": "result",
    "verification_completed": "result",
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
    "planning_started": {"description": "Planner starts evaluating intent", "user_visible": True},
    "plan_candidate": {"description": "Planner produced a candidate plan", "user_visible": True},
    "plan_refined": {"description": "Planner refined execution order", "user_visible": True},
    "plan_ready": {"description": "Final execution plan is available", "user_visible": True},
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
    "browser_open": {"description": "Browser session opened", "user_visible": True},
    "browser_navigate": {"description": "Browser navigates to target URL", "user_visible": True},
    "browser_scroll": {"description": "Browser scrolling page", "user_visible": True},
    "browser_extract": {"description": "Extracting content from page", "user_visible": True},
    "browser_cookie_accept": {"description": "Cookie consent accepted", "user_visible": True},
    "browser_cookie_check": {"description": "Cookie consent check completed", "user_visible": True},
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
    "email_set_body": {"description": "Body applied to email draft", "user_visible": True},
    "email_ready_to_send": {"description": "Draft ready to send", "user_visible": True},
    "email_auth_required": {"description": "Gmail web session requires authentication", "user_visible": True},
    "email_sent": {"description": "Email was sent", "user_visible": True},
    "doc_open": {"description": "Editable document opened", "user_visible": True},
    "doc_locate_anchor": {"description": "Anchor located in document", "user_visible": True},
    "doc_insert_text": {"description": "Text inserted into document", "user_visible": True},
    "doc_save": {"description": "Document saved", "user_visible": True},
    "synthesis_started": {"description": "Answer synthesis started", "user_visible": True},
    "response_writing": {"description": "Final response is being written", "user_visible": True},
    "response_written": {"description": "Final response writing completed", "user_visible": True},
    "synthesis_completed": {"description": "Final response finalized", "user_visible": True},
    "verification_started": {"description": "Post-run verification started", "user_visible": True},
    "verification_check": {"description": "Verification check evaluated", "user_visible": True},
    "verification_completed": {"description": "Post-run verification completed", "user_visible": True},
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
    if event_type.startswith(("document_", "pdf_", "email_", "doc_")):
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
