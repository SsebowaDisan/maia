from __future__ import annotations

from api.schemas import ChatRequest
from api.services.agent.models import AgentAction
from api.services.agent.orchestration.answer_builder import compose_professional_answer


def test_delivery_status_highlights_required_external_action_when_missing() -> None:
    answer = compose_professional_answer(
        request=ChatRequest(
            message="Open the site and send a message via their contact form.",
            agent_mode="company_agent",
        ),
        planned_steps=[],
        executed_steps=[],
        actions=[],
        sources=[],
        next_steps=[],
        runtime_settings={
            "__task_contract": {
                "required_actions": ["submit_contact_form"],
            }
        },
        verification_report=None,
    )
    assert "## Delivery Status" in answer
    assert "Required external actions: submit_contact_form." in answer
    assert "No email delivery requested." not in answer


def test_delivery_status_reports_contact_form_success_as_external_action() -> None:
    answer = compose_professional_answer(
        request=ChatRequest(
            message="Send a message via contact form.",
            agent_mode="company_agent",
        ),
        planned_steps=[],
        executed_steps=[],
        actions=[
            AgentAction(
                tool_id="browser.contact_form.send",
                action_class="execute",
                status="success",
                summary="Contact form submitted successfully.",
                started_at="2026-03-06T12:00:00Z",
                ended_at="2026-03-06T12:00:05Z",
            )
        ],
        sources=[],
        next_steps=[],
        runtime_settings={},
        verification_report=None,
    )
    assert "## Delivery Status" in answer
    assert "- External action: completed." in answer
    assert "- External action attempt: executed successfully." in answer
    assert "- Tool: `browser.contact_form.send`." in answer


def test_delivery_status_reports_contact_form_failure_as_attempted_but_failed() -> None:
    answer = compose_professional_answer(
        request=ChatRequest(
            message="Send a message via contact form.",
            agent_mode="company_agent",
        ),
        planned_steps=[],
        executed_steps=[],
        actions=[
            AgentAction(
                tool_id="browser.contact_form.send",
                action_class="execute",
                status="failed",
                summary="Submission failed: telephone number is required.",
                started_at="2026-03-06T12:00:00Z",
                ended_at="2026-03-06T12:00:05Z",
            )
        ],
        sources=[],
        next_steps=[],
        runtime_settings={},
        verification_report=None,
    )
    assert "## Delivery Status" in answer
    assert "- External action: not completed." in answer
    assert "- External action attempt: executed but failed." in answer
    assert "- Tool: `browser.contact_form.send`." in answer
