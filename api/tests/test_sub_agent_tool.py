from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.services.agent.tools.base import ToolExecutionContext, ToolExecutionError
from api.services.agent.tools.sub_agent_tool import SubAgentDelegateTool


def _context() -> ToolExecutionContext:
    return ToolExecutionContext(
        user_id="user_1",
        tenant_id="tenant_1",
        conversation_id="conv_1",
        run_id="run_1",
        mode="company_agent",
        settings={},
    )


def test_delegate_tool_auto_resolves_child_agent_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.services.agents.definition_store.list_agents",
        lambda tenant_id: [
            SimpleNamespace(agent_id="writer", name="Writer"),
            SimpleNamespace(agent_id="researcher", name="Researcher"),
        ],
    )
    monkeypatch.setattr(
        "api.services.agents.orchestrator.delegate_to_agent",
        lambda **kwargs: {
            "success": True,
            "result": "Collected research findings.",
            "child_run_id": "child_run_1",
        },
    )

    tool = SubAgentDelegateTool()
    result = tool.execute(
        context=_context(),
        prompt="Research machine learning and gather reliable sources.",
        params={"task": "Research machine learning and gather reliable sources."},
    )

    assert result.data.get("child_agent_id") == "researcher"
    assert "Collected research findings." in result.content


def test_delegate_tool_still_errors_when_no_child_can_be_resolved(monkeypatch) -> None:
    monkeypatch.setattr("api.services.agents.definition_store.list_agents", lambda tenant_id: [])

    tool = SubAgentDelegateTool()
    with pytest.raises(ToolExecutionError, match="could not be auto-resolved"):
        tool.execute(
            context=_context(),
            prompt="Research machine learning",
            params={"task": "Research machine learning"},
        )
