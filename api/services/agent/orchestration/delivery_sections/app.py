from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.models import AgentActivityEvent

from ..models import ExecutionState, TaskPreparation
from .decisioning import (
    build_delivery_runtime,
    prepare_delivery_content,
    should_attempt_delivery,
)
from .remediation import enforce_delivery_contract_gate
from .send_path import run_delivery_send_path


def maybe_send_server_delivery(
    *,
    run_id: str,
    request: ChatRequest,
    task_prep: TaskPreparation,
    state: ExecutionState,
    emit_event: Callable[[AgentActivityEvent], dict[str, Any]],
    activity_event_factory: Callable[..., AgentActivityEvent],
) -> Generator[dict[str, Any], None, None]:
    if not should_attempt_delivery(task_prep=task_prep, state=state):
        return

    runtime = build_delivery_runtime(state=state)
    gate_allowed = yield from enforce_delivery_contract_gate(
        run_id=run_id,
        request=request,
        task_prep=task_prep,
        state=state,
        runtime=runtime,
        emit_event=emit_event,
        activity_event_factory=activity_event_factory,
    )
    if not gate_allowed:
        return

    report_title, report_body, pre_send_events = prepare_delivery_content(
        request=request,
        task_prep=task_prep,
        state=state,
        runtime=runtime,
        activity_event_factory=activity_event_factory,
    )
    for event in pre_send_events:
        yield emit_event(event)

    yield from run_delivery_send_path(
        task_prep=task_prep,
        state=state,
        runtime=runtime,
        report_title=report_title,
        report_body=report_body,
        emit_event=emit_event,
        activity_event_factory=activity_event_factory,
    )
