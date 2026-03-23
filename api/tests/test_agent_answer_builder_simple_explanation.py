from __future__ import annotations

from api.schemas import ChatRequest
from api.services.agent.models import AgentSource
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


def test_answer_builder_synthesizes_cited_summary_from_sources(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.services.agent.orchestration.answer_builder_sections.summary.call_text_response",
        lambda **kwargs: (
            "Machine learning has moved from narrow prediction workflows into foundation-model systems used for coding, search, and enterprise automation, "
            "but the strongest evidence still concentrates in benchmarked model quality, infrastructure cost, and governance risk [1][2].\n\n"
            "Recent surveys and benchmark programs show that gains are real but uneven: frontier capability continues to rise, while reproducibility, energy cost, "
            "and evaluation drift remain open constraints for production use [2][3]."
        ),
    )
    answer = compose_professional_answer(
        request=ChatRequest(
            message="Make the research about machine learning and write an email about the research.",
            agent_mode="company_agent",
        ),
        planned_steps=[],
        executed_steps=[],
        actions=[],
        sources=[
            AgentSource(
                source_type="web",
                label="Stanford AI Index 2025",
                url="https://aiindex.stanford.edu/report/",
                metadata={"snippet": "Annual report tracking model capability, cost, investment, and governance."},
            ),
            AgentSource(
                source_type="web",
                label="MLPerf Benchmarks",
                url="https://mlcommons.org/benchmarks/",
                metadata={"snippet": "Benchmark suite covering training and inference performance across model families."},
            ),
            AgentSource(
                source_type="web",
                label="Nature Machine Intelligence review",
                url="https://www.nature.com/",
                metadata={"snippet": "Review article on practical deployment limits, reproducibility, and evaluation."},
            ),
        ],
        next_steps=[],
        runtime_settings={},
        verification_report=None,
    )
    assert "Machine learning has moved" in answer
    assert "[1][2]" in answer
    assert "## Evidence Citations" in answer

