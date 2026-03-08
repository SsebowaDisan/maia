from __future__ import annotations

from api.schemas import ChatRequest
from api.services.agent.models import AgentAction
from api.services.agent.orchestration.answer_builder import compose_professional_answer


def test_delivery_status_hidden_by_default_for_end_user_response() -> None:
    answer = compose_professional_answer(
        request=ChatRequest(
            message="Send a message via contact form.",
            agent_mode="company_agent",
        ),
        planned_steps=[],
        executed_steps=[],
        actions=[],
        sources=[],
        next_steps=[],
        runtime_settings={},
        verification_report=None,
    )
    assert "## Delivery Status" not in answer
    assert "## Contract Gate" not in answer
    assert "## Verification" not in answer


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
            "__show_response_diagnostics": True,
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
        runtime_settings={"__show_response_diagnostics": True},
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
        runtime_settings={"__show_response_diagnostics": True},
        verification_report=None,
    )
    assert "## Delivery Status" in answer
    assert "- External action: not completed." in answer
    assert "- External action attempt: executed but failed." in answer
    assert "- Tool: `browser.contact_form.send`." in answer


def test_delivery_status_treats_success_as_blocked_when_contract_gate_disallows_external_actions() -> None:
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
        runtime_settings={
            "__show_response_diagnostics": True,
            "__task_contract_check": {
                "ready_for_final_response": False,
                "ready_for_external_actions": False,
                "reason": "Required facts are not yet verified with evidence.",
            }
        },
        verification_report=None,
    )
    assert "## Delivery Status" in answer
    assert "- External action: not completed." in answer
    assert "- External action attempt: executed but blocked by contract gate." in answer
    assert "- Contract gate reason: Required facts are not yet verified with evidence." in answer


def test_delivery_status_truthfulness_ledger_marks_resumed_and_blocked_outcomes() -> None:
    answer = compose_professional_answer(
        request=ChatRequest(
            message="Send update email to the stakeholder.",
            agent_mode="company_agent",
        ),
        planned_steps=[],
        executed_steps=[],
        actions=[
            AgentAction(
                tool_id="mailer.report_send",
                action_class="execute",
                status="success",
                summary="Report sent.",
                started_at="2026-03-06T12:00:00Z",
                ended_at="2026-03-06T12:00:05Z",
            )
        ],
        sources=[],
        next_steps=[],
        runtime_settings={
            "__show_response_diagnostics": True,
            "__task_contract": {"required_actions": ["send_email"]},
            "__task_contract_check": {
                "ready_for_final_response": False,
                "ready_for_external_actions": False,
                "reason": "Post-resume verification pending.",
            },
            "__side_effect_status": {
                "send_email": {
                    "action_key": "send_email",
                    "status": "blocked",
                    "tool_id": "mailer.report_send",
                }
            },
            "__handoff_state": {"state": "resumed"},
        },
        verification_report=None,
    )
    assert "- Truthfulness ledger:" in answer
    assert "`send_email`: attempted=yes" in answer
    assert "blocked=yes" in answer
    assert "resumed=yes" in answer


def test_delivery_status_truthfulness_ledger_marks_required_action_not_attempted() -> None:
    answer = compose_professional_answer(
        request=ChatRequest(
            message="Please submit the contact form.",
            agent_mode="company_agent",
        ),
        planned_steps=[],
        executed_steps=[],
        actions=[],
        sources=[],
        next_steps=[],
        runtime_settings={
            "__show_response_diagnostics": True,
            "__task_contract": {"required_actions": ["submit_contact_form"]},
        },
        verification_report=None,
    )
    assert "- Truthfulness ledger:" in answer
    assert "`submit_contact_form`: attempted=no" in answer
