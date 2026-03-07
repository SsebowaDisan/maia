from __future__ import annotations

from typing import Any

from api.schemas import ChatRequest
from api.services.agent.llm_execution_support import (
    build_location_delivery_brief,
    polish_email_content,
)
from api.services.agent.models import AgentActivityEvent, utc_now

from ..constants import DELIVERY_ACTION_IDS
from ..models import ExecutionState, TaskPreparation
from ..text_helpers import compact
from .models import DeliveryRuntime


def should_attempt_delivery(
    *,
    task_prep: TaskPreparation,
    state: ExecutionState,
) -> bool:
    task_intelligence = task_prep.task_intelligence
    delivery_requested = bool(
        task_intelligence.requires_delivery
        and task_intelligence.delivery_email
        and not task_prep.clarification_blocked
    )
    side_effect_state = ""
    side_effect_status_raw = state.execution_context.settings.get("__side_effect_status")
    if isinstance(side_effect_status_raw, dict):
        send_email_row = side_effect_status_raw.get("send_email")
        if isinstance(send_email_row, dict):
            side_effect_state = " ".join(
                str(send_email_row.get("status") or "").split()
            ).strip().lower()
    if side_effect_state in {"pending", "completed", "failed", "blocked"}:
        return False

    delivery_attempted = any(
        item.tool_id in DELIVERY_ACTION_IDS
        and str(item.status or "").strip().lower() in {"success", "failed", "skipped"}
        for item in state.all_actions
    )
    return delivery_requested and not delivery_attempted


def build_delivery_runtime(*, state: ExecutionState) -> DeliveryRuntime:
    return DeliveryRuntime(
        step=len(state.executed_steps) + 1,
        started_at=utc_now().isoformat(),
    )


def prepare_delivery_content(
    *,
    request: ChatRequest,
    task_prep: TaskPreparation,
    state: ExecutionState,
    runtime: DeliveryRuntime,
    activity_event_factory,
) -> tuple[str, str, list[AgentActivityEvent]]:
    task_intelligence = task_prep.task_intelligence
    report_title = str(
        state.execution_context.settings.get("__latest_report_title")
        or "Website Analysis Report"
    ).strip()
    report_body = str(
        state.execution_context.settings.get("__latest_report_content") or ""
    ).strip()
    if not report_body:
        summary_lines = [
            f"- {row.get('title') or row.get('tool_id')}: {row.get('summary') or ''}".strip()
            for row in state.executed_steps
            if str(row.get("status") or "") == "success"
        ]
        report_body = "\n".join(
            [
                "No dedicated report draft was generated; sending execution summary.",
                "",
                *summary_lines[:10],
            ]
        ).strip()

    pre_send_events: list[AgentActivityEvent] = []
    required_facts_for_delivery = (
        [
            str(item).strip()
            for item in task_prep.task_contract.get("required_facts", [])
            if str(item).strip()
        ]
        if isinstance(task_prep.task_contract, dict)
        and isinstance(task_prep.task_contract.get("required_facts"), list)
        else []
    )
    delivery_intent_tags = set(task_intelligence.intent_tags)
    location_delivery_requested = "location_lookup" in delivery_intent_tags
    if not required_facts_for_delivery and location_delivery_requested:
        required_facts_for_delivery = (
            [
                str(item).strip()
                for item in task_prep.contract_success_checks
                if str(item).strip()
            ]
            if isinstance(task_prep.contract_success_checks, list)
            else []
        )[:4]
        if not required_facts_for_delivery and task_intelligence.objective:
            required_facts_for_delivery = [str(task_intelligence.objective).strip()[:220]]
    if location_delivery_requested and required_facts_for_delivery:
        location_brief = build_location_delivery_brief(
            request_message=request.message,
            objective=task_intelligence.objective,
            report_body=report_body,
            browser_findings=(
                state.execution_context.settings.get("__latest_browser_findings")
                if isinstance(
                    state.execution_context.settings.get("__latest_browser_findings"),
                    dict,
                )
                else {}
            ),
            sources=[
                {
                    "label": str(source.label or "").strip(),
                    "url": str(source.url or "").strip(),
                    "metadata": (
                        source.metadata if isinstance(source.metadata, dict) else {}
                    ),
                }
                for source in state.all_sources[:12]
            ],
        )
        location_summary = " ".join(str(location_brief.get("summary") or "").split()).strip()
        location_address = " ".join(str(location_brief.get("address") or "").split()).strip()
        location_urls = (
            [
                str(item).strip()
                for item in location_brief.get("evidence_urls", [])
                if str(item).strip()
            ]
            if isinstance(location_brief.get("evidence_urls"), list)
            else []
        )
        location_confidence = " ".join(
            str(location_brief.get("confidence") or "").split()
        ).strip()
        if location_summary:
            location_lines = [
                "## Required Fact Findings",
                f"- Summary: {location_summary}",
            ]
            if location_address:
                location_lines.append(f"- Extracted detail: {location_address}")
            if location_confidence:
                location_lines.append(f"- Confidence: {location_confidence}")
            for url in location_urls[:4]:
                location_lines.append(f"- Evidence URL: {url}")
            report_body = "\n".join([report_body.strip(), "", *location_lines]).strip()
            pre_send_events.append(
                activity_event_factory(
                    event_type="llm.location_brief",
                    title="LLM fact synthesis",
                    detail=compact(location_summary, 180),
                    metadata={
                        "summary": location_summary,
                        "extracted_detail": location_address,
                        "evidence_urls": location_urls[:4],
                        "confidence": location_confidence or "unknown",
                        "required_facts": required_facts_for_delivery[:6],
                        "tool_id": runtime.tool_id,
                        "step": runtime.step,
                    },
                )
            )

    preferred_tone = str(
        task_intelligence.preferred_tone or task_prep.user_preferences.get("tone") or ""
    ).strip()
    context_summary = f"{task_intelligence.objective} Tone: {preferred_tone}".strip()
    polished_email = polish_email_content(
        subject=report_title or "Website Analysis Report",
        body_text=report_body or "Report requested, but no body content was generated.",
        recipient=task_intelligence.delivery_email,
        context_summary=context_summary,
    )
    report_title = str(
        polished_email.get("subject") or report_title or "Website Analysis Report"
    ).strip()
    report_body = str(
        polished_email.get("body_text")
        or report_body
        or "Report requested, but no body content was generated."
    ).strip()
    return report_title, report_body, pre_send_events
