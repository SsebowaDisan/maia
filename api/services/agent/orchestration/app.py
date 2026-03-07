from __future__ import annotations

import time
from typing import Any, Generator

from api.schemas import ChatRequest
from api.services.agent.activity import get_activity_store
from api.services.agent.audit import get_audit_logger
from api.services.agent.events import CORE_EVENT_TYPES, RunEventEmitter
from api.services.agent.memory import get_memory_service
from api.services.agent.models import AgentActivityEvent
from api.services.agent.planner import PlannedStep
from api.services.agent.planner_helpers import intent_signals
from api.services.agent.policy import ACCESS_MODE_FULL, build_access_context
from api.services.agent.tools.base import ToolExecutionContext
from api.services.agent.tools.registry import get_tool_registry

from .delivery import maybe_send_server_delivery
from .execution_checkpoints import append_execution_checkpoint, build_role_dispatch_plan
from .finalization import finalize_run
from .handoff_state import (
    handoff_pause_notice,
    handoff_resume_notice,
    is_handoff_paused,
    maybe_resume_handoff_from_settings,
    read_handoff_state,
)
from .models import ExecutionState
from .role_contracts import resolve_owner_role_for_tool
from .run_checkpoint_persistence import persist_run_checkpoint
from .session_store import get_session_store
from .step_execution import execute_planned_steps
from .step_planner import build_execution_steps
from .stream_bridge import LiveRunStream
from .task_preparation import prepare_task_context
from .text_helpers import compact
from .working_context import scoped_working_context_for_role


class AgentOrchestrator:
    def __init__(self) -> None:
        self.registry = get_tool_registry()
        self.activity_store = get_activity_store()
        self.audit = get_audit_logger()
        self.memory = get_memory_service()
        self.session_store = get_session_store()
        self._emitters: dict[str, RunEventEmitter] = {}

    def _activity_event(
        self,
        *,
        run_id: str,
        event_type: str,
        title: str,
        detail: str = "",
        metadata: dict[str, Any] | None = None,
        stage: str | None = None,
        status: str | None = None,
        snapshot_ref: str | None = None,
    ) -> AgentActivityEvent:
        emitter = self._emitters.get(run_id)
        if emitter is None:
            emitter = RunEventEmitter(run_id=run_id)
            self._emitters[run_id] = emitter
        return emitter.emit(
            event_type=event_type,
            title=title,
            detail=detail,
            metadata=metadata or {},
            stage=stage,
            status=status,
            snapshot_ref=snapshot_ref,
        )

    def _selected_file_ids(self, request: ChatRequest) -> list[str]:
        collected: list[str] = []
        for selection in request.index_selection.values():
            file_ids = getattr(selection, "file_ids", []) or []
            for file_id in file_ids:
                file_id_text = str(file_id).strip()
                if file_id_text:
                    collected.append(file_id_text)
        return list(dict.fromkeys(collected))

    def _selected_index_id(self, request: ChatRequest) -> int | None:
        for raw_index_id in request.index_selection.keys():
            text = str(raw_index_id).strip()
            if not text:
                continue
            if text.isdigit():
                return int(text)
        return None

    def _expected_event_types(
        self,
        *,
        steps: list[PlannedStep],
        request: ChatRequest,
    ) -> list[str]:
        expected: list[str] = list(CORE_EVENT_TYPES)
        inferred_signals = intent_signals(request)
        has_docs = bool(self._selected_file_ids(request)) or bool(inferred_signals.get("wants_file_scope"))
        has_web_steps = False
        for step in steps:
            expected.append("tool_started")
            expected.append("tool_completed")
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

    def _build_execution_prompt(
        self,
        *,
        request: ChatRequest,
        settings: dict[str, Any],
    ) -> str:
        base = " ".join(str(request.message or "").split()).strip()
        context_summary = " ".join(str(settings.get("__conversation_summary") or "").split()).strip()
        working_context_preview = " ".join(
            str(settings.get("__working_context_preview") or "").split()
        ).strip()
        snippets_raw = settings.get("__conversation_snippets")
        snippets = (
            [str(item).strip() for item in snippets_raw if str(item).strip()]
            if isinstance(snippets_raw, list)
            else []
        )
        session_raw = settings.get("__session_context_snippets")
        session_snippets = (
            [str(item).strip() for item in session_raw if str(item).strip()]
            if isinstance(session_raw, list)
            else []
        )
        memory_raw = settings.get("__memory_context_snippets")
        memory_snippets = (
            [str(item).strip() for item in memory_raw if str(item).strip()]
            if isinstance(memory_raw, list)
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
        prompt = "\n".join(lines).strip()
        return prompt[:2400]

    def _build_scoped_execution_prompt(
        self,
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
        lines = [base_prompt]
        lines.append(f"Active role: {owner_role}")
        if preview:
            lines.append(f"Role-scoped context: {preview}")
        if obligation_rows:
            lines.append("Role verification obligations:")
            lines.extend(f"- {row}" for row in obligation_rows)
        return "\n".join(lines).strip()[:2400]

    def run_stream(
        self,
        *,
        user_id: str,
        conversation_id: str,
        request: ChatRequest,
        settings: dict[str, Any],
    ) -> Generator[dict[str, Any], None, Any]:
        access_context = build_access_context(user_id=user_id, settings=settings)
        if request.access_mode is not None:
            request_full_access = request.access_mode == ACCESS_MODE_FULL
            access_context = access_context.__class__(
                role=access_context.role,
                access_mode=request.access_mode,
                full_access_enabled=access_context.full_access_enabled or request_full_access,
                tenant_id=access_context.tenant_id,
            )

        header = self.activity_store.start_run(
            user_id=user_id,
            conversation_id=conversation_id,
            mode=request.agent_mode,
            goal=request.agent_goal or request.message,
        )
        run_id = header.run_id
        self._emitters[run_id] = RunEventEmitter(run_id=run_id)
        observed_event_types: list[str] = []
        run_started_clock = time.perf_counter()
        stream = LiveRunStream(
            activity_store=self.activity_store,
            user_id=user_id,
            run_id=run_id,
            observed_event_types=observed_event_types,
        )

        def activity_event_factory(
            *,
            event_type: str,
            title: str,
            detail: str = "",
            metadata: dict[str, Any] | None = None,
            stage: str | None = None,
            status: str | None = None,
            snapshot_ref: str | None = None,
        ) -> AgentActivityEvent:
            return self._activity_event(
                run_id=run_id,
                event_type=event_type,
                title=title,
                detail=detail,
                metadata=metadata,
                stage=stage,
                status=status,
                snapshot_ref=snapshot_ref,
            )

        try:
            desktop_start_event = activity_event_factory(
                event_type="desktop_starting",
                title="Starting secure agent desktop",
                detail="Booting isolated workspace and loading connected tools",
                metadata={"conversation_id": conversation_id},
            )
            yield stream.emit(desktop_start_event)

            task_prep = yield from prepare_task_context(
                run_id=run_id,
                conversation_id=conversation_id,
                user_id=user_id,
                request=request,
                settings=settings,
                emit_event=stream.emit,
                activity_event_factory=activity_event_factory,
            )
            task_checkpoint = append_execution_checkpoint(
                settings=settings,
                name="task_prepared",
                status="completed",
            )
            yield stream.emit(
                activity_event_factory(
                    event_type="execution_checkpoint",
                    title="Checkpoint: task_prepared",
                    detail="Task context prepared and scoped for planning.",
                    metadata=task_checkpoint,
                    stage="plan",
                    status="completed",
                )
            )
            persist_run_checkpoint(
                session_store=self.session_store,
                run_id=run_id,
                user_id=user_id,
                tenant_id=access_context.tenant_id,
                conversation_id=conversation_id,
                request=request,
                checkpoint=task_checkpoint,
                settings=settings,
                resume_status="in_progress",
            )
            plan_prep = yield from build_execution_steps(
                request=request,
                settings=settings,
                task_prep=task_prep,
                registry=self.registry,
                emit_event=stream.emit,
                activity_event_factory=activity_event_factory,
            )
            steps = list(plan_prep.steps)
            role_dispatch_plan = build_role_dispatch_plan(steps=steps)
            settings["__role_dispatch_plan"] = role_dispatch_plan[:40]
            role_dispatch_event = activity_event_factory(
                event_type="role_dispatch_plan",
                title="Role dispatch plan ready",
                detail=(
                    f"{len(role_dispatch_plan)} role segment(s) scheduled across {len(steps)} step(s)."
                ),
                metadata={
                    "planned_steps": len(steps),
                    "role_dispatch_segments": len(role_dispatch_plan),
                    "role_dispatch_plan": role_dispatch_plan[:20],
                },
                stage="plan",
                status="completed",
            )
            yield stream.emit(role_dispatch_event)
            plan_checkpoint = append_execution_checkpoint(
                settings=settings,
                name="plan_ready",
                status="completed",
                pending_steps=len(steps),
                metadata={
                    "role_dispatch_segments": len(role_dispatch_plan),
                },
            )
            yield stream.emit(
                activity_event_factory(
                    event_type="execution_checkpoint",
                    title="Checkpoint: plan_ready",
                    detail=f"Execution plan prepared with {len(steps)} step(s).",
                    metadata=plan_checkpoint,
                    stage="plan",
                    status="completed",
                )
            )
            persist_run_checkpoint(
                session_store=self.session_store,
                run_id=run_id,
                user_id=user_id,
                tenant_id=access_context.tenant_id,
                conversation_id=conversation_id,
                request=request,
                checkpoint=plan_checkpoint,
                settings=settings,
                pending_steps=steps,
                resume_status="in_progress",
            )
            desktop_ready_event = activity_event_factory(
                event_type="desktop_ready",
                title="Agent desktop is ready",
                detail="Workspace initialized. Executing plan in live mode.",
                metadata={"steps": len(steps)},
            )
            yield stream.emit(desktop_ready_event)

            execution_context = ToolExecutionContext(
                user_id=user_id,
                tenant_id=access_context.tenant_id,
                conversation_id=conversation_id,
                run_id=run_id,
                mode=request.agent_mode,
                settings={
                    **settings,
                    "__agent_user_id": user_id,
                    "__agent_run_id": run_id,
                    "__selected_file_ids": self._selected_file_ids(request),
                    "__selected_index_id": self._selected_index_id(request),
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
                    "__conversation_summary": str(settings.get("__conversation_summary") or "").strip()[
                        :480
                    ],
                    "__conversation_snippets": (
                        [
                            str(item).strip()
                            for item in (settings.get("__conversation_snippets") or [])
                            if str(item).strip()
                        ][:8]
                        if isinstance(settings.get("__conversation_snippets"), list)
                        else []
                    ),
                    "__session_context_snippets": list(task_prep.session_context_snippets[:6]),
                    "__memory_context_snippets": list(task_prep.memory_context_snippets[:6]),
                    "__working_context": task_prep.working_context,
                    "__working_context_preview": " ".join(
                        str(task_prep.working_context.get("preview") or "").split()
                    ).strip()[:480],
                },
            )
            resumed_handoff = maybe_resume_handoff_from_settings(
                settings=execution_context.settings,
            )
            if isinstance(resumed_handoff, dict):
                resume_notice = handoff_resume_notice(resumed_handoff=resumed_handoff)
                resume_event = activity_event_factory(
                    event_type=str(resume_notice.get("event_type") or "handoff_resumed"),
                    title=str(resume_notice.get("title") or "Resumed after human verification"),
                    detail=str(resume_notice.get("detail") or ""),
                    metadata=dict(resume_notice.get("metadata") or {}),
                )
                yield stream.emit(resume_event)
            docs_logging_requested = any(
                step.tool_id in ("workspace.docs.research_notes", "workspace.docs.fill_template", "docs.create")
                for step in steps
            )
            sheets_logging_requested = any(
                step.tool_id in ("workspace.sheets.track_step", "workspace.sheets.append")
                for step in steps
            ) or bool(plan_prep.deep_workspace_logging_enabled)
            state = ExecutionState(
                execution_context=execution_context,
                deep_workspace_logging_enabled=plan_prep.deep_workspace_logging_enabled,
                deep_workspace_docs_logging_enabled=docs_logging_requested,
                deep_workspace_sheets_logging_enabled=sheets_logging_requested,
            )
            if task_prep.clarification_blocked and steps:
                clarification_block_event = activity_event_factory(
                    event_type="policy_blocked",
                    title="Execution paused for clarification",
                    detail=compact("; ".join(task_prep.contract_missing_requirements[:4]), 200),
                    metadata={
                        "missing_requirements": task_prep.contract_missing_requirements[:6],
                        "questions": task_prep.clarification_questions[:6],
                        "missing_requirement_slots": task_prep.contract_missing_slots[:8],
                    },
                )
                yield stream.emit(clarification_block_event)
                state.next_steps.extend(task_prep.clarification_questions[:6])
                steps = []
            if is_handoff_paused(settings=state.execution_context.settings) and steps:
                pause_notice = handoff_pause_notice(settings=state.execution_context.settings)
                pause_event = activity_event_factory(
                    event_type=str(pause_notice.get("event_type") or "handoff_paused"),
                    title=str(pause_notice.get("title") or "Execution paused for human verification"),
                    detail=compact(str(pause_notice.get("detail") or ""), 200),
                    metadata=dict(pause_notice.get("metadata") or {}),
                )
                yield stream.emit(pause_event)
                handoff = read_handoff_state(settings=state.execution_context.settings)
                pause_note = " ".join(str(handoff.get("note") or "").split()).strip()
                if pause_note:
                    state.next_steps.append(pause_note)
                steps = []
            execution_prompt = self._build_execution_prompt(request=request, settings=settings)
            cycle_index = 1
            cycle_started_checkpoint = append_execution_checkpoint(
                settings=state.execution_context.settings,
                name="execution_cycle_started",
                status="in_progress",
                cycle=cycle_index,
                step_cursor=0,
                pending_steps=len(steps),
            )
            yield stream.emit(
                activity_event_factory(
                    event_type="execution_checkpoint",
                    title="Checkpoint: execution_cycle_started",
                    detail=f"Cycle {cycle_index} started with {len(steps)} planned step(s).",
                    metadata=cycle_started_checkpoint,
                    stage="tool",
                    status="in_progress",
                )
            )
            persist_run_checkpoint(
                session_store=self.session_store,
                run_id=run_id,
                user_id=user_id,
                tenant_id=access_context.tenant_id,
                conversation_id=conversation_id,
                request=request,
                checkpoint=cycle_started_checkpoint,
                settings=state.execution_context.settings,
                state=state,
                pending_steps=steps,
                resume_status="in_progress",
            )

            def run_tool_live(
                *,
                step: PlannedStep,
                step_index: int,
                prompt: str,
                params: dict[str, Any],
            ) -> Generator[dict[str, Any], None, Any]:
                owner_role = resolve_owner_role_for_tool(step.tool_id)
                working_context_raw = state.execution_context.settings.get("__working_context")
                working_context = (
                    working_context_raw
                    if isinstance(working_context_raw, dict)
                    else {}
                )
                scoped_context = scoped_working_context_for_role(
                    working_context=working_context,
                    role=owner_role,
                )
                scoped_prompt = self._build_scoped_execution_prompt(
                    base_prompt=prompt,
                    owner_role=owner_role,
                    scoped_working_context=scoped_context,
                )
                scoped_params = {
                    **dict(params or {}),
                    "__owner_role": owner_role,
                    "__working_context_scoped": scoped_context,
                }
                return (yield from stream.run_tool_live(
                    registry=self.registry,
                    step=step,
                    step_index=step_index,
                    execution_context=state.execution_context,
                    access_context=access_context,
                    prompt=scoped_prompt,
                    params=scoped_params,
                    activity_event_factory=activity_event_factory,
                ))

            yield from execute_planned_steps(
                run_id=run_id,
                request=request,
                access_context=access_context,
                registry=self.registry,
                steps=steps,
                execution_prompt=execution_prompt,
                deep_research_mode=plan_prep.deep_research_mode,
                task_prep=task_prep,
                state=state,
                run_tool_live=run_tool_live,
                emit_event=stream.emit,
                activity_event_factory=activity_event_factory,
            )
            active_role = " ".join(
                str(state.execution_context.settings.get("__active_execution_role") or "").split()
            ).strip().lower()
            cycle_completed_checkpoint = append_execution_checkpoint(
                settings=state.execution_context.settings,
                name="execution_cycle_completed",
                status="completed",
                cycle=cycle_index,
                step_cursor=len(state.executed_steps),
                pending_steps=0,
                active_role=active_role,
                metadata={"executed_steps": len(state.executed_steps)},
            )
            yield stream.emit(
                activity_event_factory(
                    event_type="execution_checkpoint",
                    title="Checkpoint: execution_cycle_completed",
                    detail=f"Cycle {cycle_index} completed after {len(state.executed_steps)} executed step(s).",
                    metadata=cycle_completed_checkpoint,
                    stage="tool",
                    status="completed",
                )
            )
            persist_run_checkpoint(
                session_store=self.session_store,
                run_id=run_id,
                user_id=user_id,
                tenant_id=access_context.tenant_id,
                conversation_id=conversation_id,
                request=request,
                checkpoint=cycle_completed_checkpoint,
                settings=state.execution_context.settings,
                state=state,
                pending_steps=[],
                resume_status=(
                    "paused"
                    if is_handoff_paused(settings=state.execution_context.settings)
                    else "in_progress"
                ),
            )
            yield from maybe_send_server_delivery(
                run_id=run_id,
                request=request,
                task_prep=task_prep,
                state=state,
                emit_event=stream.emit,
                activity_event_factory=activity_event_factory,
            )
            finalization_started_checkpoint = append_execution_checkpoint(
                settings=state.execution_context.settings,
                name="finalization_started",
                status="in_progress",
                cycle=cycle_index,
                step_cursor=len(state.executed_steps),
                pending_steps=0,
                active_role=active_role,
            )
            yield stream.emit(
                activity_event_factory(
                    event_type="execution_checkpoint",
                    title="Checkpoint: finalization_started",
                    detail="Final validation and response synthesis started.",
                    metadata=finalization_started_checkpoint,
                    stage="result",
                    status="in_progress",
                )
            )
            persist_run_checkpoint(
                session_store=self.session_store,
                run_id=run_id,
                user_id=user_id,
                tenant_id=access_context.tenant_id,
                conversation_id=conversation_id,
                request=request,
                checkpoint=finalization_started_checkpoint,
                settings=state.execution_context.settings,
                state=state,
                pending_steps=[],
                resume_status="in_progress",
            )
            result = yield from finalize_run(
                run_id=run_id,
                user_id=user_id,
                conversation_id=conversation_id,
                request=request,
                settings=settings,
                access_context=access_context,
                task_prep=task_prep,
                steps=steps,
                deep_research_mode=plan_prep.deep_research_mode,
                run_started_clock=run_started_clock,
                observed_event_types=observed_event_types,
                state=state,
                activity_store=self.activity_store,
                audit=self.audit,
                memory=self.memory,
                session_store=self.session_store,
                emit_event=stream.emit,
                activity_event_factory=activity_event_factory,
                expected_event_types_resolver=self._expected_event_types,
            )
            finalization_completed_checkpoint = append_execution_checkpoint(
                settings=state.execution_context.settings,
                name="finalization_completed",
                status="completed",
                cycle=cycle_index,
                step_cursor=len(state.executed_steps),
                pending_steps=0,
                active_role=active_role,
            )
            yield stream.emit(
                activity_event_factory(
                    event_type="execution_checkpoint",
                    title="Checkpoint: finalization_completed",
                    detail="Finalization completed and run result is ready.",
                    metadata=finalization_completed_checkpoint,
                    stage="result",
                    status="completed",
                )
            )
            persist_run_checkpoint(
                session_store=self.session_store,
                run_id=run_id,
                user_id=user_id,
                tenant_id=access_context.tenant_id,
                conversation_id=conversation_id,
                request=request,
                checkpoint=finalization_completed_checkpoint,
                settings=state.execution_context.settings,
                state=state,
                pending_steps=[],
                resume_status="completed",
            )
            return result
        finally:
            self._emitters.pop(run_id, None)


_orchestrator: AgentOrchestrator | None = None


def get_orchestrator() -> AgentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator
