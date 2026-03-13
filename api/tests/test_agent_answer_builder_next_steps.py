from __future__ import annotations

from api.schemas import ChatRequest
from api.services.agent.orchestration.answer_builder import compose_professional_answer


def test_recommended_next_steps_hides_internal_install_actions_for_end_users() -> None:
    answer = compose_professional_answer(
        request=ChatRequest(
            message="research uganda and summarize",
            agent_mode="deep_search",
        ),
        planned_steps=[],
        executed_steps=[],
        actions=[],
        sources=[],
        next_steps=[
            "Run `pip install playwright` and then execute `playwright install`.",
            "Validate the key findings with two independent public sources.",
        ],
        runtime_settings={},
        verification_report=None,
    )

    assert "## Recommended Next Steps" in answer
    assert "pip install" not in answer.lower()
    assert "playwright install" not in answer.lower()
    assert "Validate the key findings" in answer


def test_recommended_next_steps_keeps_internal_actions_when_diagnostics_enabled() -> None:
    answer = compose_professional_answer(
        request=ChatRequest(
            message="show debug diagnostics",
            agent_mode="company_agent",
        ),
        planned_steps=[],
        executed_steps=[],
        actions=[],
        sources=[],
        next_steps=[
            "Run `pip install playwright` and then execute `playwright install`.",
            "Validate the key findings with two independent public sources.",
        ],
        runtime_settings={"__show_response_diagnostics": True},
        verification_report=None,
    )

    assert "## Recommended Next Steps" in answer
    assert "pip install" in answer.lower()
    assert "Validate the key findings" in answer


def test_recommended_next_steps_filters_agent_internal_reasoning() -> None:
    """Regression: agent-internal reasoning phrases must not leak into user-visible
    Recommended Next Steps even when __show_response_diagnostics is off."""
    answer = compose_professional_answer(
        request=ChatRequest(
            message="summarize the research",
            agent_mode="deep_search",
        ),
        planned_steps=[],
        executed_steps=[],
        actions=[],
        sources=[],
        next_steps=[
            "Note that the pipeline has semantic understanding constraints.",
            "Be aware that hardcoded words may affect retrieval quality.",
            "Validate findings with two independent sources.",
            "Please note: internal constraint prevents cross-shard lookup.",
        ],
        runtime_settings={},
        verification_report=None,
    )

    # Useful step must survive
    assert "Validate findings" in answer
    # Agent-internal phrases must be stripped
    assert "semantic understanding" not in answer
    assert "hardcoded word" not in answer.lower()
    assert "Note that" not in answer
    assert "Be aware" not in answer
    assert "Please note" not in answer
