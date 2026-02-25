from __future__ import annotations

import html
import time
from typing import Any, Generator

from api.schemas import ChatRequest
from api.services.agent.activity import get_activity_store
from api.services.agent.audit import get_audit_logger
from api.services.agent.events import CORE_EVENT_TYPES, RunEventEmitter, coverage_report
from api.services.agent.live_events import get_live_event_broker
from api.services.agent.memory import get_memory_service
from api.services.agent.models import (
    AgentActivityEvent,
    AgentAction,
    AgentRunResult,
    AgentSource,
    utc_now,
)
from api.services.agent.planner import (
    PlannedStep,
    build_browser_followup_steps,
    build_plan,
    is_deep_research_request,
)
from api.services.agent.policy import (
    ACCESS_MODE_FULL,
    build_access_context,
)
from api.services.agent.tools.base import (
    ToolExecutionContext,
    ToolTraceEvent,
)
from api.services.agent.tools.registry import get_tool_registry


def _compact(text: str, max_len: int = 140) -> str:
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= max_len else f"{clean[: max_len - 1].rstrip()}..."


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

        for step in steps:
            expected.append("tool_started")
            expected.append("tool_completed")
            if step.tool_id in ("marketing.web_research", "browser.playwright.inspect"):
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
            if has_docs and step.tool_id in (
                "report.generate",
                "data.dataset.analyze",
                "invoice.create",
                "docs.create",
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
                expected.extend(
                    [
                        "doc_open",
                        "doc_locate_anchor",
                        "doc_insert_text",
                        "doc_save",
                    ]
                )
        return list(dict.fromkeys(expected))

    def _step_scene_events(
        self,
        *,
        run_id: str,
        step: PlannedStep,
        request: ChatRequest,
        step_index: int,
    ) -> list[AgentActivityEvent]:
        events: list[AgentActivityEvent] = []
        lower_message = request.message.lower()
        selected_file_ids = self._selected_file_ids(request)
        primary_file_id = selected_file_ids[0] if selected_file_ids else ""
        action_meta = {
            "tool_id": step.tool_id,
            "file_id": primary_file_id,
            "file_count": len(selected_file_ids),
        }

        if step.tool_id in ("marketing.web_research", "browser.playwright.inspect"):
            query = str(step.params.get("query") or request.message).strip()
            web_meta = {
                "tool_id": step.tool_id,
                "query": query,
                "file_id": primary_file_id,
                "file_count": len(selected_file_ids),
            }
            events.append(
                self._activity_event(
                    run_id=run_id,
                    event_type="web_search_started",
                    title=f"Step {step_index}: Search the web",
                    detail=_compact(query, 180),
                    metadata=web_meta,
                )
            )
            events.append(
                self._activity_event(
                    run_id=run_id,
                    event_type="browser_open",
                    title=f"Step {step_index}: Start browser session",
                    detail="Launching sandboxed browser for research",
                    metadata=web_meta,
                )
            )
            events.append(
                self._activity_event(
                    run_id=run_id,
                    event_type="browser_navigate",
                    title=f"Step {step_index}: Navigate to sources",
                    detail="Opening top-ranked results",
                    metadata=web_meta,
                )
            )
            events.append(
                self._activity_event(
                    run_id=run_id,
                    event_type="browser_scroll",
                    title=f"Step {step_index}: Scroll and inspect",
                    detail="Reading sections for key claims and metrics",
                    metadata=web_meta,
                )
            )
            events.append(
                self._activity_event(
                    run_id=run_id,
                    event_type="web_result_opened",
                    title=f"Step {step_index}: Open top sources",
                    detail="Collecting source snippets and relevance signals",
                    metadata=web_meta,
                )
            )
            events.append(
                self._activity_event(
                    run_id=run_id,
                    event_type="browser_extract",
                    title=f"Step {step_index}: Extract web evidence",
                    detail="Saving excerpts for grounded synthesis",
                    metadata=web_meta,
                )
            )

        references_documents = step.tool_id == "docs.create" or any(
            token in lower_message for token in ("pdf", "document", "file", "page")
        )
        if references_documents and step.tool_id in (
            "report.generate",
            "data.dataset.analyze",
            "invoice.create",
            "docs.create",
        ):
            doc_meta = {
                "tool_id": step.tool_id,
                "file_id": primary_file_id,
                "file_count": len(selected_file_ids),
            }
            events.append(
                self._activity_event(
                    run_id=run_id,
                    event_type="document_opened",
                    title=f"Step {step_index}: Open indexed files",
                    detail="Preparing file context from uploaded and indexed sources",
                    metadata=doc_meta,
                )
            )
            events.append(
                self._activity_event(
                    run_id=run_id,
                    event_type="pdf_open",
                    title=f"Step {step_index}: Open PDF preview",
                    detail="Rendering source document in agent desktop",
                    metadata=doc_meta,
                )
            )
            events.append(
                self._activity_event(
                    run_id=run_id,
                    event_type="pdf_page_change",
                    title=f"Step {step_index}: Navigate PDF pages",
                    detail="Jumping to the most relevant pages",
                    metadata=doc_meta,
                )
            )
            events.append(
                self._activity_event(
                    run_id=run_id,
                    event_type="document_scanned",
                    title=f"Step {step_index}: Scan sections",
                    detail="Reviewing sections, tables, and extracted text",
                    metadata=doc_meta,
                )
            )
            events.append(
                self._activity_event(
                    run_id=run_id,
                    event_type="pdf_scan_region",
                    title=f"Step {step_index}: Scan target regions",
                    detail="Reading key regions, formulas, and diagrams",
                    metadata=doc_meta,
                )
            )
            events.append(
                self._activity_event(
                    run_id=run_id,
                    event_type="highlights_detected",
                    title=f"Step {step_index}: Mark evidence",
                    detail="Identifying the most relevant excerpts for answer grounding",
                    metadata=doc_meta,
                )
            )
            events.append(
                self._activity_event(
                    run_id=run_id,
                    event_type="pdf_evidence_linked",
                    title=f"Step {step_index}: Link evidence to claims",
                    detail="Binding evidence snippets to upcoming response claims",
                    metadata=doc_meta,
                )
            )

        if step.tool_id in ("email.draft", "gmail.draft", "email.send", "gmail.send", "slack.post_message"):
            if step.tool_id.startswith("gmail."):
                events.extend(
                    [
                        self._activity_event(
                            run_id=run_id,
                            event_type="browser_open",
                            title=f"Step {step_index}: Open secure browser",
                            detail="Launching browser workspace for Gmail task",
                            metadata=action_meta,
                        ),
                        self._activity_event(
                            run_id=run_id,
                            event_type="browser_navigate",
                            title=f"Step {step_index}: Search and open Gmail",
                            detail="Opening search engine, then navigating to Gmail compose view",
                            metadata=action_meta,
                        ),
                    ]
                )
            events.append(
                self._activity_event(
                    run_id=run_id,
                    event_type="action_prepared",
                    title=f"Step {step_index}: Prepare action payload",
                    detail=f"Validating parameters for {step.tool_id}",
                    metadata=action_meta,
                )
            )
        if step.tool_id in ("email.draft", "gmail.draft"):
            events.extend(
                [
                    self._activity_event(
                        run_id=run_id,
                        event_type="email_draft_create",
                        title=f"Step {step_index}: Start email draft",
                        detail="Opening composer with draft template",
                        metadata=action_meta,
                    ),
                    self._activity_event(
                        run_id=run_id,
                        event_type="email_set_to",
                        title=f"Step {step_index}: Apply recipients",
                        detail="Setting recipient list",
                        metadata=action_meta,
                    ),
                    self._activity_event(
                        run_id=run_id,
                        event_type="email_set_subject",
                        title=f"Step {step_index}: Draft subject",
                        detail="Generating concise subject line",
                        metadata=action_meta,
                    ),
                    self._activity_event(
                        run_id=run_id,
                        event_type="email_set_body",
                        title=f"Step {step_index}: Draft body",
                        detail="Writing structured business message",
                        metadata=action_meta,
                    ),
                    self._activity_event(
                        run_id=run_id,
                        event_type="email_ready_to_send",
                        title=f"Step {step_index}: Draft ready",
                        detail="Email is ready for send policy check",
                        metadata=action_meta,
                    ),
                ]
            )
        if step.tool_id in ("email.send", "gmail.send"):
            events.append(
                self._activity_event(
                    run_id=run_id,
                    event_type="email_ready_to_send",
                    title=f"Step {step_index}: Confirm send action",
                    detail="Final validation before dispatch",
                    metadata=action_meta,
                )
            )
            events.append(
                self._activity_event(
                    run_id=run_id,
                    event_type="email_sent",
                    title=f"Step {step_index}: Email dispatched",
                    detail="Send action completed by configured connector",
                    metadata=action_meta,
                )
            )
        return events

    def run_stream(
        self,
        *,
        user_id: str,
        conversation_id: str,
        request: ChatRequest,
        settings: dict[str, Any],
    ) -> Generator[dict[str, Any], None, AgentRunResult]:
        access_context = build_access_context(user_id=user_id, settings=settings)
        if request.access_mode is not None:
            access_context = access_context.__class__(
                role=access_context.role,
                access_mode=request.access_mode,
                full_access_enabled=access_context.full_access_enabled,
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

        def _stream_event(event: AgentActivityEvent) -> dict[str, Any]:
            observed_event_types.append(event.event_type)
            self.activity_store.append(event)
            get_live_event_broker().publish(
                user_id=user_id,
                run_id=run_id,
                event={
                    "type": event.event_type,
                    "message": event.title,
                    "data": event.data,
                    "run_id": run_id,
                    "event_id": event.event_id,
                    "seq": event.seq,
                },
            )
            return {"type": "activity", "event": event.to_dict()}

        def _trace_payload(trace: ToolTraceEvent | Any) -> dict[str, Any] | None:
            if isinstance(trace, ToolTraceEvent):
                return trace.to_dict()
            if hasattr(trace, "to_dict"):
                raw = trace.to_dict()
                return raw if isinstance(raw, dict) else None
            return dict(trace) if isinstance(trace, dict) else None

        def _stream_traces(
            *,
            step: PlannedStep,
            step_index: int,
            traces: list[ToolTraceEvent] | list[Any],
        ) -> Generator[dict[str, Any], None, None]:
            for trace in list(traces or []):
                payload = _trace_payload(trace)
                if not isinstance(payload, dict):
                    continue
                trace_event_type = str(payload.get("event_type") or "tool_progress").strip()
                trace_title = str(payload.get("title") or step.title).strip() or step.title
                trace_detail = str(payload.get("detail") or "").strip()
                trace_data = payload.get("data")
                trace_data_dict = dict(trace_data) if isinstance(trace_data, dict) else {}
                trace_snapshot = payload.get("snapshot_ref")
                trace_event = self._activity_event(
                    run_id=run_id,
                    event_type=trace_event_type,
                    title=trace_title,
                    detail=trace_detail,
                    metadata={
                        **trace_data_dict,
                        "tool_id": step.tool_id,
                        "step": step_index,
                    },
                    snapshot_ref=str(trace_snapshot) if trace_snapshot else None,
                )
                yield _stream_event(trace_event)

        def _run_tool_live(
            *,
            step: PlannedStep,
            step_index: int,
            prompt: str,
            params: dict[str, Any],
        ) -> Generator[dict[str, Any], None, Any]:
            execution_stream = self.registry.execute_with_trace(
                tool_id=step.tool_id,
                context=execution_context,
                access=access_context,
                prompt=prompt,
                params=params,
            )
            while True:
                try:
                    trace = next(execution_stream)
                except StopIteration as stop:
                    return stop.value
                for trace_event in _stream_traces(
                    step=step,
                    step_index=step_index,
                    traces=[trace],
                ):
                    yield trace_event

        desktop_start_event = self._activity_event(
            run_id=run_id,
            event_type="desktop_starting",
            title="Starting secure agent desktop",
            detail="Booting isolated workspace and loading connected tools",
            metadata={"conversation_id": conversation_id},
        )
        yield _stream_event(desktop_start_event)

        started_event = self._activity_event(
            run_id=run_id,
            event_type="planning_started",
            title="Planning agent workflow",
            detail=_compact(request.message, 220),
            metadata={"conversation_id": conversation_id},
        )
        yield _stream_event(started_event)

        steps = build_plan(request)
        deep_research_mode = is_deep_research_request(request)
        deep_workspace_logging_enabled = deep_research_mode
        deep_workspace_warning_emitted = False
        dynamic_inspection_inserted = False

        plan_candidate_event = self._activity_event(
            run_id=run_id,
            event_type="plan_candidate",
            title="Generated initial execution plan",
            detail=f"Candidate plan has {len(steps)} step(s)",
            metadata={"steps": [step.__dict__ for step in steps]},
        )
        yield _stream_event(plan_candidate_event)
        plan_refined_event = self._activity_event(
            run_id=run_id,
            event_type="plan_refined",
            title="Refined execution order",
            detail="Prioritized sequence for speed and grounding quality",
            metadata={"step_ids": [step.tool_id for step in steps]},
        )
        yield _stream_event(plan_refined_event)
        planned_event = self._activity_event(
            run_id=run_id,
            event_type="plan_ready",
            title=f"Prepared {len(steps)} execution steps",
            metadata={"steps": [step.__dict__ for step in steps]},
        )
        yield _stream_event(planned_event)

        desktop_ready_event = self._activity_event(
            run_id=run_id,
            event_type="desktop_ready",
            title="Agent desktop is ready",
            detail="Workspace initialized. Executing plan in live mode.",
            metadata={"steps": len(steps)},
        )
        yield _stream_event(desktop_ready_event)

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
            },
        )

        all_actions: list[AgentAction] = []
        all_sources: list[AgentSource] = []
        narrative_sections: list[str] = []
        next_steps: list[str] = []

        step_cursor = 0
        display_step_index = 0
        while step_cursor < len(steps):
            step = steps[step_cursor]
            if (
                not deep_workspace_logging_enabled
                and step.tool_id in ("workspace.docs.research_notes", "workspace.sheets.track_step")
            ):
                step_cursor += 1
                continue
            display_step_index += 1
            index = display_step_index
            step_started = utc_now().isoformat()
            queued_event = self._activity_event(
                run_id=run_id,
                event_type="tool_queued",
                title=f"Queued: {step.title}",
                detail=step.tool_id,
                metadata={"tool_id": step.tool_id, "step": index},
            )
            yield _stream_event(queued_event)
            for scene_event in self._step_scene_events(
                run_id=run_id,
                step=step,
                request=request,
                step_index=index,
            ):
                yield _stream_event(scene_event)

            step_event = self._activity_event(
                run_id=run_id,
                event_type="tool_started",
                title=f"Step {index}: {step.title}",
                detail=step.tool_id,
            )
            yield _stream_event(step_event)

            progress_event = self._activity_event(
                run_id=run_id,
                event_type="tool_progress",
                title=f"Step {index}: Running {step.title}",
                detail="Tool execution in progress",
                metadata={"tool_id": step.tool_id, "step": index, "progress": 0.5},
            )
            yield _stream_event(progress_event)

            params = dict(step.params)
            # Full access mode auto-confirms execute operations.
            if access_context.access_mode == ACCESS_MODE_FULL and access_context.full_access_enabled:
                params.setdefault("confirmed", True)

            tool_meta = self.registry.get(step.tool_id).metadata
            if (
                tool_meta.action_class == "execute"
                and tool_meta.execution_policy == "confirm_before_execute"
            ):
                if params.get("confirmed"):
                    granted_event = self._activity_event(
                        run_id=run_id,
                        event_type="approval_granted",
                        title=f"Execution approved: {step.title}",
                        detail="Full access mode auto-approved this execute action",
                        metadata={"tool_id": step.tool_id, "step": index},
                    )
                    yield _stream_event(granted_event)
                else:
                    approval_event = self._activity_event(
                        run_id=run_id,
                        event_type="approval_required",
                        title=f"Approval required: {step.title}",
                        detail="Restricted mode requires explicit confirmation",
                        metadata={"tool_id": step.tool_id, "step": index},
                    )
                    yield _stream_event(approval_event)

            try:
                result = yield from _run_tool_live(
                    step=step,
                    step_index=index,
                    prompt=request.message,
                    params=params,
                )
                action = self.registry.get(step.tool_id).to_action(
                    status="success",
                    summary=result.summary,
                    started_at=step_started,
                    metadata={"step": index},
                )
                all_actions.append(action)
                all_sources.extend(result.sources)
                narrative_sections.append(
                    f"### {index}. {step.title}\n{result.content.strip()}"
                )
                next_steps.extend(result.next_steps)
                completed_event = self._activity_event(
                    run_id=run_id,
                    event_type="tool_completed",
                    title=f"Completed: {step.title}",
                    detail=result.summary,
                    metadata={"tool_id": step.tool_id, "step": index},
                )
                yield _stream_event(completed_event)

                if step.tool_id == "marketing.web_research" and not dynamic_inspection_inserted:
                    followup_steps = build_browser_followup_steps(
                        result.data,
                        max_urls=4 if deep_research_mode else 2,
                    )
                    if followup_steps:
                        insertion_point = step_cursor + 1
                        steps[insertion_point:insertion_point] = followup_steps
                        dynamic_inspection_inserted = True
                        refined_event = self._activity_event(
                            run_id=run_id,
                            event_type="plan_refined",
                            title="Expanded research plan with live source inspections",
                            detail=f"Inserted {len(followup_steps)} website inspection step(s)",
                            metadata={
                                "inserted": len(followup_steps),
                                "total_steps": len(steps),
                                "step_ids": [item.tool_id for item in steps],
                            },
                        )
                        yield _stream_event(refined_event)

                if deep_workspace_logging_enabled and step.tool_id not in (
                    "workspace.docs.research_notes",
                    "workspace.sheets.track_step",
                ):
                    keyword_rows = result.data.get("keywords") if isinstance(result.data, dict) else None
                    keywords = (
                        [str(item).strip() for item in keyword_rows if str(item).strip()]
                        if isinstance(keyword_rows, list)
                        else []
                    )
                    keyword_line = f"Keywords: {', '.join(keywords[:12])}" if keywords else ""
                    compact_content = _compact(result.content, 560)
                    note_body = "\n".join(
                        part
                        for part in [
                            f"Step {index}: {step.title}",
                            f"Summary: {result.summary}",
                            keyword_line,
                            compact_content,
                        ]
                        if part
                    )
                    log_steps = [
                        PlannedStep(
                            tool_id="workspace.sheets.track_step",
                            title=f"Track completion: {step.title}",
                            params={
                                "step_name": step.title,
                                "status": "completed",
                                "detail": result.summary,
                                "source_url": (result.sources[0].url if result.sources else ""),
                            },
                        ),
                        PlannedStep(
                            tool_id="workspace.docs.research_notes",
                            title=f"Log findings: {step.title}",
                            params={"note": note_body},
                        ),
                    ]
                    for shadow_step in log_steps:
                        shadow_started_at = utc_now().isoformat()
                        shadow_params = dict(shadow_step.params)
                        if access_context.access_mode == ACCESS_MODE_FULL and access_context.full_access_enabled:
                            shadow_params.setdefault("confirmed", True)
                        try:
                            shadow_result = yield from _run_tool_live(
                                step=shadow_step,
                                step_index=index,
                                prompt=request.message,
                                params=shadow_params,
                            )
                            shadow_action = self.registry.get(shadow_step.tool_id).to_action(
                                status="success",
                                summary=shadow_result.summary,
                                started_at=shadow_started_at,
                                metadata={"step": index, "shadow": True},
                            )
                            all_actions.append(shadow_action)
                            all_sources.extend(shadow_result.sources)
                            shadow_completed = self._activity_event(
                                run_id=run_id,
                                event_type="tool_completed",
                                title=f"Completed: {shadow_step.title}",
                                detail=shadow_result.summary,
                                metadata={"tool_id": shadow_step.tool_id, "step": index, "shadow": True},
                            )
                            yield _stream_event(shadow_completed)
                        except Exception as shadow_exc:
                            if any(
                                marker in str(shadow_exc).lower()
                                for marker in ("google_tokens_missing", "oauth", "refresh_token")
                            ):
                                deep_workspace_logging_enabled = False
                                if not deep_workspace_warning_emitted:
                                    deep_workspace_warning_emitted = True
                                    warning_event = self._activity_event(
                                        run_id=run_id,
                                        event_type="tool_failed",
                                        title="Workspace logging disabled",
                                        detail=(
                                            "Google Docs/Sheets is not connected. "
                                            "Continuing deep research without external notebook sync."
                                        ),
                                        metadata={"tool_id": shadow_step.tool_id, "step": index, "shadow": True},
                                    )
                                    yield _stream_event(warning_event)
                            shadow_failed = self._activity_event(
                                run_id=run_id,
                                event_type="tool_failed",
                                title=f"Failed: {shadow_step.title}",
                                detail=str(shadow_exc),
                                metadata={"tool_id": shadow_step.tool_id, "step": index, "shadow": True},
                            )
                            yield _stream_event(shadow_failed)
            except Exception as exc:
                if (
                    step.tool_id in ("workspace.docs.research_notes", "workspace.sheets.track_step")
                    and any(marker in str(exc).lower() for marker in ("google_tokens_missing", "oauth", "refresh_token"))
                ):
                    deep_workspace_logging_enabled = False
                action = self.registry.get(step.tool_id).to_action(
                    status="failed",
                    summary=str(exc),
                    started_at=step_started,
                    metadata={"step": index},
                )
                all_actions.append(action)
                exc_text = str(exc)
                if "requires confirmation" in exc_text.lower():
                    approval_event = self._activity_event(
                        run_id=run_id,
                        event_type="approval_required",
                        title=f"Approval required: {step.title}",
                        detail=exc_text,
                        metadata={"tool_id": step.tool_id, "step": index},
                    )
                    yield _stream_event(approval_event)
                    policy_event = self._activity_event(
                        run_id=run_id,
                        event_type="policy_blocked",
                        title=f"Policy blocked: {step.title}",
                        detail="Execution blocked in restricted mode until confirmation",
                        metadata={"tool_id": step.tool_id, "step": index},
                    )
                    yield _stream_event(policy_event)
                fail_event = self._activity_event(
                    run_id=run_id,
                    event_type="tool_failed",
                    title=f"Failed: {step.title}",
                    detail=exc_text,
                    metadata={"tool_id": step.tool_id, "step": index},
                )
                yield _stream_event(fail_event)
            step_cursor += 1

        if not narrative_sections:
            narrative_sections.append(
                "### Result\nNo tool was executed successfully. Check configuration and retry."
            )

        unique_next_steps: list[str] = []
        for step in next_steps:
            if step not in unique_next_steps:
                unique_next_steps.append(step)

        if deep_research_mode:
            minimum_seconds_raw = settings.get("agent.deep_research_min_seconds", 30)
            try:
                minimum_seconds = max(30.0, float(minimum_seconds_raw))
            except Exception:
                minimum_seconds = 30.0
            elapsed_seconds = time.perf_counter() - run_started_clock
            remaining_seconds = minimum_seconds - elapsed_seconds
            if remaining_seconds > 0.4:
                waited = 0.0
                wait_started_event = self._activity_event(
                    run_id=run_id,
                    event_type="tool_progress",
                    title="Running deep research cross-checks",
                    detail="Verifying evidence consistency before final synthesis",
                    metadata={"step": len(steps), "progress": 0.0},
                )
                yield _stream_event(wait_started_event)
                while waited < remaining_seconds:
                    chunk = min(2.0, remaining_seconds - waited)
                    time.sleep(chunk)
                    waited += chunk
                    progress = min(1.0, waited / remaining_seconds) if remaining_seconds > 0 else 1.0
                    wait_progress_event = self._activity_event(
                        run_id=run_id,
                        event_type="tool_progress",
                        title="Deep research quality pass",
                        detail=f"Cross-check in progress ({int(progress * 100)}%)",
                        metadata={"step": len(steps), "progress": round(progress, 3)},
                    )
                    yield _stream_event(wait_progress_event)

        synthesis_started_event = self._activity_event(
            run_id=run_id,
            event_type="synthesis_started",
            title="Synthesizing final response",
            detail="Combining tool outputs into one structured answer",
        )
        yield _stream_event(synthesis_started_event)

        answer = "\n\n".join(narrative_sections)
        failed_actions = [action for action in all_actions if action.status == "failed"]
        if failed_actions:
            answer += "\n\n### Execution issues\n" + "\n".join(
                f"- {item.tool_id}: {_compact(item.summary, 180)}" for item in failed_actions[:6]
            )
        if unique_next_steps:
            answer += "\n\n### Recommended next steps\n" + "\n".join(
                f"- {item}" for item in unique_next_steps[:6]
            )

        info_blocks: list[str] = []
        for idx, source in enumerate(all_sources, start=1):
            label = html.escape(source.label)
            url = html.escape(source.url or "")
            detail = f"<a href='{url}' target='_blank' rel='noopener noreferrer'>{url}</a>" if url else "Internal source"
            info_blocks.append(
                (
                    f"<details class='evidence' id='evidence-{idx}' {'open' if idx == 1 else ''}>"
                    f"<summary><i>Evidence [{idx}]</i></summary>"
                    f"<div><b>Source:</b> [{idx}] {label}</div>"
                    f"<div class='evidence-content'><b>Link:</b> {detail}</div>"
                    "</details>"
                )
            )
        info_html = "".join(info_blocks)

        result = AgentRunResult(
            run_id=run_id,
            answer=answer,
            info_html=info_html,
            actions_taken=all_actions,
            sources_used=all_sources,
            next_recommended_steps=unique_next_steps[:8],
        )
        synthesis_completed_event = self._activity_event(
            run_id=run_id,
            event_type="synthesis_completed",
            title="Final response ready",
            detail=f"Generated {len(all_actions)} action result(s) with {len(all_sources)} source(s)",
        )
        yield _stream_event(synthesis_completed_event)

        expected_events = self._expected_event_types(steps=steps, request=request)
        coverage = coverage_report(
            observed_event_types=observed_event_types,
            expected_event_types=expected_events,
        )
        coverage_event = self._activity_event(
            run_id=run_id,
            event_type="event_coverage",
            title="Generated event coverage report",
            detail=f"{coverage['coverage_percent']}% expected events were emitted",
            metadata=coverage,
            stage="result",
            status="completed",
        )
        yield _stream_event(coverage_event)

        try:
            self.activity_store.end_run(run_id, result.to_dict())
            self.audit.write(
                user_id=user_id,
                tenant_id=access_context.tenant_id,
                run_id=run_id,
                event="agent_run_completed",
                payload={
                    "conversation_id": conversation_id,
                    "steps": len(steps),
                    "actions": len(all_actions),
                    "sources": len(all_sources),
                    "event_coverage_percent": coverage.get("coverage_percent", 0),
                },
            )
            self.memory.save_run(
                {
                    "run_id": run_id,
                    "user_id": user_id,
                    "tenant_id": access_context.tenant_id,
                    "conversation_id": conversation_id,
                    "message": request.message,
                    "agent_goal": request.agent_goal,
                    "answer": result.answer,
                    "actions_taken": [item.to_dict() for item in result.actions_taken],
                    "sources_used": [item.to_dict() for item in result.sources_used],
                    "next_recommended_steps": result.next_recommended_steps,
                    "event_coverage": coverage,
                }
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
