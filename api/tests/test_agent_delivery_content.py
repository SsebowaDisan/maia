from __future__ import annotations

from api.schemas import ChatRequest
from api.services.agent.intelligence_sections.models import TaskIntelligence
from api.services.agent.models import AgentActivityEvent
from api.services.agent.orchestration.delivery_sections.decisioning import prepare_delivery_content
from api.services.agent.orchestration.models import ExecutionState, TaskPreparation
from api.services.agent.orchestration.delivery_sections.models import DeliveryRuntime
from api.services.agent.tools.base import ToolExecutionContext


def _task_prep() -> TaskPreparation:
    return TaskPreparation(
        task_intelligence=TaskIntelligence(
            objective="Research machine learning and deliver findings by email.",
            target_url="",
            target_host="",
            delivery_email="recipient@example.com",
            requires_delivery=True,
            requires_web_inspection=False,
            requested_report=True,
            preferred_tone="professional",
            intent_tags=("report_generation", "email_delivery"),
        ),
        user_preferences={},
        research_depth_profile={},
        conversation_summary="",
        rewritten_task="Research machine learning and deliver findings by email.",
        planned_deliverables=[],
        planned_constraints=[],
        task_contract={},
        contract_objective="",
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


def _state() -> ExecutionState:
    context = ToolExecutionContext(
        user_id="u1",
        tenant_id="t1",
        conversation_id="c1",
        run_id="run-1",
        mode="company_agent",
        settings={},
    )
    state = ExecutionState(execution_context=context)
    state.executed_steps.append(
        {
            "step": 1,
            "tool_id": "marketing.web_research",
            "title": "Research machine learning",
            "status": "success",
            "summary": "Collected primary definitions and practical examples.",
        }
    )
    return state


def _event_factory(**kwargs) -> AgentActivityEvent:
    return AgentActivityEvent(
        event_id="evt_test",
        run_id="run-1",
        event_type=str(kwargs.get("event_type") or "info"),
        title=str(kwargs.get("title") or ""),
        detail=str(kwargs.get("detail") or ""),
        metadata=kwargs.get("metadata") if isinstance(kwargs.get("metadata"), dict) else {},
    )


def test_prepare_delivery_content_uses_llm_draft_when_report_missing(monkeypatch) -> None:
    state = _state()
    task_prep = _task_prep()
    runtime = DeliveryRuntime(step=1, started_at="2026-03-07T00:00:00Z")

    monkeypatch.setattr(
        "api.services.agent.orchestration.delivery_sections.decisioning.draft_delivery_report_content",
        lambda **kwargs: {
            "subject": "Machine Learning Research Report",
            "body_text": (
                "## Executive Summary\n\n"
                "Machine learning is a branch of AI that learns from data.\n\n"
                "## Detailed Analysis\n\n"
                "This report covers core concepts and business applications."
            ),
        },
    )
    monkeypatch.setattr(
        "api.services.agent.orchestration.delivery_sections.decisioning.polish_email_content",
        lambda **kwargs: {"subject": kwargs.get("subject", ""), "body_text": kwargs.get("body_text", "")},
    )

    report_title, report_body, pre_send_events = prepare_delivery_content(
        request=ChatRequest(
            message="what is machine learning, make research about it and then send an email to recipient@example.com",
            agent_mode="company_agent",
        ),
        task_prep=task_prep,
        state=state,
        runtime=runtime,
        activity_event_factory=_event_factory,
    )

    assert report_title == "Machine Learning Research Report"
    assert report_body.startswith("## Executive Summary")
    assert "No dedicated report draft was generated" not in report_body
    assert pre_send_events == []
    assert state.execution_context.settings.get("__latest_report_content") == report_body


def test_prepare_delivery_content_uses_existing_report_body_without_draft_fallback(monkeypatch) -> None:
    state = _state()
    state.execution_context.settings["__latest_report_title"] = "Existing Report"
    state.execution_context.settings["__latest_report_content"] = "## Executive Summary\n\nExisting report body."
    task_prep = _task_prep()
    runtime = DeliveryRuntime(step=1, started_at="2026-03-07T00:00:00Z")

    monkeypatch.setattr(
        "api.services.agent.orchestration.delivery_sections.decisioning.draft_delivery_report_content",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("should not be called")),
    )
    monkeypatch.setattr(
        "api.services.agent.orchestration.delivery_sections.decisioning.polish_email_content",
        lambda **kwargs: {"subject": kwargs.get("subject", ""), "body_text": kwargs.get("body_text", "")},
    )

    report_title, report_body, _ = prepare_delivery_content(
        request=ChatRequest(message="send report", agent_mode="company_agent"),
        task_prep=task_prep,
        state=state,
        runtime=runtime,
        activity_event_factory=_event_factory,
    )

    assert report_title == "Existing Report"
    assert report_body == "## Executive Summary\n\nExisting report body."
