from __future__ import annotations

from api.services.agent.models import AgentActivityEvent
from api.services.agent.orchestration.contract_gate import run_contract_check_live
from api.services.agent.tools.base import ToolExecutionContext


def _activity_event_factory(**kwargs) -> AgentActivityEvent:
    return AgentActivityEvent(
        event_id=f"evt_{kwargs.get('event_type', 'event')}",
        run_id="run-1",
        event_type=str(kwargs.get("event_type") or ""),
        title=str(kwargs.get("title") or ""),
        detail=str(kwargs.get("detail") or ""),
        metadata=dict(kwargs.get("metadata") or {}),
        data=dict(kwargs.get("metadata") or {}),
        stage=str(kwargs.get("stage") or "tool"),
        status=str(kwargs.get("status") or "info"),
    )


def test_run_contract_check_live_respects_explicit_allowed_tool_scope(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def _fake_verify_task_contract_fulfillment(**kwargs):
        allowed_tool_ids = kwargs.get("allowed_tool_ids") or []
        observed["allowed_tool_ids"] = allowed_tool_ids
        remediation = []
        if "browser.playwright.inspect" in allowed_tool_ids:
            remediation.append(
                {
                    "tool_id": "browser.playwright.inspect",
                    "title": "Inspect site for missing facts",
                    "params": {"url": "https://example.com"},
                }
            )
        if "marketing.web_research" in allowed_tool_ids:
            remediation.append(
                {
                    "tool_id": "marketing.web_research",
                    "title": "Research missing facts",
                    "params": {"query": "machine learning definition"},
                }
            )
        return {
            "ready_for_final_response": False,
            "ready_for_external_actions": False,
            "missing_items": ["Unverified required fact: machine learning definition"],
            "reason": "Need more evidence.",
            "recommended_remediation": remediation,
        }

    monkeypatch.setattr(
        "api.services.agent.orchestration.contract_gate.verify_task_contract_fulfillment",
        _fake_verify_task_contract_fulfillment,
    )

    context = ToolExecutionContext(
        user_id="user-1",
        tenant_id="tenant-1",
        conversation_id="conv-1",
        run_id="run-1",
        mode="company_agent",
        settings={"__allowed_tool_ids": ["marketing.web_research", "web.extract.structured"]},
    )
    emitted: list[dict[str, object]] = []

    generator = run_contract_check_live(
        run_id="run-1",
        phase="before_final_response",
        task_contract={"required_facts": ["machine learning definition"]},
        request_message="Research machine learning",
        execution_context=context,
        executed_steps=[],
        actions=[],
        sources=[],
        emit_event=lambda event: emitted.append(event.to_dict()) or event.to_dict(),
        activity_event_factory=_activity_event_factory,
    )
    while True:
        try:
            next(generator)
        except StopIteration as stop:
            result = stop.value
            break

    assert observed["allowed_tool_ids"] == ["marketing.web_research", "web.extract.structured"]
    assert result["recommended_remediation"] == [
        {
            "tool_id": "marketing.web_research",
            "title": "Research missing facts",
            "params": {"query": "machine learning definition"},
        },
    ]
    assert any(row.get("event_type") == "llm.delivery_check_failed" for row in emitted)
