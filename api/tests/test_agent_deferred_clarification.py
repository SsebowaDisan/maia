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


def _task_prep_with_deferred_missing() -> TaskPreparation:
    return TaskPreparation(
        task_intelligence=TaskIntelligence(
            objective="Analyze site and send outreach message",
            target_url="https://axongroup.com/",
            target_host="axongroup.com",
            delivery_email="",
            requires_delivery=False,
            requires_web_inspection=True,
            requested_report=False,
            intent_tags=("web_research", "contact_form_submission"),
        ),
        user_preferences={},
        research_depth_profile={},
        conversation_summary="",
        rewritten_task="Analyze and outreach",
        planned_deliverables=[],
        planned_constraints=[],
        task_contract={"required_actions": ["submit_contact_form"]},
        contract_objective="Analyze and outreach",
        contract_outputs=[],
        contract_facts=[],
        contract_actions=["submit_contact_form"],
        contract_target="",
        contract_missing_requirements=["Provide sender company profile for outreach"],
        contract_success_checks=[],
        memory_context_snippets=[],
        clarification_blocked=False,
        clarification_questions=["Please provide: Provide sender company profile for outreach"],
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
            action_class="execute",
            status=str(status),  # type: ignore[arg-type]
            summary=summary,
            started_at=started_at,
            ended_at=started_at,
            metadata=metadata or {},
        )


class _RegistryStub:
    def __init__(self, tool_id: str) -> None:
        self._tool = _ToolStub(
            metadata=ToolMetadata(
                tool_id=tool_id,
                action_class="execute",
                risk_level="high",
                required_permissions=[],
                execution_policy="confirm_before_execute",
                description="stub",
            )
        )

    def get(self, tool_id: str) -> _ToolStub:
        assert tool_id == self._tool.metadata.tool_id
        return self._tool


def _fake_contract_gate_blocked(**_: Any) -> Generator[dict[str, Any], None, dict[str, Any]]:
    if False:
        yield {}
    return {
        "ready_for_final_response": False,
        "ready_for_external_actions": False,
        "missing_items": ["Required action not completed: submit_contact_form"],
        "reason": "Required external action is not completed.",
        "recommended_remediation": [],
    }


def _fake_contract_gate_missing_delivery_target(
    **_: Any,
) -> Generator[dict[str, Any], None, dict[str, Any]]:
    if False:
        yield {}
    return {
        "ready_for_final_response": False,
        "ready_for_external_actions": False,
        "missing_items": ["Missing delivery target for required action: send_email"],
        "reason": "Email delivery is requested but recipient is missing.",
        "recommended_remediation": [],
    }


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


def test_run_guard_checks_skips_irrelevant_deferred_clarification_after_contract_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.services.agent.orchestration.step_execution_sections.guards.run_contract_check_live",
        _fake_contract_gate_blocked,
    )
    monkeypatch.setattr(
        "api.services.agent.orchestration.step_execution_sections.guards.build_contract_remediation_steps",
        lambda **_: [],
    )
    events, emit_event, activity_event_factory = _event_factory()
    request = ChatRequest(message="Analyze and send contact form message", agent_mode="company_agent")
    task_prep = _task_prep_with_deferred_missing()
    step = PlannedStep(
        tool_id="browser.contact_form.send",
        title="Send outreach form",
        params={"url": "https://axongroup.com/"},
    )
    execution_context = ToolExecutionContext(
        user_id="u1",
        tenant_id="t1",
        conversation_id="c1",
        run_id="r1",
        mode="company_agent",
        settings={},
    )
    state = ExecutionState(execution_context=execution_context)
    outcome = _consume(
        run_guard_checks(
            run_id="r1",
            request=request,
            task_prep=task_prep,
            state=state,
            registry=_RegistryStub("browser.contact_form.send"),
            steps=[step],
            step_cursor=0,
            index=1,
            step_started="2026-03-06T00:00:00+00:00",
            step=step,
            params={"confirmed": True},
            emit_event=emit_event,
            activity_event_factory=activity_event_factory,
        )
    )
    assert outcome.decision == "skip"
    assert state.execution_context.settings.get("__clarification_requested_after_attempt") is None
    assert not any(event.event_type == "llm.clarification_requested" for event in events)


def test_run_guard_checks_emits_deferred_clarification_when_requirements_match_contract_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.services.agent.orchestration.step_execution_sections.guards.run_contract_check_live",
        _fake_contract_gate_missing_delivery_target,
    )
    monkeypatch.setattr(
        "api.services.agent.orchestration.step_execution_sections.guards.build_contract_remediation_steps",
        lambda **_: [],
    )
    events, emit_event, activity_event_factory = _event_factory()
    request = ChatRequest(message="Analyze and send contact form message", agent_mode="company_agent")
    task_prep = _task_prep_with_deferred_missing()
    task_prep.contract_missing_requirements = [
        "Recipient email address for delivery",
        "Provide sender company profile for outreach",
    ]
    task_prep.clarification_questions = [
        "Please provide: Recipient email address for delivery",
        "Please provide: Provide sender company profile for outreach",
    ]
    step = PlannedStep(
        tool_id="browser.contact_form.send",
        title="Send outreach form",
        params={"url": "https://axongroup.com/"},
    )
    execution_context = ToolExecutionContext(
        user_id="u1",
        tenant_id="t1",
        conversation_id="c1",
        run_id="r1",
        mode="company_agent",
        settings={},
    )
    state = ExecutionState(execution_context=execution_context)
    outcome = _consume(
        run_guard_checks(
            run_id="r1",
            request=request,
            task_prep=task_prep,
            state=state,
            registry=_RegistryStub("browser.contact_form.send"),
            steps=[step],
            step_cursor=0,
            index=1,
            step_started="2026-03-06T00:00:00+00:00",
            step=step,
            params={"confirmed": True},
            emit_event=emit_event,
            activity_event_factory=activity_event_factory,
        )
    )
    assert outcome.decision == "skip"
    assert state.execution_context.settings.get("__clarification_requested_after_attempt") is True
    clarification_event = next(
        event for event in events if event.event_type == "llm.clarification_requested"
    )
    assert clarification_event.data.get("missing_requirements") == [
        "Recipient email address for delivery"
    ]


def test_run_guard_checks_defers_discoverable_blocker_until_attempts_exhausted(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.services.agent.orchestration.step_execution_sections.guards.run_contract_check_live",
        _fake_contract_gate_missing_delivery_target,
    )
    monkeypatch.setattr(
        "api.services.agent.orchestration.step_execution_sections.guards.build_contract_remediation_steps",
        lambda **_: [],
    )
    events, emit_event, activity_event_factory = _event_factory()
    request = ChatRequest(message="Analyze and send contact form message", agent_mode="company_agent")
    task_prep = _task_prep_with_deferred_missing()
    task_prep.contract_missing_requirements = ["Recipient email address for delivery"]
    task_prep.contract_missing_slots = [
        {
            "requirement": "Recipient email address for delivery",
            "description": "Recipient email address for delivery",
            "discoverable": True,
            "blocking": True,
            "confidence": 0.8,
            "resolved_value": "",
            "question": "Please provide recipient email",
            "state": "attempting_discovery",
            "attempt_count": 1,
        }
    ]
    step = PlannedStep(
        tool_id="browser.contact_form.send",
        title="Send outreach form",
        params={"url": "https://axongroup.com/"},
    )
    execution_context = ToolExecutionContext(
        user_id="u1",
        tenant_id="t1",
        conversation_id="c1",
        run_id="r1",
        mode="company_agent",
        settings={"__task_clarification_slots": task_prep.contract_missing_slots},
    )
    state = ExecutionState(execution_context=execution_context)
    outcome = _consume(
        run_guard_checks(
            run_id="r1",
            request=request,
            task_prep=task_prep,
            state=state,
            registry=_RegistryStub("browser.contact_form.send"),
            steps=[step],
            step_cursor=0,
            index=1,
            step_started="2026-03-06T00:00:00+00:00",
            step=step,
            params={"confirmed": True},
            emit_event=emit_event,
            activity_event_factory=activity_event_factory,
        )
    )
    assert outcome.decision == "skip"
    assert not any(event.event_type == "llm.clarification_requested" for event in events)
