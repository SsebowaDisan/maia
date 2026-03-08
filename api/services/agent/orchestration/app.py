from __future__ import annotations

import time
from typing import Any, Generator

from api.schemas import ChatRequest
from api.services.agent.activity import get_activity_store
from api.services.agent.audit import get_audit_logger
from api.services.agent.events import RunEventEmitter
from api.services.agent.memory import get_memory_service
from api.services.agent.models import AgentActivityEvent
from api.services.agent.planner import PlannedStep
from api.services.agent.policy import ACCESS_MODE_FULL, build_access_context
from api.services.agent.tools.base import ToolExecutionContext
from api.services.agent.tools.registry import get_tool_registry

from .app_runtime_helpers import (
    build_execution_context_settings,
    build_execution_prompt,
    build_run_tool_live,
    build_scoped_execution_prompt,
    emit_checkpoint_with_persistence,
    expected_event_types,
)
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
from .session_store import get_session_store
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
        self.session_store = get_session_store()
        self._emitters: dict[str, RunEventEmitter] = {}

    def _build_execution_prompt(
        self,
        *,
        request: ChatRequest,
        settings: dict[str, Any],
    ) -> str:
        return build_execution_prompt(request=request, settings=settings)

    def _build_scoped_execution_prompt(
        self,
        *,
        base_prompt: str,
        owner_role: str,
        scoped_working_context: dict[str, Any],
    ) -> str:
        return build_scoped_execution_prompt(base_prompt=base_prompt, owner_role=owner_role, scoped_working_context=scoped_working_context)

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
        emitter = self._emitters[run_id]
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
            return emitter.emit(
                event_type=event_type,
                title=title,
                detail=detail,
                metadata=metadata or {},
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
            yield from emit_checkpoint_with_persistence(
                emit_event=stream.emit,
                activity_event_factory=activity_event_factory,
                session_store=self.session_store,
                run_id=run_id,
                user_id=user_id,
                tenant_id=access_context.tenant_id,
                conversation_id=conversation_id,
                request=request,
                checkpoint=task_checkpoint,
                title="Checkpoint: task_prepared",
                detail="Task context prepared and scoped for planning.",
                stage="plan",
                status="completed",
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
            yield from emit_checkpoint_with_persistence(
                emit_event=stream.emit,
                activity_event_factory=activity_event_factory,
                session_store=self.session_store,
                run_id=run_id,
                user_id=user_id,
                tenant_id=access_context.tenant_id,
                conversation_id=conversation_id,
                request=request,
                checkpoint=plan_checkpoint,
                title="Checkpoint: plan_ready",
                detail=f"Execution plan prepared with {len(steps)} step(s).",
                stage="plan",
                status="completed",
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
                settings=build_execution_context_settings(
                    request=request,
                    settings=settings,
                    run_id=run_id,
                    user_id=user_id,
                    plan_prep=plan_prep,
                    task_prep=task_prep,
                    role_dispatch_plan=role_dispatch_plan,
                ),
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
            yield from emit_checkpoint_with_persistence(
                emit_event=stream.emit,
                activity_event_factory=activity_event_factory,
                session_store=self.session_store,
                run_id=run_id,
                user_id=user_id,
                tenant_id=access_context.tenant_id,
                conversation_id=conversation_id,
                request=request,
                checkpoint=cycle_started_checkpoint,
                title="Checkpoint: execution_cycle_started",
                detail=f"Cycle {cycle_index} started with {len(steps)} planned step(s).",
                stage="tool",
                status="in_progress",
                settings=state.execution_context.settings,
                state=state,
                pending_steps=steps,
                resume_status="in_progress",
            )

            run_tool_live = build_run_tool_live(
                stream=stream,
                registry=self.registry,
                state=state,
                access_context=access_context,
                activity_event_factory=activity_event_factory,
                scoped_prompt_builder=lambda prompt, owner_role, scoped_context: self._build_scoped_execution_prompt(
                    base_prompt=prompt,
                    owner_role=owner_role,
                    scoped_working_context=scoped_context,
                ),
            )

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
            yield from emit_checkpoint_with_persistence(
                emit_event=stream.emit,
                activity_event_factory=activity_event_factory,
                session_store=self.session_store,
                run_id=run_id,
                user_id=user_id,
                tenant_id=access_context.tenant_id,
                conversation_id=conversation_id,
                request=request,
                checkpoint=cycle_completed_checkpoint,
                title="Checkpoint: execution_cycle_completed",
                detail=f"Cycle {cycle_index} completed after {len(state.executed_steps)} executed step(s).",
                stage="tool",
                status="completed",
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
            yield from emit_checkpoint_with_persistence(
                emit_event=stream.emit,
                activity_event_factory=activity_event_factory,
                session_store=self.session_store,
                run_id=run_id,
                user_id=user_id,
                tenant_id=access_context.tenant_id,
                conversation_id=conversation_id,
                request=request,
                checkpoint=finalization_started_checkpoint,
                title="Checkpoint: finalization_started",
                detail="Final validation and response synthesis started.",
                stage="result",
                status="in_progress",
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
                expected_event_types_resolver=expected_event_types,
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
            yield from emit_checkpoint_with_persistence(
                emit_event=stream.emit,
                activity_event_factory=activity_event_factory,
                session_store=self.session_store,
                run_id=run_id,
                user_id=user_id,
                tenant_id=access_context.tenant_id,
                conversation_id=conversation_id,
                request=request,
                checkpoint=finalization_completed_checkpoint,
                title="Checkpoint: finalization_completed",
                detail="Finalization completed and run result is ready.",
                stage="result",
                status="completed",
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
