from __future__ import annotations

from types import SimpleNamespace

from api.schemas import ChatRequest
from api.services.agent.orchestration.step_planner_sections import research as research_module
from api.services.agent.orchestration.step_planner_sections.research import (
    build_research_plan,
    ensure_company_agent_highlight_step,
)
from api.services.agent.orchestration.step_planner_sections.intent_enrichment import (
    apply_intent_enrichment,
)
from api.services.agent.orchestration.step_planner_sections.workspace_logging import (
    build_workspace_logging_plan,
    prepend_workspace_roadmap_steps,
)
from api.services.agent.planner import PlannedStep


def _task_prep(*, contract_actions: list[str], intent_tags: tuple[str, ...]):
    return SimpleNamespace(
        contract_actions=contract_actions,
        task_intelligence=SimpleNamespace(intent_tags=intent_tags),
    )


def test_workspace_logging_disabled_by_default_for_company_agent_mode() -> None:
    request = ChatRequest(message="what is machine learning", agent_mode="company_agent")
    task_prep = _task_prep(contract_actions=[], intent_tags=())
    plan = build_workspace_logging_plan(
        request=request,
        settings={},
        task_prep=task_prep,
        deep_research_mode=True,
    )
    assert plan.workspace_logging_requested is False
    assert plan.deep_workspace_logging_enabled is False


def test_workspace_logging_can_be_enabled_for_company_agent_mode_via_setting() -> None:
    request = ChatRequest(message="what is machine learning", agent_mode="company_agent")
    task_prep = _task_prep(contract_actions=[], intent_tags=())
    plan = build_workspace_logging_plan(
        request=request,
        settings={"agent.company_agent_always_workspace_logging": True},
        task_prep=task_prep,
        deep_research_mode=True,
    )
    assert plan.workspace_logging_requested is False
    assert plan.deep_workspace_logging_enabled is True


def test_workspace_logging_enabled_when_update_sheet_requested() -> None:
    request = ChatRequest(message="update this in sheets", agent_mode="company_agent")
    task_prep = _task_prep(contract_actions=["update_sheet"], intent_tags=("sheets_update",))
    plan = build_workspace_logging_plan(
        request=request,
        settings={},
        task_prep=task_prep,
        deep_research_mode=False,
    )
    assert plan.workspace_logging_requested is True
    assert plan.deep_workspace_logging_enabled is True


def test_workspace_logging_can_be_enabled_for_deep_research_via_setting() -> None:
    request = ChatRequest(message="what is machine learning", agent_mode="company_agent")
    task_prep = _task_prep(contract_actions=[], intent_tags=())
    plan = build_workspace_logging_plan(
        request=request,
        settings={"agent.deep_research_workspace_logging": True},
        task_prep=task_prep,
        deep_research_mode=True,
    )
    assert plan.workspace_logging_requested is False
    assert plan.deep_workspace_logging_enabled is True


def test_company_agent_highlight_step_not_inserted_without_signal() -> None:
    request = ChatRequest(message="what is machine learning", agent_mode="company_agent")
    steps = [
        PlannedStep(
            tool_id="report.generate",
            title="Generate report",
            params={"summary": "what is machine learning"},
        )
    ]
    result = ensure_company_agent_highlight_step(
        request=request,
        steps=steps,
        highlight_color="yellow",
        planned_keywords=["machine", "learning"],
    )
    assert all(step.tool_id != "documents.highlight.extract" for step in result)


def test_company_agent_highlight_step_inserted_when_user_requests_highlighting() -> None:
    request = ChatRequest(
        message="highlight copied words from these files and summarize",
        agent_mode="company_agent",
    )
    steps = [
        PlannedStep(
            tool_id="report.generate",
            title="Generate report",
            params={"summary": "highlight copied words"},
        )
    ]
    result = ensure_company_agent_highlight_step(
        request=request,
        steps=steps,
        highlight_color="green",
        planned_keywords=["highlight", "copied words"],
    )
    assert any(step.tool_id == "documents.highlight.extract" for step in result)


def test_build_research_plan_uses_small_keyword_floor_for_simple_question(monkeypatch) -> None:
    captured: dict[str, int] = {}

    def _fake_build_research_blueprint(*, message: str, agent_goal: str | None, min_keywords: int):
        del message, agent_goal
        captured["min_keywords"] = min_keywords
        return {"search_terms": ["what is machine learning"], "keywords": ["machine", "learning"]}

    monkeypatch.setattr(
        research_module,
        "build_research_blueprint",
        _fake_build_research_blueprint,
    )
    _ = build_research_plan(
        request=ChatRequest(message="what is machine learning", agent_mode="company_agent"),
        settings={},
    )
    assert captured["min_keywords"] == 4


def test_intent_enrichment_adds_docs_and_sheets_steps_from_text_when_tags_missing() -> None:
    request = ChatRequest(
        message=(
            "Research online competitors, write findings in Google Docs, and track each task in Google Sheets."
        ),
        agent_mode="company_agent",
    )
    task_prep = _task_prep(contract_actions=[], intent_tags=())
    steps = [
        PlannedStep(tool_id="marketing.web_research", title="Search online sources", params={"query": "x"}),
        PlannedStep(tool_id="report.generate", title="Generate report", params={"summary": "x"}),
    ]
    enriched = apply_intent_enrichment(
        request=request,
        task_prep=task_prep,
        steps=steps,
    )
    tool_ids = [step.tool_id for step in enriched]
    assert "workspace.docs.research_notes" in tool_ids
    assert "workspace.sheets.track_step" in tool_ids
    assert tool_ids[0] == "workspace.sheets.track_step"


def test_workspace_roadmap_steps_marked_for_optional_skip() -> None:
    request = ChatRequest(message="Research online", agent_mode="company_agent")
    task_prep = _task_prep(contract_actions=[], intent_tags=())
    steps = [
        PlannedStep(tool_id="marketing.web_research", title="Search online sources", params={"query": "x"}),
        PlannedStep(tool_id="report.generate", title="Generate report", params={"summary": "x"}),
    ]
    with_roadmap = prepend_workspace_roadmap_steps(
        request=request,
        task_prep=task_prep,
        steps=steps,
        planned_search_terms=["research online"],
        planned_keywords=["research", "online"],
    )
    roadmap_only = [step for step in with_roadmap if step.tool_id == "workspace.sheets.track_step"]
    assert roadmap_only
    assert all(bool(step.params.get("__workspace_logging_step")) for step in roadmap_only)
