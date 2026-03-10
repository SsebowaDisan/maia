from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from api.services.agent.models import AgentAction, AgentActivityEvent, new_id
from api.services.agent.orchestration.step_execution_sections import success as success_section
from api.services.agent.planner import PlannedStep
from api.services.agent.tools.base import ToolExecutionContext, ToolExecutionResult


class _RegistryTool:
    def __init__(self, tool_id: str) -> None:
        self._tool_id = tool_id

    def to_action(self, *, status: str, summary: str, started_at: str, metadata: dict[str, Any] | None = None) -> AgentAction:
        return AgentAction(
            tool_id=self._tool_id,
            action_class="read",
            status=status,  # type: ignore[arg-type]
            summary=summary,
            started_at=started_at,
            ended_at=started_at,
            metadata=dict(metadata or {}),
        )


class _Registry:
    def get(self, tool_id: str) -> _RegistryTool:
        return _RegistryTool(tool_id)


def _activity_event_factory(*, event_type: str, title: str, detail: str = "", metadata: dict[str, Any] | None = None, **_: Any) -> AgentActivityEvent:
    return AgentActivityEvent(
        event_id=new_id("evt"),
        run_id="run-1",
        event_type=event_type,
        title=title,
        detail=detail,
        metadata=dict(metadata or {}),
    )


def test_handle_step_success_marks_unavailable_tool_result_as_failed(monkeypatch) -> None:
    monkeypatch.setattr(
        success_section,
        "summarize_step_outcome",
        lambda **kwargs: {"summary": "step summary", "suggestion": ""},
    )

    state = SimpleNamespace(
        execution_context=ToolExecutionContext(
            user_id="u1",
            tenant_id="t1",
            conversation_id="c1",
            run_id="run-1",
            mode="company_agent",
            settings={},
        ),
        all_actions=[],
        all_sources=[],
        executed_steps=[],
        next_steps=[],
        dynamic_inspection_inserted=False,
        research_retry_inserted=False,
        deep_workspace_logging_enabled=False,
        deep_workspace_docs_logging_enabled=False,
        deep_workspace_sheets_logging_enabled=False,
        deep_workspace_warning_emitted=False,
    )
    access_context = SimpleNamespace(access_mode="restricted", full_access_enabled=False)
    result = ToolExecutionResult(
        summary="GA4 data access is blocked by permissions.",
        content="",
        data={"available": False, "error": "ga4_queries_failed"},
        sources=[],
        next_steps=[],
        events=[],
    )
    step = PlannedStep(tool_id="analytics.ga4.full_report", title="Generate Full GA4 Report", params={})

    emitted: list[dict[str, Any]] = []
    generator = success_section.handle_step_success(
        access_context=access_context,
        deep_research_mode=False,
        execution_prompt="ga4 report",
        state=state,
        registry=_Registry(),
        steps=[step],
        step_cursor=0,
        step=step,
        index=1,
        step_started="2026-03-10T00:00:00+00:00",
        duration_seconds=1.0,
        result=result,
        run_tool_live=lambda **kwargs: (_ for _ in ()),  # pragma: no cover - not reached in this path.
        emit_event=lambda event: emitted.append(event.to_dict()) or event.to_dict(),
        activity_event_factory=_activity_event_factory,
    )
    list(generator)

    assert state.all_actions
    assert state.all_actions[0].status == "failed"
    assert state.executed_steps[0]["status"] == "failed"
    assert any(row.get("type") == "tool_failed" for row in emitted)
