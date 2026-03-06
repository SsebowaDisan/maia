from __future__ import annotations

from api.schemas import ChatRequest
from api.services.agent.orchestration.answer_builder import compose_professional_answer


def test_answer_builder_includes_simple_explanation_when_requested() -> None:
    answer = compose_professional_answer(
        request=ChatRequest(
            message="Research machine learning and explain it so a 5 year old can understand.",
            agent_mode="company_agent",
        ),
        planned_steps=[],
        executed_steps=[],
        actions=[],
        sources=[],
        next_steps=[],
        runtime_settings={
            "__simple_explanation_required": True,
            "__latest_report_title": "Machine Learning Report",
            "__latest_report_content": "### Executive Summary\nMachine learning finds patterns in data.",
        },
        verification_report=None,
    )
    assert "## Simple Explanation (For a 5-Year-Old)" in answer


def test_answer_builder_hides_execution_trace_when_not_requested() -> None:
    answer = compose_professional_answer(
        request=ChatRequest(message="Research this topic and summarize.", agent_mode="company_agent"),
        planned_steps=[],
        executed_steps=[],
        actions=[],
        sources=[],
        next_steps=[],
        runtime_settings={"__include_execution_why": False},
        verification_report=None,
    )
    assert "## Task Understanding" not in answer
    assert "## Execution Plan" not in answer

