from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.models import AgentAction, AgentActivityEvent, utc_now

from ..contract_gate import run_contract_check_live
from ..models import ExecutionState, TaskPreparation
from ..text_helpers import compact
from .models import DeliveryRuntime


def enforce_delivery_contract_gate(
    *,
    run_id: str,
    request: ChatRequest,
    task_prep: TaskPreparation,
    state: ExecutionState,
    runtime: DeliveryRuntime,
    emit_event: Callable[[AgentActivityEvent], dict[str, Any]],
    activity_event_factory: Callable[..., AgentActivityEvent],
) -> Generator[dict[str, Any], None, bool]:
    task_intelligence = task_prep.task_intelligence
    state.contract_check_result = yield from run_contract_check_live(
        run_id=run_id,
        phase="before_server_delivery",
        task_contract=task_prep.task_contract,
        request_message=request.message,
        execution_context=state.execution_context,
        executed_steps=state.executed_steps,
        actions=state.all_actions,
        sources=state.all_sources,
        emit_event=emit_event,
        activity_event_factory=activity_event_factory,
    )
    if bool(state.contract_check_result.get("ready_for_external_actions")):
        return True

    missing = (
        [
            str(item).strip()
            for item in state.contract_check_result.get("missing_items", [])
            if str(item).strip()
        ]
        if isinstance(state.contract_check_result.get("missing_items"), list)
        else []
    )
    blocked_summary = "contract_gate_blocked: " + (
        ", ".join(missing[:4])
        if missing
        else str(state.contract_check_result.get("reason") or "task contract not satisfied")
    )
    blocked_event = activity_event_factory(
        event_type="policy_blocked",
        title=f"Blocked by task contract: {runtime.title}",
        detail=compact(blocked_summary, 200),
        metadata={
            "tool_id": runtime.tool_id,
            "step": runtime.step,
            "missing_items": missing[:8],
        },
    )
    yield emit_event(blocked_event)
    state.all_actions.append(
        AgentAction(
            tool_id=runtime.tool_id,
            action_class="execute",
            status="failed",
            summary=blocked_summary,
            started_at=runtime.started_at,
            ended_at=utc_now().isoformat(),
            metadata={"step": runtime.step, "recipient": task_intelligence.delivery_email},
        )
    )
    state.executed_steps.append(
        {
            "step": runtime.step,
            "tool_id": runtime.tool_id,
            "title": runtime.title,
            "status": "failed",
            "summary": blocked_summary,
        }
    )
    if missing:
        for item in missing[:6]:
            if item and item not in state.next_steps:
                state.next_steps.append(item)
    else:
        blocked_reason = " ".join(
            str(state.contract_check_result.get("reason") or "").split()
        ).strip()
        if blocked_reason and blocked_reason not in state.next_steps:
            state.next_steps.append(blocked_reason)
    return False
