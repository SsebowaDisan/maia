from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.events import CORE_EVENT_TYPES
from api.services.agent.models import AgentActivityEvent
from api.services.agent.planner import PlannedStep
from api.services.agent.planner_helpers import intent_signals
from api.services.agent.tools.base import ToolExecutionContext

from .run_checkpoint_persistence import persist_run_checkpoint
from .role_contracts import resolve_owner_role_for_tool
from .working_context import scoped_working_context_for_role


def selected_file_ids(request: ChatRequest) -> list[str]:
    collected: list[str] = []
    for selection in request.index_selection.values():
        file_ids = getattr(selection, "file_ids", []) or []
        for file_id in file_ids:
            file_id_text = str(file_id).strip()
            if file_id_text:
                collected.append(file_id_text)
    return list(dict.fromkeys(collected))


def selected_index_id(request: ChatRequest) -> int | None:
    for raw_index_id in request.index_selection.keys():
        text = str(raw_index_id).strip()
        if text.isdigit():
            return int(text)
    return None


def expected_event_types(
    *,
    steps: list[PlannedStep],
    request: ChatRequest,
) -> list[str]:
    expected: list[str] = list(CORE_EVENT_TYPES)
    inferred_signals = intent_signals(request)
    has_docs = bool(selected_file_ids(request)) or bool(inferred_signals.get("wants_file_scope"))
    has_web_steps = False
    for step in steps:
        expected.extend(["tool_started", "tool_completed"])
        if step.tool_id in (
            "marketing.web_research",
            "browser.playwright.inspect",
            "web.extract.structured",
            "web.dataset.adapter",
        ):
            has_web_steps = True
            expected.extend(
                [
                    "web_search_started",
                    "browser_open",
                    "browser_navigate",
                    "browser_scroll",
                    "web_result_opened",
                    "browser_extract",
                ]
            )
        if step.tool_id == "browser.contact_form.send":
            expected.extend(
                [
                    "browser_open",
                    "browser_cookie_accept",
                    "browser_contact_form_detected",
                    "browser_contact_required_scan",
                    "browser_contact_fill_name",
                    "browser_contact_fill_email",
                    "browser_contact_fill_company",
                    "browser_contact_fill_phone",
                    "browser_contact_fill_subject",
                    "browser_contact_fill_message",
                    "browser_contact_submit",
                    "browser_contact_confirmation",
                ]
            )
        if has_docs and step.tool_id in (
            "report.generate",
            "data.dataset.analyze",
            "data.science.profile",
            "data.science.visualize",
            "data.science.ml.train",
            "data.science.deep_learning.train",
            "invoice.create",
            "docs.create",
            "documents.highlight.extract",
        ):
            expected.extend(
                [
                    "document_opened",
                    "pdf_open",
                    "pdf_page_change",
                    "document_scanned",
                    "pdf_scan_region",
                    "highlights_detected",
                    "pdf_evidence_linked",
                ]
            )
        if step.tool_id in ("email.draft", "gmail.draft"):
            expected.extend(
                [
                    "email_draft_create",
                    "email_set_to",
                    "email_set_subject",
                    "email_set_body",
                    "email_ready_to_send",
                ]
            )
        if step.tool_id in ("email.send", "gmail.send"):
            expected.append("email_sent")
        if step.tool_id in (
            "docs.create",
            "workspace.docs.fill_template",
            "workspace.docs.research_notes",
            "workspace.sheets.track_step",
        ):
            expected.extend(["doc_open", "doc_locate_anchor", "doc_insert_text", "doc_save"])
        if step.tool_id in ("workspace.docs.fill_template", "workspace.docs.research_notes"):
            expected.extend(
                [
                    "docs.create_started",
                    "docs.create_completed",
                    "docs.insert_started",
                    "docs.insert_completed",
                    "drive.go_to_doc",
                ]
            )
        if step.tool_id in ("workspace.sheets.track_step", "workspace.sheets.append"):
            expected.extend(
                [
                    "sheets.create_started",
                    "sheets.create_completed",
                    "sheets.append_started",
                    "sheets.append_completed",
                    "drive.go_to_sheet",
                ]
            )
    if has_web_steps:
        expected.extend(["web_kpi_summary", "web_evidence_summary", "web_release_gate"])
    return list(dict.fromkeys(expected))


def build_execution_prompt(
    *,
    request: ChatRequest,
    settings: dict[str, Any],
) -> str:
    base = " ".join(str(request.message or "").split()).strip()
    context_summary = " ".join(str(settings.get("__conversation_summary") or "").split()).strip()
    working_context_preview = " ".join(str(settings.get("__working_context_preview") or "").split()).strip()
    snippets = (
        [str(item).strip() for item in (settings.get("__conversation_snippets") or []) if str(item).strip()]
        if isinstance(settings.get("__conversation_snippets"), list)
        else []
    )
    session_snippets = (
        [str(item).strip() for item in (settings.get("__session_context_snippets") or []) if str(item).strip()]
        if isinstance(settings.get("__session_context_snippets"), list)
        else []
    )
    memory_snippets = (
        [str(item).strip() for item in (settings.get("__memory_context_snippets") or []) if str(item).strip()]
        if isinstance(settings.get("__memory_context_snippets"), list)
        else []
    )
    if not context_summary and not working_context_preview and not snippets and not session_snippets and not memory_snippets:
        return base
    lines = [base]
    if working_context_preview:
        lines.append(f"Working context: {working_context_preview}")
    if context_summary:
        lines.append(f"Conversation context: {context_summary}")
    if snippets:
        lines.append("Recent snippets:")
        lines.extend(f"- {snippet}" for snippet in snippets[-6:])
    if session_snippets:
        lines.append("Recent session memory:")
        lines.extend(f"- {snippet}" for snippet in session_snippets[:4])
    if memory_snippets:
        lines.append("Relevant past memory:")
        lines.extend(f"- {snippet}" for snippet in memory_snippets[:4])
    return "\n".join(lines).strip()[:2400]


def build_scoped_execution_prompt(
    *,
    base_prompt: str,
    owner_role: str,
    scoped_working_context: dict[str, Any],
) -> str:
    preview = " ".join(str(scoped_working_context.get("preview") or "").split()).strip()
    obligations = scoped_working_context.get("verification_obligations")
    obligation_rows = (
        [str(item).strip() for item in obligations if str(item).strip()][:4]
        if isinstance(obligations, list)
        else []
    )
    lines = [base_prompt, f"Active role: {owner_role}"]
    if preview:
        lines.append(f"Role-scoped context: {preview}")
    if obligation_rows:
        lines.append("Role verification obligations:")
        lines.extend(f"- {row}" for row in obligation_rows)
    return "\n".join(lines).strip()[:2400]


def build_execution_context_settings(
    *,
    request: ChatRequest,
    settings: dict[str, Any],
    run_id: str,
    user_id: str,
    plan_prep: Any,
    task_prep: Any,
    role_dispatch_plan: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        **settings,
        # Reset run-local artifacts to prevent stale carry-over between turns/runs.
        "__latest_report_title": "",
        "__latest_report_content": "",
        "__latest_report_sources": [],
        "__latest_web_sources": [],
        "__latest_web_query": "",
        "__latest_web_provider": "",
        "__latest_web_source_count": 0,
        "__latest_web_source_target": 0,
        "__latest_web_domain_scope_hosts": [],
        "__latest_web_domain_scope_mode": "",
        "__latest_web_domain_scope_filtered_out": 0,
        "__latest_analytics_report": {},
        "__latest_analytics_full_report": {},
        "__web_kpi": {},
        "__web_evidence": {"items": []},
        "__agent_user_id": user_id,
        "__agent_run_id": run_id,
        "__selected_file_ids": selected_file_ids(request),
        "__selected_index_id": selected_index_id(request),
        "__research_search_terms": plan_prep.planned_search_terms[:20],
        "__research_keywords": plan_prep.planned_keywords[:16],
        "__highlight_color": plan_prep.highlight_color,
        "__role_owned_steps": plan_prep.role_owned_steps[:40],
        "__role_dispatch_plan": role_dispatch_plan[:40],
        "__copied_highlights": [],
        "__user_preferences": task_prep.user_preferences,
        "__research_depth_profile": task_prep.research_depth_profile,
        "__task_preferred_tone": task_prep.task_intelligence.preferred_tone,
        "__task_preferred_format": task_prep.task_intelligence.preferred_format,
        "__intent_tags": list(task_prep.task_intelligence.intent_tags),
        "__task_target_url": str(task_prep.task_intelligence.target_url or "").strip(),
        "__task_rewrite_detail": task_prep.rewritten_task,
        "__task_rewrite_deliverables": task_prep.planned_deliverables,
        "__task_rewrite_constraints": task_prep.planned_constraints,
        "__task_contract": task_prep.task_contract,
        "__task_contract_check": {},
        "__task_contract_success_checks": task_prep.contract_success_checks[:8],
        "__task_clarification_missing": task_prep.contract_missing_requirements[:6],
        "__task_clarification_questions": task_prep.clarification_questions[:6],
        "__task_clarification_slots": task_prep.contract_missing_slots[:8],
        "__clarification_blocked": task_prep.clarification_blocked,
        "__conversation_summary": str(settings.get("__conversation_summary") or "").strip()[:480],
        "__conversation_snippets": (
            [str(item).strip() for item in (settings.get("__conversation_snippets") or []) if str(item).strip()][
                :8
            ]
            if isinstance(settings.get("__conversation_snippets"), list)
            else []
        ),
        "__session_context_snippets": list(task_prep.session_context_snippets[:6]),
        "__memory_context_snippets": list(task_prep.memory_context_snippets[:6]),
        "__working_context": task_prep.working_context,
        "__working_context_preview": " ".join(
            str(task_prep.working_context.get("preview") or "").split()
        ).strip()[:480],
    }


def build_run_tool_live(
    *,
    stream: Any,
    registry: Any,
    state: Any,
    access_context: Any,
    activity_event_factory: Callable[..., AgentActivityEvent],
    scoped_prompt_builder: Callable[[str, str, dict[str, Any]], str],
) -> Callable[..., Generator[dict[str, Any], None, Any]]:
    def run_tool_live(
        *,
        step: PlannedStep,
        step_index: int,
        prompt: str,
        params: dict[str, Any],
    ) -> Generator[dict[str, Any], None, Any]:
        owner_role = resolve_owner_role_for_tool(step.tool_id)
        working_context_raw = state.execution_context.settings.get("__working_context")
        working_context = working_context_raw if isinstance(working_context_raw, dict) else {}
        scoped_context = scoped_working_context_for_role(
            working_context=working_context,
            role=owner_role,
        )
        scoped_prompt = scoped_prompt_builder(prompt, owner_role, scoped_context)
        scoped_params = {
            **dict(params or {}),
            "__owner_role": owner_role,
            "__working_context_scoped": scoped_context,
        }
        return (yield from stream.run_tool_live(
            registry=registry,
            step=step,
            step_index=step_index,
            execution_context=state.execution_context,
            access_context=access_context,
            prompt=scoped_prompt,
            params=scoped_params,
            activity_event_factory=activity_event_factory,
        ))

    return run_tool_live


def emit_checkpoint_with_persistence(
    *,
    emit_event: Callable[[AgentActivityEvent], dict[str, Any]],
    activity_event_factory: Callable[..., AgentActivityEvent],
    session_store: Any,
    run_id: str,
    user_id: str,
    tenant_id: str,
    conversation_id: str,
    request: ChatRequest,
    checkpoint: dict[str, Any],
    title: str,
    detail: str,
    stage: str,
    status: str,
    settings: dict[str, Any],
    state: Any | None = None,
    pending_steps: list[Any] | None = None,
    resume_status: str = "in_progress",
) -> Generator[dict[str, Any], None, None]:
    yield emit_event(
        activity_event_factory(
            event_type="execution_checkpoint",
            title=title,
            detail=detail,
            metadata=checkpoint,
            stage=stage,
            status=status,
        )
    )
    persist_run_checkpoint(
        session_store=session_store,
        run_id=run_id,
        user_id=user_id,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        request=request,
        checkpoint=checkpoint,
        settings=settings,
        state=state,
        pending_steps=pending_steps or [],
        resume_status=resume_status,
    )
