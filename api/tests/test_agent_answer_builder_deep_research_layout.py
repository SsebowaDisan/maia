from __future__ import annotations

from api.schemas import ChatRequest
from api.services.agent.orchestration.answer_builder import compose_professional_answer


def test_deep_research_response_leads_with_report_and_hides_diagnostics_by_default() -> None:
    answer = compose_professional_answer(
        request=ChatRequest(message="make research about uganda", agent_mode="deep_search"),
        planned_steps=[],
        executed_steps=[
            {
                "step": 1,
                "tool_id": "marketing.web_research",
                "title": "Collect sources",
                "status": "success",
                "summary": "Collected source coverage",
            }
        ],
        actions=[],
        sources=[],
        next_steps=["Validate macroeconomic section with one additional source."],
        runtime_settings={
            "__research_depth_tier": "deep_research",
            "__latest_report_content": (
                "## Uganda Research Report\n"
                "### Executive Summary\n"
                "Uganda is a landlocked East African country with a young population.\n\n"
                "### Detailed Analysis\n"
                "Economy, geography, and social indicators are summarized from external sources."
            ),
            "__include_execution_why": True,
        },
        verification_report={
            "score": 88.0,
            "grade": "strong",
            "checks": [{"name": "Source grounding", "status": "pass", "detail": "Strong"}],
        },
    )

    assert "## Detailed Research Report" in answer
    assert "### Executive Summary" in answer
    assert "## Key Findings" not in answer
    assert "## Delivery Status" not in answer
    assert "## Contract Gate" not in answer
    assert "## Verification" not in answer
    assert "## Task Understanding" not in answer
    assert "## Execution Plan" not in answer
    assert "## Execution Summary" not in answer


def test_deep_research_response_can_include_diagnostics_when_explicitly_enabled() -> None:
    answer = compose_professional_answer(
        request=ChatRequest(message="make research about uganda", agent_mode="deep_search"),
        planned_steps=[],
        executed_steps=[
            {
                "step": 1,
                "tool_id": "marketing.web_research",
                "title": "Collect sources",
                "status": "success",
                "summary": "Collected source coverage",
            }
        ],
        actions=[],
        sources=[],
        next_steps=[],
        runtime_settings={
            "__research_depth_tier": "deep_research",
            "__latest_report_content": "## Uganda Research Report\n### Executive Summary\nSummary text.",
            "__show_response_diagnostics": True,
            "__include_execution_why": True,
        },
        verification_report={
            "score": 80.0,
            "grade": "fair",
            "checks": [{"name": "Source grounding", "status": "pass", "detail": "Strong"}],
        },
    )

    assert "## Detailed Research Report" in answer
    assert "## Verification" in answer
    assert "## Task Understanding" in answer
    assert "## Execution Plan" in answer


def test_deep_research_response_strips_operational_sections_from_report_content() -> None:
    answer = compose_professional_answer(
        request=ChatRequest(message="make research about uganda", agent_mode="deep_search"),
        planned_steps=[],
        executed_steps=[],
        actions=[],
        sources=[],
        next_steps=[],
        runtime_settings={
            "__research_depth_tier": "deep_research",
            "__latest_report_content": (
                "## Key Findings\n"
                "- noisy ops section\n\n"
                "## Detailed Research Report\n"
                "### Executive Summary\n"
                "Uganda overview.\n\n"
                "### Detailed Analysis\n"
                "Real analysis.\n\n"
                "## Delivery Status\n"
                "- No email\n\n"
                "## Contract Gate\n"
                "- Final response ready: no."
            ),
        },
        verification_report=None,
    )

    assert "## Detailed Research Report" in answer
    assert "### Executive Summary" in answer
    assert "### Detailed Analysis" in answer
    assert "noisy ops section" not in answer
    assert "## Delivery Status" not in answer
