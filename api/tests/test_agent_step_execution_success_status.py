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


def test_handle_step_success_skips_browser_followups_for_standard_overview_runs(monkeypatch) -> None:
    monkeypatch.setattr(
        success_section,
        "summarize_step_outcome",
        lambda **kwargs: {"summary": "web research completed", "suggestion": ""},
    )
    monkeypatch.setattr(
        success_section,
        "run_workspace_shadow_logging",
        lambda **kwargs: iter(()),
    )

    state = SimpleNamespace(
        execution_context=ToolExecutionContext(
            user_id="u1",
            tenant_id="t1",
            conversation_id="c1",
            run_id="run-1",
            mode="company_agent",
            settings={
                "__research_depth_tier": "standard",
                "__research_branching_mode": "overview",
                "__research_max_live_inspections": 3,
            },
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
        parallel_research_trace=[],
        retry_trace=[],
        remediation_trace=[],
    )
    access_context = SimpleNamespace(access_mode="restricted", full_access_enabled=False)
    step = PlannedStep(
        tool_id="marketing.web_research",
        title="Search online sources",
        params={"query": "machine learning overview authoritative source"},
    )
    result = ToolExecutionResult(
        summary="Collected 12 source-backed results.",
        content="",
        data={
            "coverage_ok": True,
            "items": [
                {"label": "Source A", "url": "https://example.com/a"},
                {"label": "Source B", "url": "https://example.com/b.pdf"},
            ],
        },
        sources=[],
        next_steps=[],
        events=[],
    )
    steps = [step, PlannedStep(tool_id="report.generate", title="Generate report", params={})]
    emitted: list[dict[str, Any]] = []

    list(
        success_section.handle_step_success(
            access_context=access_context,
            deep_research_mode=False,
            execution_prompt="make the research about machine learning and write an email about the research",
            state=state,
            registry=_Registry(),
            steps=steps,
            step_cursor=0,
            step=step,
            index=1,
            step_started="2026-03-22T00:00:00+00:00",
            duration_seconds=2.0,
            result=result,
            run_tool_live=lambda **kwargs: (_ for _ in ()),
            emit_event=lambda event: emitted.append(event.to_dict()) or event.to_dict(),
            activity_event_factory=_activity_event_factory,
        )
    )

    assert [planned.tool_id for planned in steps] == ["marketing.web_research", "report.generate"]
    assert state.dynamic_inspection_inserted is False
    assert not any(row.get("type") == "plan_refined" for row in emitted)


def test_handle_step_success_skips_standard_coverage_retry_followups(monkeypatch) -> None:
    monkeypatch.setattr(
        success_section,
        "summarize_step_outcome",
        lambda **kwargs: {"summary": "web research completed", "suggestion": ""},
    )
    monkeypatch.setattr(
        success_section,
        "run_workspace_shadow_logging",
        lambda **kwargs: iter(()),
    )

    state = SimpleNamespace(
        execution_context=ToolExecutionContext(
            user_id="u1",
            tenant_id="t1",
            conversation_id="c1",
            run_id="run-1",
            mode="company_agent",
            settings={
                "__research_depth_tier": "standard",
                "__research_branching_mode": "overview",
                "__research_max_live_inspections": 3,
            },
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
        parallel_research_trace=[],
        retry_trace=[],
        remediation_trace=[],
    )
    access_context = SimpleNamespace(access_mode="restricted", full_access_enabled=False)
    step = PlannedStep(
        tool_id="marketing.web_research",
        title="Search online sources",
        params={"query": "machine learning overview authoritative source"},
    )
    result = ToolExecutionResult(
        summary="Collected 36 source-backed results.",
        content="",
        data={
            "coverage_ok": False,
            "items": [
                {"label": "Source A", "url": "https://example.com/a"},
                {"label": "Source B", "url": "https://example.com/b.pdf"},
            ],
        },
        sources=[],
        next_steps=[],
        events=[],
    )
    steps = [step, PlannedStep(tool_id="report.generate", title="Generate report", params={})]

    list(
        success_section.handle_step_success(
            access_context=access_context,
            deep_research_mode=False,
            execution_prompt="make the research about machine learning and write an email about the research",
            state=state,
            registry=_Registry(),
            steps=steps,
            step_cursor=0,
            step=step,
            index=1,
            step_started="2026-03-22T00:00:00+00:00",
            duration_seconds=2.0,
            result=result,
            run_tool_live=lambda **kwargs: (_ for _ in ()),
            emit_event=lambda event: event.to_dict(),
            activity_event_factory=_activity_event_factory,
        )
    )

    assert [planned.tool_id for planned in steps] == ["marketing.web_research", "report.generate"]
    assert state.research_retry_inserted is False


def test_handle_step_success_keeps_browser_followups_for_deep_runs(monkeypatch) -> None:
    monkeypatch.setattr(
        success_section,
        "summarize_step_outcome",
        lambda **kwargs: {"summary": "web research completed", "suggestion": ""},
    )
    monkeypatch.setattr(
        success_section,
        "run_workspace_shadow_logging",
        lambda **kwargs: iter(()),
    )

    state = SimpleNamespace(
        execution_context=ToolExecutionContext(
            user_id="u1",
            tenant_id="t1",
            conversation_id="c1",
            run_id="run-1",
            mode="deep_search",
            settings={
                "__research_depth_tier": "deep_research",
                "__research_branching_mode": "segmented",
                "__research_max_live_inspections": 2,
            },
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
        parallel_research_trace=[],
        retry_trace=[],
        remediation_trace=[],
    )
    access_context = SimpleNamespace(access_mode="restricted", full_access_enabled=False)
    step = PlannedStep(
        tool_id="marketing.web_research",
        title="Search online sources",
        params={"query": "machine learning benchmarks"},
    )
    result = ToolExecutionResult(
        summary="Collected 20 source-backed results.",
        content="",
        data={
            "coverage_ok": True,
            "items": [
                {"label": "Research PDF", "url": "https://example.com/paper.pdf"},
                {"label": "Website article", "url": "https://example.com/article"},
            ],
        },
        sources=[],
        next_steps=[],
        events=[],
    )
    steps = [step, PlannedStep(tool_id="report.generate", title="Generate report", params={})]
    emitted: list[dict[str, Any]] = []

    list(
        success_section.handle_step_success(
            access_context=access_context,
            deep_research_mode=True,
            execution_prompt="deeply research machine learning benchmarks",
            state=state,
            registry=_Registry(),
            steps=steps,
            step_cursor=0,
            step=step,
            index=1,
            step_started="2026-03-22T00:00:00+00:00",
            duration_seconds=2.0,
            result=result,
            run_tool_live=lambda **kwargs: (_ for _ in ()),
            emit_event=lambda event: emitted.append(event.to_dict()) or event.to_dict(),
            activity_event_factory=_activity_event_factory,
        )
    )

    assert [planned.tool_id for planned in steps][:3] == [
        "marketing.web_research",
        "browser.playwright.inspect",
        "browser.playwright.inspect",
    ]
    assert state.dynamic_inspection_inserted is True
    assert any(row.get("type") == "plan_refined" for row in emitted)


def test_handle_step_success_research_retry_uses_stage_topic_not_execution_contract(monkeypatch) -> None:
    monkeypatch.setattr(
        success_section,
        "summarize_step_outcome",
        lambda **kwargs: {"summary": "web research completed", "suggestion": ""},
    )
    monkeypatch.setattr(
        success_section,
        "run_workspace_shadow_logging",
        lambda **kwargs: iter(()),
    )

    state = SimpleNamespace(
        execution_context=ToolExecutionContext(
            user_id="u1",
            tenant_id="t1",
            conversation_id="c1",
            run_id="run-1",
            mode="deep_search",
            settings={
                "__research_depth_tier": "deep_research",
                "__research_branching_mode": "segmented",
                "__research_max_live_inspections": 2,
                "__workflow_stage_primary_topic": "machine learning",
                "__research_search_terms": ["machine learning", "machine learning enterprise adoption"],
            },
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
        parallel_research_trace=[],
        retry_trace=[],
        remediation_trace=[],
    )
    access_context = SimpleNamespace(access_mode="restricted", full_access_enabled=False)
    step = PlannedStep(
        tool_id="marketing.web_research",
        title="Search online sources",
        params={"query": "machine learning overview authoritative source"},
    )
    result = ToolExecutionResult(
        summary="Collected 8 source-backed results.",
        content="",
        data={
            "coverage_ok": False,
            "items": [{"label": "Source A", "url": "https://example.com/a"}],
        },
        sources=[],
        next_steps=[],
        events=[],
    )
    steps = [step, PlannedStep(tool_id="report.generate", title="Generate report", params={})]

    list(
        success_section.handle_step_success(
            access_context=access_context,
            deep_research_mode=True,
            execution_prompt=(
                "Each inline citation marker [n] must resolve to exactly one numbered row in the "
                "Evidence Citations section."
            ),
            state=state,
            registry=_Registry(),
            steps=steps,
            step_cursor=0,
            step=step,
            index=1,
            step_started="2026-03-22T00:00:00+00:00",
            duration_seconds=2.0,
            result=result,
            run_tool_live=lambda **kwargs: (_ for _ in ()),
            emit_event=lambda event: event.to_dict(),
            activity_event_factory=_activity_event_factory,
        )
    )

    assert len(steps) >= 2
    retry_step = steps[1]
    assert retry_step.tool_id == "marketing.web_research"
    assert retry_step.params["query"] == "machine learning official report filetype:pdf"


def test_handle_step_success_filters_inserted_followups_by_explicit_allowlist(monkeypatch) -> None:
    monkeypatch.setattr(
        success_section,
        "summarize_step_outcome",
        lambda **kwargs: {"summary": "web research completed", "suggestion": ""},
    )
    monkeypatch.setattr(
        success_section,
        "run_workspace_shadow_logging",
        lambda **kwargs: iter(()),
    )

    state = SimpleNamespace(
        execution_context=ToolExecutionContext(
            user_id="u1",
            tenant_id="t1",
            conversation_id="c1",
            run_id="run-1",
            mode="deep_search",
            settings={
                "__research_depth_tier": "deep_research",
                "__research_branching_mode": "segmented",
                "__research_max_live_inspections": 2,
                "__allowed_tool_ids": ["marketing.web_research", "web.extract.structured"],
            },
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
        parallel_research_trace=[],
        retry_trace=[],
        remediation_trace=[],
    )
    access_context = SimpleNamespace(access_mode="restricted", full_access_enabled=False)
    step = PlannedStep(
        tool_id="marketing.web_research",
        title="Search online sources",
        params={"query": "machine learning benchmarks"},
    )
    result = ToolExecutionResult(
        summary="Collected 20 source-backed results.",
        content="",
        data={
            "coverage_ok": True,
            "items": [
                {"label": "Research PDF", "url": "https://example.com/paper.pdf"},
                {"label": "Website article", "url": "https://example.com/article"},
            ],
        },
        sources=[],
        next_steps=[],
        events=[],
    )
    steps = [step, PlannedStep(tool_id="report.generate", title="Generate report", params={})]

    list(
        success_section.handle_step_success(
            access_context=access_context,
            deep_research_mode=True,
            execution_prompt="deeply research machine learning benchmarks",
            state=state,
            registry=_Registry(),
            steps=steps,
            step_cursor=0,
            step=step,
            index=1,
            step_started="2026-03-22T00:00:00+00:00",
            duration_seconds=2.0,
            result=result,
            run_tool_live=lambda **kwargs: (_ for _ in ()),
            emit_event=lambda event: event.to_dict(),
            activity_event_factory=_activity_event_factory,
        )
    )

    assert [planned.tool_id for planned in steps] == [
        "marketing.web_research",
        "report.generate",
    ]
    assert state.dynamic_inspection_inserted is False


def test_handle_step_success_skips_live_source_followups_for_standard_explicit_scope(monkeypatch) -> None:
    monkeypatch.setattr(
        success_section,
        "summarize_step_outcome",
        lambda **kwargs: {"summary": "web research completed", "suggestion": ""},
    )
    monkeypatch.setattr(
        success_section,
        "run_workspace_shadow_logging",
        lambda **kwargs: iter(()),
    )

    state = SimpleNamespace(
        execution_context=ToolExecutionContext(
            user_id="u1",
            tenant_id="t1",
            conversation_id="c1",
            run_id="run-1",
            mode="company_agent",
            settings={
                "__research_depth_tier": "standard",
                "__research_branching_mode": "segmented",
                "__research_max_live_inspections": 8,
                "__allowed_tool_ids": [
                    "marketing.web_research",
                    "web.extract.structured",
                    "browser.playwright.inspect",
                ],
            },
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
        parallel_research_trace=[],
        retry_trace=[],
        remediation_trace=[],
    )
    access_context = SimpleNamespace(access_mode="restricted", full_access_enabled=False)
    step = PlannedStep(
        tool_id="marketing.web_research",
        title="Search online sources",
        params={"query": "machine learning benchmarks"},
    )
    result = ToolExecutionResult(
        summary="Collected 20 source-backed results.",
        content="",
        data={
            "coverage_ok": True,
            "items": [
                {"label": "Research PDF", "url": "https://example.com/paper.pdf"},
                {"label": "Website article", "url": "https://example.com/article"},
            ],
        },
        sources=[],
        next_steps=[],
        events=[],
    )
    steps = [step, PlannedStep(tool_id="report.generate", title="Generate report", params={})]

    list(
        success_section.handle_step_success(
            access_context=access_context,
            deep_research_mode=False,
            execution_prompt="research machine learning and email the result",
            state=state,
            registry=_Registry(),
            steps=steps,
            step_cursor=0,
            step=step,
            index=1,
            step_started="2026-03-22T00:00:00+00:00",
            duration_seconds=2.0,
            result=result,
            run_tool_live=lambda **kwargs: (_ for _ in ()),
            emit_event=lambda event: event.to_dict(),
            activity_event_factory=_activity_event_factory,
        )
    )

    assert [planned.tool_id for planned in steps] == [
        "marketing.web_research",
        "report.generate",
    ]
    assert state.dynamic_inspection_inserted is False
