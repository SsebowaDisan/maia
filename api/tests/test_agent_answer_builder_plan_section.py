from __future__ import annotations

from api.schemas import ChatRequest
from api.services.agent.orchestration.answer_builder_sections.models import AnswerBuildContext
from api.services.agent.orchestration.answer_builder_sections.plan import append_execution_plan
from api.services.agent.planner import PlannedStep


def _ctx(*, planned_steps: list[PlannedStep], runtime_settings: dict):
    return AnswerBuildContext(
        request=ChatRequest(message="test", agent_mode="company_agent"),
        planned_steps=planned_steps,
        executed_steps=[],
        actions=[],
        sources=[],
        next_steps=[],
        runtime_settings=runtime_settings,
        verification_report=None,
    )


def test_execution_plan_hides_research_blueprint_when_no_research_steps() -> None:
    lines: list[str] = []
    ctx = _ctx(
        planned_steps=[
            PlannedStep(
                tool_id="report.generate",
                title="Generate report",
                params={"summary": "test"},
            )
        ],
        runtime_settings={
            "__research_search_terms": ["what is machine learning"],
            "__research_keywords": ["machine", "learning"],
        },
    )
    append_execution_plan(lines, ctx)
    output = "\n".join(lines)
    assert "## Research Blueprint" not in output


def test_execution_plan_shows_research_blueprint_when_research_steps_exist() -> None:
    lines: list[str] = []
    ctx = _ctx(
        planned_steps=[
            PlannedStep(
                tool_id="marketing.web_research",
                title="Search online sources",
                params={"query": "machine learning overview"},
            )
        ],
        runtime_settings={
            "__research_search_terms": ["machine learning overview"],
            "__research_keywords": ["machine", "learning", "overview"],
        },
    )
    append_execution_plan(lines, ctx)
    output = "\n".join(lines)
    assert "## Research Blueprint" in output
