from __future__ import annotations

import time
from collections.abc import Callable, Generator
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.models import AgentActivityEvent, utc_now
from api.services.agent.observability import get_agent_observability
from api.services.agent.planner import PlannedStep

from ..models import ExecutionState, TaskPreparation
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
    while step_cursor < len(steps):
        step = steps[step_cursor]
        if should_skip_step_for_workspace_logging(state=state, step=step):
            step_cursor += 1
            continue

        display_step_index += 1
        index = display_step_index
        step_started = utc_now().isoformat()

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
                retry_event = activity_event_factory(
                    event_type="tool_progress",
                    title=step.title,
                    detail="Transient browser error detected; retrying once with reduced scope.",
                    metadata={
                        "tool_id": step.tool_id,
                        "step": index,
                        "retry": True,
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
