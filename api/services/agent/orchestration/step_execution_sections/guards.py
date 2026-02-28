from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.models import AgentActivityEvent
from api.services.agent.planner import PlannedStep
from api.services.agent.policy import ACCESS_MODE_FULL

from ..constants import GUARDED_ACTION_TOOL_IDS
from ..contract_gate import build_contract_remediation_steps, run_contract_check_live
from ..models import ExecutionState, TaskPreparation
from ..text_helpers import compact
from .models import StepGuardOutcome


def should_skip_step_for_workspace_logging(
    *,
    state: ExecutionState,
    step: PlannedStep,
) -> bool:
    return (not state.deep_workspace_logging_enabled) and step.tool_id in (
        "workspace.docs.research_notes",
        "workspace.sheets.track_step",
    )


def prepare_step_params(
    *,
    step: PlannedStep,
    access_context: Any,
) -> dict[str, Any]:
    params = dict(step.params)
    if (
        access_context.access_mode == ACCESS_MODE_FULL
        and access_context.full_access_enabled
    ):
        params.setdefault("confirmed", True)
    return params


def run_guard_checks(
    *,
    run_id: str,
    request: ChatRequest,
    task_prep: TaskPreparation,
    state: ExecutionState,
    registry: Any,
    steps: list[PlannedStep],
    step_cursor: int,
    index: int,
    step_started: str,
    step: PlannedStep,
    params: dict[str, Any],
    emit_event: Callable[[AgentActivityEvent], dict[str, Any]],
    activity_event_factory: Callable[..., AgentActivityEvent],
) -> Generator[dict[str, Any], None, StepGuardOutcome]:
    tool_meta = registry.get(step.tool_id).metadata
    is_guarded_action = step.tool_id in GUARDED_ACTION_TOOL_IDS
    if is_guarded_action:
        state.contract_check_result = yield from run_contract_check_live(
            run_id=run_id,
            phase=f"before_action_step_{index}",
            task_contract=task_prep.task_contract,
            request_message=request.message,
            execution_context=state.execution_context,
            executed_steps=state.executed_steps,
            actions=state.all_actions,
            sources=state.all_sources,
            emit_event=emit_event,
            activity_event_factory=activity_event_factory,
        )
        ready_for_actions = bool(
            state.contract_check_result.get("ready_for_external_actions")
        )
        if not ready_for_actions:
            remediation_steps: list[PlannedStep] = []
            if state.remediation_attempts < state.max_remediation_attempts:
                remediation_steps = build_contract_remediation_steps(
                    check=state.contract_check_result,
                    registry=registry,
                    remediation_signatures=state.remediation_signatures,
                    allow_execute=False,
                    limit=3,
                )
            if remediation_steps:
                state.remediation_attempts += 1
                steps[step_cursor:step_cursor] = remediation_steps
                remediation_event = activity_event_factory(
                    event_type="plan_refined",
                    title="Inserted contract remediation steps",
                    detail=(
                        f"Added {len(remediation_steps)} remediation step(s) "
                        f"before '{step.title}'."
                    ),
                    metadata={
                        "inserted": len(remediation_steps),
                        "at_step": index,
                        "tool_ids": [item.tool_id for item in remediation_steps],
                    },
                )
                yield emit_event(remediation_event)
                return StepGuardOutcome(decision="restart", params=params)

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
                else str(
                    state.contract_check_result.get("reason")
                    or "task contract not satisfied"
                )
            )
            blocked_event = activity_event_factory(
                event_type="policy_blocked",
                title=f"Blocked by task contract: {step.title}",
                detail=compact(blocked_summary, 200),
                metadata={
                    "tool_id": step.tool_id,
                    "step": index,
                    "missing_items": missing[:8],
                },
            )
            yield emit_event(blocked_event)
            state.all_actions.append(
                registry.get(step.tool_id).to_action(
                    status="failed",
                    summary=blocked_summary,
                    started_at=step_started,
                    metadata={
                        "step": index,
                        "contract_blocked": True,
                        "missing_items": missing[:8],
                    },
                )
            )
            state.executed_steps.append(
                {
                    "step": index,
                    "tool_id": step.tool_id,
                    "title": step.title,
                    "status": "failed",
                    "summary": blocked_summary,
                }
            )
            return StepGuardOutcome(decision="skip", params=params)

    if (
        tool_meta.action_class == "execute"
        and tool_meta.execution_policy == "confirm_before_execute"
    ):
        if params.get("confirmed"):
            granted_event = activity_event_factory(
                event_type="approval_granted",
                title=f"Execution approved: {step.title}",
                detail="Full access mode auto-approved this execute action",
                metadata={"tool_id": step.tool_id, "step": index},
            )
            yield emit_event(granted_event)
        else:
            approval_event = activity_event_factory(
                event_type="approval_required",
                title=f"Approval required: {step.title}",
                detail="Restricted mode requires explicit confirmation",
                metadata={"tool_id": step.tool_id, "step": index},
            )
            yield emit_event(approval_event)

    return StepGuardOutcome(decision="execute", params=params)
