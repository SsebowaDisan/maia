from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.intelligence_sections.models import TaskIntelligence
from api.services.agent.models import AgentAction, AgentActivityEvent
from api.services.agent.orchestration.models import ExecutionState, TaskPreparation
from api.services.agent.orchestration.step_execution_sections.guards import run_guard_checks
from api.services.agent.planner import PlannedStep
from api.services.agent.tools.base import ToolExecutionContext, ToolMetadata


def _task_prep() -> TaskPreparation:
    return TaskPreparation(
        task_intelligence=TaskIntelligence(
            objective="Build report",
            target_url="",
            target_host="",
            delivery_email="",
            requires_delivery=False,
            requires_web_inspection=False,
            requested_report=True,
            intent_tags=("report",),
        ),
        user_preferences={},
        research_depth_profile={},
        conversation_summary="",
        rewritten_task="Build report",
        planned_deliverables=[],
        planned_constraints=[],
        task_contract={},
        contract_objective="Build report",
        contract_outputs=[],
        contract_facts=[],
        contract_actions=[],
        contract_target="",
        contract_missing_requirements=[],
        contract_success_checks=[],
        memory_context_snippets=[],
        clarification_blocked=False,
        clarification_questions=[],
    )


@dataclass
class _ToolStub:
    metadata: ToolMetadata

    def to_action(
        self,
        *,
        status: str,
        summary: str,
        started_at: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentAction:
        return AgentAction(
            tool_id=self.metadata.tool_id,
            action_class=self.metadata.action_class,
            status=str(status),  # type: ignore[arg-type]
            summary=summary,
            started_at=started_at,
            ended_at=started_at,
            metadata=metadata or {},
        )


class _RegistryStub:
    def __init__(self, tool_id: str, *, action_class: str = "draft") -> None:
        self._tool = _ToolStub(
            metadata=ToolMetadata(
                tool_id=tool_id,
                action_class=action_class,  # type: ignore[arg-type]
                risk_level="low",
                required_permissions=[],
                execution_policy="auto_execute",
                description="stub",
            )
        )

    def get(self, tool_id: str) -> _ToolStub:
        assert tool_id == self._tool.metadata.tool_id
        return self._tool


def _event_factory() -> tuple[
    list[AgentActivityEvent],
    Any,
    Any,
]:
    events: list[AgentActivityEvent] = []

    def emit_event(event: AgentActivityEvent) -> dict[str, Any]:
        events.append(event)
        return {"event_type": event.event_type, "title": event.title}

    def activity_event_factory(
        *,
        event_type: str,
        title: str,
        detail: str = "",
        metadata: dict[str, Any] | None = None,
        **_: Any,
    ) -> AgentActivityEvent:
        payload = dict(metadata or {})
        return AgentActivityEvent(
            event_id=f"evt_{len(events) + 1}",
            run_id="run_test",
            event_type=event_type,
            title=title,
            detail=detail,
            metadata=payload,
        )

    return events, emit_event, activity_event_factory


def _consume(generator: Generator[dict[str, Any], None, Any]) -> Any:
    while True:
        try:
            next(generator)
        except StopIteration as stop:
            return stop.value


def test_run_guard_checks_emits_role_contract_check_and_allows_matching_role() -> None:
    events, emit_event, activity_event_factory = _event_factory()
    step = PlannedStep(
        tool_id="report.generate",
        title="Write report",
        params={},
    )
    execution_context = ToolExecutionContext(
        user_id="u1",
        tenant_id="t1",
        conversation_id="c1",
        run_id="r1",
        mode="company_agent",
        settings={"__role_owned_steps": [{"step": 1, "owner_role": "writer"}]},
    )
    state = ExecutionState(execution_context=execution_context)
    outcome = _consume(
        run_guard_checks(
            run_id="r1",
            request=ChatRequest(message="build report", agent_mode="company_agent"),
            task_prep=_task_prep(),
            state=state,
            registry=_RegistryStub("report.generate", action_class="draft"),
            steps=[step],
            step_cursor=0,
            index=1,
            step_started="2026-03-07T00:00:00+00:00",
            step=step,
            params={},
            emit_event=emit_event,
            activity_event_factory=activity_event_factory,
        )
    )
    assert outcome.decision == "execute"
    check_event = next(event for event in events if event.event_type == "role_contract_check")
    assert check_event.data.get("owner_role") == "writer"
    assert check_event.data.get("role_allows_tool") is True


def test_run_guard_checks_blocks_when_planned_role_cannot_use_tool() -> None:
    events, emit_event, activity_event_factory = _event_factory()
    step = PlannedStep(
        tool_id="report.generate",
        title="Write report",
        params={},
    )
    execution_context = ToolExecutionContext(
        user_id="u1",
        tenant_id="t1",
        conversation_id="c1",
        run_id="r1",
        mode="company_agent",
        settings={"__role_owned_steps": [{"step": 1, "owner_role": "browser"}]},
    )
    state = ExecutionState(execution_context=execution_context)
    outcome = _consume(
        run_guard_checks(
            run_id="r1",
            request=ChatRequest(message="build report", agent_mode="company_agent"),
            task_prep=_task_prep(),
            state=state,
            registry=_RegistryStub("report.generate", action_class="draft"),
            steps=[step],
            step_cursor=0,
            index=1,
            step_started="2026-03-07T00:00:00+00:00",
            step=step,
            params={},
            emit_event=emit_event,
            activity_event_factory=activity_event_factory,
        )
    )
    assert outcome.decision == "skip"
    blocked_event = next(event for event in events if event.event_type == "policy_blocked")
    assert "role_contract_blocked" in blocked_event.detail
    assert state.executed_steps[-1]["status"] == "failed"
    assert state.all_actions[-1].status == "failed"
