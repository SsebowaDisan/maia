from __future__ import annotations

import time
from collections.abc import Callable, Generator
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.models import AgentActivityEvent, utc_now
from api.services.agent.observability import get_agent_observability
from api.services.agent.planner import PlannedStep

from ..execution_trace import record_retry_trace
from ..handoff_state import handoff_pause_notice, is_handoff_paused
from ..models import ExecutionState, TaskPreparation
from ..role_contracts import resolve_owner_role_for_tool
from .failure import handle_step_failure
from .guards import (
    prepare_step_params,
    run_guard_checks,
    should_skip_step_for_workspace_logging,
)
from .success import handle_step_success


def _should_retry_transient_browser_failure(
    *,
    step: PlannedStep,
    params: dict[str, Any],
    exc: Exception,
) -> bool:
    if step.tool_id != "browser.playwright.inspect":
        return False
    if bool(params.get("__retry_attempted")):
        return False
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "net::err_http2_protocol_error",
            "net::err_connection_reset",
            "net::err_connection_closed",
            "net::err_timed_out",
            "net::err_name_not_resolved",
            "navigation timeout",
        )
    )


def execute_planned_steps(
    *,
    run_id: str,
    request: ChatRequest,
    access_context: Any,
    registry: Any,
    steps: list[PlannedStep],
    execution_prompt: str,
    deep_research_mode: bool,
    task_prep: TaskPreparation,
    state: ExecutionState,
    run_tool_live: Callable[..., Generator[dict[str, Any], None, Any]],
    emit_event: Callable[[AgentActivityEvent], dict[str, Any]],
    activity_event_factory: Callable[..., AgentActivityEvent],
) -> Generator[dict[str, Any], None, None]:
    step_cursor = 0
    display_step_index = 0
    active_role = " ".join(
        str(state.execution_context.settings.get("__active_execution_role") or "").split()
    ).strip().lower()
    while step_cursor < len(steps):
        if is_handoff_paused(settings=state.execution_context.settings):
            if not bool(state.execution_context.settings.get("__handoff_pause_emitted")):
                pause_notice = handoff_pause_notice(settings=state.execution_context.settings)
                pause_event = activity_event_factory(
                    event_type=str(pause_notice.get("event_type") or "handoff_paused"),
                    title=str(pause_notice.get("title") or "Execution paused for human verification"),
                    detail=str(pause_notice.get("detail") or "")[:200],
                    metadata=dict(pause_notice.get("metadata") or {}),
                )
                yield emit_event(pause_event)
                waiting_event = activity_event_factory(
                    event_type="agent.waiting",
                    title="Agent waiting for human verification",
                    detail=str(pause_notice.get("detail") or "")[:200],
                    metadata=dict(pause_notice.get("metadata") or {}),
                )
                yield emit_event(waiting_event)
                state.execution_context.settings["__handoff_pause_emitted"] = True
            break
        step = steps[step_cursor]
        if should_skip_step_for_workspace_logging(state=state, step=step):
            step_cursor += 1
            continue

        display_step_index += 1
        index = display_step_index
        step_started = utc_now().isoformat()
        owner_role = resolve_owner_role_for_tool(step.tool_id)
        if active_role != owner_role:
            if active_role:
                handoff_event = activity_event_factory(
                    event_type="role_handoff",
                    title="Role handoff",
                    detail=f"{active_role} -> {owner_role}",
                    metadata={
                        "from_role": active_role,
                        "to_role": owner_role,
                        "step": index,
                        "tool_id": step.tool_id,
                    },
                )
                yield emit_event(handoff_event)
                agent_handoff_event = activity_event_factory(
                    event_type="agent.handoff",
                    title="Agent handoff",
                    detail=f"{active_role} -> {owner_role}",
                    metadata={
                        "from_role": active_role,
                        "to_role": owner_role,
                        "step": index,
                        "tool_id": step.tool_id,
                    },
                )
                yield emit_event(agent_handoff_event)
            role_event = activity_event_factory(
                event_type="role_activated",
                title=f"Role active: {owner_role}",
                detail=step.title[:200],
                metadata={
                    "role": owner_role,
                    "step": index,
                    "tool_id": step.tool_id,
                },
            )
            yield emit_event(role_event)
            agent_resume_event = activity_event_factory(
                event_type="agent.resume",
                title=f"Agent resumed: {owner_role}",
                detail=step.title[:200],
                metadata={
                    "role": owner_role,
                    "step": index,
                    "tool_id": step.tool_id,
                },
            )
            yield emit_event(agent_resume_event)
            active_role = owner_role
            state.execution_context.settings["__active_execution_role"] = owner_role

        queued_event = activity_event_factory(
            event_type="tool_queued",
            title=step.title,
            detail=step.tool_id,
            metadata={"tool_id": step.tool_id, "step": index},
        )
        yield emit_event(queued_event)
        step_event = activity_event_factory(
            event_type="tool_started",
            title=step.title,
            detail=step.tool_id,
            metadata={"tool_id": step.tool_id, "step": index},
        )
        yield emit_event(step_event)
        progress_event = activity_event_factory(
            event_type="tool_progress",
            title=step.title,
            detail="Tool execution in progress",
            metadata={"tool_id": step.tool_id, "step": index, "progress": 0.5},
        )
        yield emit_event(progress_event)

        params = prepare_step_params(step=step, access_context=access_context)
        guard_outcome = yield from run_guard_checks(
            run_id=run_id,
            request=request,
            task_prep=task_prep,
            state=state,
            registry=registry,
            steps=steps,
            step_cursor=step_cursor,
            index=index,
            step_started=step_started,
            step=step,
            params=params,
            emit_event=emit_event,
            activity_event_factory=activity_event_factory,
        )
        if guard_outcome.decision == "restart":
            continue
        if guard_outcome.decision == "skip":
            step_cursor += 1
            continue

        tool_started_clock = time.perf_counter()
        try:
            result = yield from run_tool_live(
                step=step,
                step_index=index,
                prompt=execution_prompt,
                params=guard_outcome.params,
            )
            elapsed = time.perf_counter() - tool_started_clock
            get_agent_observability().observe_tool_execution(
                tool_id=step.tool_id,
                status="success",
                duration_seconds=elapsed,
            )
            yield from handle_step_success(
                access_context=access_context,
                deep_research_mode=deep_research_mode,
                execution_prompt=execution_prompt,
                state=state,
                registry=registry,
                steps=steps,
                step_cursor=step_cursor,
                step=step,
                index=index,
                step_started=step_started,
                duration_seconds=elapsed,
                result=result,
                run_tool_live=run_tool_live,
                emit_event=emit_event,
                activity_event_factory=activity_event_factory,
            )
        except Exception as exc:
            elapsed = time.perf_counter() - tool_started_clock
            if _should_retry_transient_browser_failure(
                step=step,
                params=guard_outcome.params,
                exc=exc,
            ):
                retry_trace = record_retry_trace(
                    state=state,
                    step_index=index,
                    tool_id=step.tool_id,
                    reason=str(exc),
                    status="started",
                )
                retry_event = activity_event_factory(
                    event_type="tool_progress",
                    title=step.title,
                    detail="Transient browser error detected; retrying once with reduced scope.",
                    metadata={
                        "tool_id": step.tool_id,
                        "step": index,
                        "retry": True,
                        "retry_trace": retry_trace,
                    },
                )
                yield emit_event(retry_event)
                retry_params = dict(guard_outcome.params)
                retry_params["__retry_attempted"] = True
                retry_params.setdefault("follow_same_domain_links", False)
                retry_started_clock = time.perf_counter()
                try:
                    retry_result = yield from run_tool_live(
                        step=step,
                        step_index=index,
                        prompt=execution_prompt,
                        params=retry_params,
                    )
                    retry_elapsed = time.perf_counter() - retry_started_clock
                    get_agent_observability().observe_tool_execution(
                        tool_id=step.tool_id,
                        status="success",
                        duration_seconds=retry_elapsed,
                    )
                    record_retry_trace(
                        state=state,
                        step_index=index,
                        tool_id=step.tool_id,
                        reason="retry completed successfully",
                        status="completed",
                    )
                    yield from handle_step_success(
                        access_context=access_context,
                        deep_research_mode=deep_research_mode,
                        execution_prompt=execution_prompt,
                        state=state,
                        registry=registry,
                        steps=steps,
                        step_cursor=step_cursor,
                        step=step,
                        index=index,
                        step_started=step_started,
                        duration_seconds=retry_elapsed,
                        result=retry_result,
                        run_tool_live=run_tool_live,
                        emit_event=emit_event,
                        activity_event_factory=activity_event_factory,
                    )
                    step_cursor += 1
                    continue
                except Exception as retry_exc:
                    record_retry_trace(
                        state=state,
                        step_index=index,
                        tool_id=step.tool_id,
                        reason=str(retry_exc),
                        status="failed",
                    )
                    exc = retry_exc
                    elapsed = time.perf_counter() - retry_started_clock
            get_agent_observability().observe_tool_execution(
                tool_id=step.tool_id,
                status="failed",
                duration_seconds=elapsed,
            )
            yield from handle_step_failure(
                execution_prompt=execution_prompt,
                state=state,
                registry=registry,
                step=step,
                index=index,
                step_started=step_started,
                duration_seconds=elapsed,
                exc=exc,
                emit_event=emit_event,
                activity_event_factory=activity_event_factory,
            )
        step_cursor += 1
