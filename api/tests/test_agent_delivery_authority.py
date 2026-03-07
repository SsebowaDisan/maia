from __future__ import annotations

from types import SimpleNamespace

from api.services.agent.contract_verification import build_deterministic_contract_check
from api.services.agent.orchestration.delivery_sections.decisioning import should_attempt_delivery
from api.services.agent.orchestration.models import ExecutionState
from api.services.agent.tools.base import ToolExecutionContext


def _state() -> ExecutionState:
    context = ToolExecutionContext(
        user_id="u1",
        tenant_id="t1",
        conversation_id="c1",
        run_id="run-1",
        mode="company_agent",
        settings={},
    )
    return ExecutionState(execution_context=context)


def test_contract_check_uses_failed_side_effect_as_authoritative_blocker() -> None:
    check = build_deterministic_contract_check(
        contract={
            "required_actions": ["send_email"],
            "required_facts": [],
            "delivery_target": "recipient@example.com",
        },
        request_message="Send report to recipient@example.com",
        executed_steps=[],
        actions=[],
        report_body="Final report body",
        sources=[],
        allowed_tool_ids=["gmail.draft", "marketing.web_research"],
        side_effect_status={
            "send_email": {"status": "failed", "tool_id": "mailer.report_send"},
        },
    )
    assert check["ready_for_external_actions"] is False
    assert check["ready_for_final_response"] is False
    assert any(
        "External action failed: send_email (failed)" in str(item)
        for item in check["missing_items"]
    )


def test_contract_check_allows_completed_side_effect_without_success_action_row() -> None:
    check = build_deterministic_contract_check(
        contract={
            "required_actions": ["send_email"],
            "required_facts": [],
            "delivery_target": "recipient@example.com",
        },
        request_message="Send report to recipient@example.com",
        executed_steps=[],
        actions=[],
        report_body="Final report body",
        sources=[],
        allowed_tool_ids=["gmail.draft", "marketing.web_research"],
        side_effect_status={
            "send_email": {"status": "completed", "tool_id": "mailer.report_send"},
        },
    )
    assert check["ready_for_external_actions"] is True
    assert check["ready_for_final_response"] is True
    assert not check["missing_items"]


def test_should_attempt_delivery_respects_side_effect_status() -> None:
    state = _state()
    state.execution_context.settings["__side_effect_status"] = {
        "send_email": {"status": "completed"}
    }
    task_prep = SimpleNamespace(
        clarification_blocked=False,
        task_intelligence=SimpleNamespace(
            requires_delivery=True,
            delivery_email="recipient@example.com",
        ),
    )
    assert should_attempt_delivery(task_prep=task_prep, state=state) is False

    state.execution_context.settings["__side_effect_status"] = {}
    assert should_attempt_delivery(task_prep=task_prep, state=state) is True
