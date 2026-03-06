from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.models import AgentActivityEvent
from api.services.agent.planner import PlannedStep
from api.services.agent.policy import ACCESS_MODE_FULL

from ..clarification_helpers import (
    questions_for_requirements,
    select_relevant_clarification_requirements,
)
from ..constants import GUARDED_ACTION_TOOL_IDS
from ..contract_gate import build_contract_remediation_steps, run_contract_check_live
from ..discovery_gate import (
    blocking_requirements_from_slots,
    update_slot_lifecycle,
    with_slot_lifecycle_defaults,
)
from ..models import ExecutionState, TaskPreparation
from ..text_helpers import compact
from .models import StepGuardOutcome


def should_skip_step_for_workspace_logging(
    *,
    state: ExecutionState,
    step: PlannedStep,
) -> bool:
    if state.deep_workspace_logging_enabled:
        return False
    if step.tool_id not in ("workspace.docs.research_notes", "workspace.sheets.track_step"):
        return False
    return bool(step.params.get("__workspace_logging_step"))


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
        runtime_slots_raw = state.execution_context.settings.get("__task_clarification_slots")
        runtime_slots = (
            [dict(row) for row in runtime_slots_raw if isinstance(row, dict)]
            if isinstance(runtime_slots_raw, list)
            else [dict(row) for row in task_prep.contract_missing_slots[:8] if isinstance(row, dict)]
        )
        runtime_slots = with_slot_lifecycle_defaults(slots=runtime_slots[:8])
        deferred_missing_requirements = blocking_requirements_from_slots(
            slots=runtime_slots[:8],
            fallback_requirements=task_prep.contract_missing_requirements[:6],
            limit=6,
        )
        runtime_slots = update_slot_lifecycle(
            slots=runtime_slots,
            unresolved_requirements=deferred_missing_requirements,
            attempted_requirements=deferred_missing_requirements,
            evidence_sources=[step.tool_id],
        )
        task_prep.contract_missing_slots = runtime_slots[:8]
        state.execution_context.settings["__task_clarification_slots"] = runtime_slots[:8]
        state.contract_check_result = yield from run_contract_check_live(
            run_id=run_id,
            phase=f"before_action_step_{index}",
            task_contract=task_prep.task_contract,
            request_message=request.message,
            execution_context=state.execution_context,
            executed_steps=state.executed_steps,
            actions=state.all_actions,
            sources=state.all_sources,
            pending_action_tool_id=step.tool_id,
            emit_event=emit_event,
            activity_event_factory=activity_event_factory,
        )
        ready_for_actions = bool(
            state.contract_check_result.get("ready_for_external_actions")
        )
        if ready_for_actions:
            resolved_slots = update_slot_lifecycle(
                slots=runtime_slots,
                unresolved_requirements=[],
                attempted_requirements=deferred_missing_requirements,
                evidence_sources=[step.tool_id],
            )
            task_prep.contract_missing_slots = resolved_slots[:8]
            state.execution_context.settings["__task_clarification_slots"] = resolved_slots[:8]
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
            relevant_missing_requirements = select_relevant_clarification_requirements(
                deferred_missing_requirements=deferred_missing_requirements,
                contract_missing_items=missing[:8],
                limit=6,
            )
            runtime_slots = update_slot_lifecycle(
                slots=runtime_slots,
                unresolved_requirements=relevant_missing_requirements,
                attempted_requirements=deferred_missing_requirements,
                evidence_sources=[step.tool_id],
            )
            task_prep.contract_missing_slots = runtime_slots[:8]
            state.execution_context.settings["__task_clarification_slots"] = runtime_slots[:8]
            if (
                relevant_missing_requirements
                and not task_prep.clarification_blocked
                and not bool(state.execution_context.settings.get("__clarification_requested_after_attempt"))
            ):
                clarification_questions = questions_for_requirements(
                    requirements=relevant_missing_requirements,
                    all_requirements=deferred_missing_requirements,
                    all_questions=task_prep.clarification_questions[:6],
                )
                clarification_event = activity_event_factory(
                    event_type="llm.clarification_requested",
                    title="Clarification required after autonomous attempts",
                    detail=compact("; ".join(relevant_missing_requirements[:3]), 200),
                    metadata={
                        "missing_requirements": relevant_missing_requirements,
                        "questions": clarification_questions,
                        "contract_check_missing_items": missing[:8],
                        "deferred_until_after_attempts": True,
                        "tool_id": step.tool_id,
                        "step": index,
                        "missing_requirement_slots": runtime_slots[:8],
                    },
                )
                yield emit_event(clarification_event)
                state.execution_context.settings["__clarification_requested_after_attempt"] = True
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
                    "missing_requirement_slots": runtime_slots[:8],
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
