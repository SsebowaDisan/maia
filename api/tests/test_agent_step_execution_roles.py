from __future__ import annotations

from types import SimpleNamespace

from api.schemas import ChatRequest
from api.services.agent.models import AgentActivityEvent
from api.services.agent.orchestration.models import ExecutionState
from api.services.agent.orchestration.step_execution_sections import app as step_exec_module
from api.services.agent.planner import PlannedStep
from api.services.agent.tools.base import ToolExecutionContext


def _activity_factory(**kwargs) -> AgentActivityEvent:
    return AgentActivityEvent(
        event_id=f"evt_{kwargs.get('event_type', 'event')}",
        run_id="run-1",
        event_type=str(kwargs.get("event_type") or ""),
        title=str(kwargs.get("title") or ""),
        detail=str(kwargs.get("detail") or ""),
        metadata=dict(kwargs.get("metadata") or {}),
        stage=str(kwargs.get("stage") or "tool"),
        status=str(kwargs.get("status") or "info"),
        snapshot_ref=kwargs.get("snapshot_ref"),
    )


def test_execute_planned_steps_emits_role_activation_and_handoff(monkeypatch) -> None:
    def _run_guard_checks(**kwargs):
        if False:  # pragma: no cover
            yield {}
        return SimpleNamespace(decision="continue", params=dict(kwargs.get("params") or {}))

    def _handle_step_success(**kwargs):
        if False:  # pragma: no cover
            yield {}
        return None

    monkeypatch.setattr(step_exec_module, "run_guard_checks", _run_guard_checks)
    monkeypatch.setattr(step_exec_module, "handle_step_success", _handle_step_success)

    def _run_tool_live(**kwargs):
        if False:  # pragma: no cover
            yield {}
        return SimpleNamespace(summary="ok")

    state = ExecutionState(
        execution_context=ToolExecutionContext(
            user_id="user-1",
            tenant_id="tenant-1",
            conversation_id="conv-1",
            run_id="run-1",
            mode="company_agent",
            settings={},
        )
    )
    steps = [
        PlannedStep(tool_id="marketing.web_research", title="Research", params={}),
        PlannedStep(tool_id="report.generate", title="Write report", params={}),
    ]
    captured: list[AgentActivityEvent] = []

    def _emit(event: AgentActivityEvent):
        captured.append(event)
        return {"type": "activity", "event": event.to_dict()}

    _ = list(
        step_exec_module.execute_planned_steps(
            run_id="run-1",
            request=ChatRequest(message="research and report", agent_mode="company_agent"),
            access_context=SimpleNamespace(
                access_mode="restricted",
                full_access_enabled=False,
            ),
            registry=SimpleNamespace(),
            steps=steps,
            execution_prompt="research and report",
            deep_research_mode=False,
            task_prep=SimpleNamespace(),
            state=state,
            run_tool_live=_run_tool_live,
            emit_event=_emit,
            activity_event_factory=_activity_factory,
        )
    )

    event_types = [event.event_type for event in captured]
    assert "role_activated" in event_types
    assert "role_handoff" in event_types
    assert event_types.count("role_activated") == 2
    assert state.execution_context.settings.get("__active_execution_role") == "writer"
