from __future__ import annotations

from api.services.agent.orchestration.execution_trace import (
    record_parallel_research_trace,
    record_remediation_trace,
    record_retry_trace,
)
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


def test_record_retry_trace_updates_state_and_settings() -> None:
    state = _state()
    row = record_retry_trace(
        state=state,
        step_index=2,
        tool_id="browser.playwright.inspect",
        reason="net::ERR_CONNECTION_RESET",
        status="started",
    )
    assert row["tool_id"] == "browser.playwright.inspect"
    assert row["status"] == "started"
    assert state.retry_trace
    assert isinstance(state.execution_context.settings.get("__retry_trace"), list)


def test_record_remediation_trace_updates_state_and_settings() -> None:
    state = _state()
    state.remediation_attempts = 1
    row = record_remediation_trace(
        state=state,
        step_index=4,
        blocked_tool_id="email.send",
        inserted_steps=["marketing.web_research", "report.generate"],
        reason="contract_gate_requires_remediation",
    )
    assert row["blocked_tool_id"] == "email.send"
    assert row["attempt"] == 1
    assert row["inserted_tool_ids"] == ["marketing.web_research", "report.generate"]
    assert state.remediation_trace
    assert isinstance(state.execution_context.settings.get("__remediation_trace"), list)


def test_record_parallel_research_trace_updates_state_and_settings() -> None:
    state = _state()
    row = record_parallel_research_trace(
        state=state,
        step_index=3,
        tool_id="marketing.web_research",
        batch_type="adaptive_research_followups",
        inserted_steps=["browser.playwright.inspect", "browser.playwright.inspect"],
        metadata={"inserted": 2},
    )
    assert row["tool_id"] == "marketing.web_research"
    assert row["batch_type"] == "adaptive_research_followups"
    assert len(row["inserted_tool_ids"]) == 2
    assert state.parallel_research_trace
    assert isinstance(state.execution_context.settings.get("__parallel_research_trace"), list)
