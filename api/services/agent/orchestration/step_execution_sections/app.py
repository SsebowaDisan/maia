from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.models import AgentActivityEvent, utc_now
from api.services.agent.planner import PlannedStep

from ..models import ExecutionState, TaskPreparation
from .failure import handle_step_failure
from .guards import (
    prepare_step_params,
    run_guard_checks,
    should_skip_step_for_workspace_logging,
)
from .success import handle_step_success


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
            title=f"Queued: {step.title}",
            detail=step.tool_id,
            metadata={"tool_id": step.tool_id, "step": index},
        )
        yield emit_event(queued_event)
        step_event = activity_event_factory(
            event_type="tool_started",
            title=f"Step {index}: {step.title}",
            detail=step.tool_id,
        )
        yield emit_event(step_event)
        progress_event = activity_event_factory(
            event_type="tool_progress",
            title=f"Step {index}: Running {step.title}",
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

        try:
            result = yield from run_tool_live(
                step=step,
                step_index=index,
                prompt=execution_prompt,
                params=guard_outcome.params,
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
                result=result,
                run_tool_live=run_tool_live,
                emit_event=emit_event,
                activity_event_factory=activity_event_factory,
            )
        except Exception as exc:
            yield from handle_step_failure(
                execution_prompt=execution_prompt,
                state=state,
                registry=registry,
                step=step,
                index=index,
                step_started=step_started,
                exc=exc,
                emit_event=emit_event,
                activity_event_factory=activity_event_factory,
            )
        step_cursor += 1
