from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any

from api.services.agent.llm_execution_support import suggest_failure_recovery
from api.services.agent.models import AgentActivityEvent
from api.services.agent.planner import PlannedStep

from ..models import ExecutionState
from ..web_evidence import record_web_evidence
from ..web_kpi import is_web_tool, record_web_kpi


def handle_step_failure(
    *,
    execution_prompt: str,
    state: ExecutionState,
    registry: Any,
    step: PlannedStep,
    index: int,
    step_started: str,
    duration_seconds: float,
    exc: Exception,
    emit_event: Callable[[AgentActivityEvent], dict[str, Any]],
    activity_event_factory: Callable[..., AgentActivityEvent],
) -> Generator[dict[str, Any], None, None]:
    if is_web_tool(step.tool_id):
        record_web_kpi(
            settings=state.execution_context.settings,
            tool_id=step.tool_id,
            status="failed",
            duration_seconds=duration_seconds,
            data={},
        )
        record_web_evidence(
            settings=state.execution_context.settings,
            tool_id=step.tool_id,
            status="failed",
            data={},
            sources=[],
        )
    workspace_auth_error = (
        step.tool_id in ("workspace.docs.research_notes", "workspace.sheets.track_step")
        and any(
            marker in str(exc).lower()
            for marker in (
                "google_tokens_missing",
                "oauth",
                "refresh_token",
                "unauthenticated",
                "invalid authentication",
            )
        )
    )
    is_workspace_logging_step = bool(step.params.get("__workspace_logging_step"))
    if workspace_auth_error and is_workspace_logging_step:
        state.deep_workspace_logging_enabled = False
        if not state.deep_workspace_warning_emitted:
            state.deep_workspace_warning_emitted = True
            warning_event = activity_event_factory(
                event_type="tool_failed",
                title="Workspace logging disabled",
                detail=(
                    "Google Docs/Sheets is not connected. "
                    "Continuing execution without automatic roadmap sync."
                ),
                metadata={
                    "tool_id": step.tool_id,
                    "step": index,
                    "workspace_logging": True,
                },
            )
            yield emit_event(warning_event)
        skipped_summary = (
            "Workspace logging skipped because Google Docs/Sheets authentication is unavailable. "
            "Execution continued without roadmap sync."
        )
        skipped_action = registry.get(step.tool_id).to_action(
            status="skipped",
            summary=skipped_summary,
            started_at=step_started,
            metadata={"step": index, "workspace_logging": True},
        )
        state.all_actions.append(skipped_action)
        state.executed_steps.append(
            {
                "step": index,
                "tool_id": step.tool_id,
                "title": step.title,
                "status": "skipped",
                "summary": skipped_summary,
            }
        )
        skipped_event = activity_event_factory(
            event_type="tool_skipped",
            title=step.title,
            detail=skipped_summary,
            metadata={
                "tool_id": step.tool_id,
                "step": index,
                "workspace_logging": True,
            },
        )
        yield emit_event(skipped_event)
        return
    tool_instance = registry.get(step.tool_id)
    tool_meta = tool_instance.metadata
    action = tool_instance.to_action(
        status="failed",
        summary=str(exc),
        started_at=step_started,
        metadata={"step": index},
    )
    state.all_actions.append(action)
    state.executed_steps.append(
        {
            "step": index,
            "tool_id": step.tool_id,
            "title": step.title,
            "status": "failed",
            "summary": str(exc),
        }
    )
    exc_text = str(exc)
    if "requires confirmation" in exc_text.lower():
        approval_event = activity_event_factory(
            event_type="approval_required",
            title=f"Approval required: {step.title}",
            detail=exc_text,
            metadata={"tool_id": step.tool_id, "step": index},
        )
        yield emit_event(approval_event)
        policy_event = activity_event_factory(
            event_type="policy_blocked",
            title=f"Policy blocked: {step.title}",
            detail="Execution blocked in restricted mode until confirmation",
            metadata={"tool_id": step.tool_id, "step": index},
        )
        yield emit_event(policy_event)
    fail_event = activity_event_factory(
        event_type="tool_failed",
        title=step.title,
        detail=exc_text,
        metadata={"tool_id": step.tool_id, "step": index},
    )
    yield emit_event(fail_event)
    recovery_hint = suggest_failure_recovery(
        request_message=execution_prompt,
        tool_id=step.tool_id,
        step_title=step.title,
        error_text=exc_text,
        recent_steps=state.executed_steps[-8:],
    )
    if recovery_hint:
        state.next_steps.append(recovery_hint)
        recovery_event = activity_event_factory(
            event_type="tool_progress",
            title="Recovery suggestion generated",
            detail=recovery_hint,
            metadata={
                "tool_id": step.tool_id,
                "step": index,
                "recovery_hint": recovery_hint,
            },
        )
        yield emit_event(recovery_event)
        if (
            str(tool_meta.action_class).strip().lower() == "execute"
            and not bool(state.execution_context.settings.get("__clarification_requested_after_attempt"))
        ):
            question = (
                recovery_hint
                if recovery_hint.strip().lower().startswith("please provide")
                else f"Please provide: {recovery_hint}"
            )
            clarification_event = activity_event_factory(
                event_type="llm.clarification_requested",
                title="Clarification required after autonomous attempts",
                detail=question[:200],
                metadata={
                    "missing_requirements": [recovery_hint[:220]],
                    "questions": [question[:240]],
                    "deferred_until_after_attempts": True,
                    "tool_id": step.tool_id,
                    "step": index,
                },
            )
            yield emit_event(clarification_event)
            state.execution_context.settings["__clarification_requested_after_attempt"] = True
