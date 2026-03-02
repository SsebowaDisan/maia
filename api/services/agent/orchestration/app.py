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
from api.services.agent.policy import ACCESS_MODE_FULL, build_access_context
from api.services.agent.tools.base import ToolExecutionContext
from api.services.agent.tools.registry import get_tool_registry

from .delivery import maybe_send_server_delivery
from .finalization import finalize_run
from .models import ExecutionState
from .step_execution import execute_planned_steps
from .step_planner import build_execution_steps
from .stream_bridge import LiveRunStream
from .task_preparation import prepare_task_context
from .text_helpers import compact


class AgentOrchestrator:
    def __init__(self) -> None:
        self.registry = get_tool_registry()
        self.activity_store = get_activity_store()
        self.audit = get_audit_logger()
        self.memory = get_memory_service()
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
        has_docs = any(
            token in request.message.lower() for token in ("pdf", "document", "file", "page")
        )
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
                        "browser_contact_fill_name",
                        "browser_contact_fill_email",
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
        snippets_raw = settings.get("__conversation_snippets")
        snippets = (
            [str(item).strip() for item in snippets_raw if str(item).strip()]
            if isinstance(snippets_raw, list)
            else []
        )
        memory_raw = settings.get("__memory_context_snippets")
        memory_snippets = (
            [str(item).strip() for item in memory_raw if str(item).strip()]
            if isinstance(memory_raw, list)
            else []
        )
        if not context_summary and not snippets and not memory_snippets:
            return base
        lines = [base]
        if context_summary:
            lines.append(f"Conversation context: {context_summary}")
        if snippets:
            lines.append("Recent snippets:")
            lines.extend(f"- {snippet}" for snippet in snippets[-6:])
        if memory_snippets:
            lines.append("Relevant past memory:")
            lines.extend(f"- {snippet}" for snippet in memory_snippets[:4])
        prompt = "\n".join(lines).strip()
        return prompt[:2400]

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
            plan_prep = yield from build_execution_steps(
                request=request,
                settings=settings,
                task_prep=task_prep,
                registry=self.registry,
                emit_event=stream.emit,
                activity_event_factory=activity_event_factory,
            )
            desktop_ready_event = activity_event_factory(
                event_type="desktop_ready",
                title="Agent desktop is ready",
                detail="Workspace initialized. Executing plan in live mode.",
                metadata={"steps": len(plan_prep.steps)},
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
                    "__research_search_terms": plan_prep.planned_search_terms[:6],
                    "__research_keywords": plan_prep.planned_keywords[:16],
                    "__highlight_color": plan_prep.highlight_color,
                    "__copied_highlights": [],
                    "__user_preferences": task_prep.user_preferences,
                    "__task_preferred_tone": task_prep.task_intelligence.preferred_tone,
                    "__task_preferred_format": task_prep.task_intelligence.preferred_format,
                    "__intent_tags": list(task_prep.task_intelligence.intent_tags),
                    "__task_rewrite_detail": task_prep.rewritten_task,
                    "__task_rewrite_deliverables": task_prep.planned_deliverables,
                    "__task_rewrite_constraints": task_prep.planned_constraints,
                    "__task_contract": task_prep.task_contract,
                    "__task_contract_check": {},
                    "__task_contract_success_checks": task_prep.contract_success_checks[:8],
                    "__task_clarification_missing": task_prep.contract_missing_requirements[:6],
                    "__task_clarification_questions": task_prep.clarification_questions[:6],
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
                    "__memory_context_snippets": list(task_prep.memory_context_snippets[:6]),
                },
            )
            state = ExecutionState(
                execution_context=execution_context,
                deep_workspace_logging_enabled=plan_prep.deep_workspace_logging_enabled,
            )
            steps = list(plan_prep.steps)
            if task_prep.clarification_blocked and steps:
                clarification_block_event = activity_event_factory(
                    event_type="policy_blocked",
                    title="Execution paused for clarification",
                    detail=compact("; ".join(task_prep.contract_missing_requirements[:4]), 200),
                    metadata={
                        "missing_requirements": task_prep.contract_missing_requirements[:6],
                        "questions": task_prep.clarification_questions[:6],
                    },
                )
                yield stream.emit(clarification_block_event)
                state.next_steps.extend(task_prep.clarification_questions[:6])
                steps = []
            execution_prompt = self._build_execution_prompt(request=request, settings=settings)

            def run_tool_live(
                *,
                step: PlannedStep,
                step_index: int,
                prompt: str,
                params: dict[str, Any],
            ) -> Generator[dict[str, Any], None, Any]:
                return (yield from stream.run_tool_live(
                    registry=self.registry,
                    step=step,
                    step_index=step_index,
                    execution_context=state.execution_context,
                    access_context=access_context,
                    prompt=prompt,
                    params=params,
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
            yield from maybe_send_server_delivery(
                run_id=run_id,
                request=request,
                task_prep=task_prep,
                state=state,
                emit_event=stream.emit,
                activity_event_factory=activity_event_factory,
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
                emit_event=stream.emit,
                activity_event_factory=activity_event_factory,
                expected_event_types_resolver=self._expected_event_types,
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
