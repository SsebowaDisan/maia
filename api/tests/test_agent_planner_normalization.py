from __future__ import annotations

from types import SimpleNamespace

from api.schemas import ChatRequest
from api.services.agent.orchestration.models import TaskPreparation
from api.services.agent.orchestration.step_planner_sections.contracts import (
    enforce_contract_synthesis_step,
)
from api.services.agent.planner_models import PlannedStep
from api.services.agent.planner_normalization import normalize_steps


def _request(message: str) -> ChatRequest:
    return ChatRequest(message=message, agent_goal="", conversation_id="test")


def test_normalize_steps_drops_placeholder_extract_urls_for_online_research() -> None:
    request = _request("Research machine learning and email the findings.")
    steps = [
        PlannedStep(
            tool_id="marketing.web_research",
            title="Search web sources",
            params={"query": "machine learning overview"},
        ),
        PlannedStep(
            tool_id="web.extract.structured",
            title="Extract combined source insights",
            params={"url": "https://example.com/machine-learning-hybrid-source"},
        ),
    ]

    normalized = normalize_steps(
        request,
        steps,
        intent={"routing_mode": "online_research"},
        web_routing={"routing_mode": "online_research"},
        deep_research_mode=False,
        company_agent_mode=False,
    )

    assert [step.tool_id for step in normalized] == ["marketing.web_research"]


def test_normalize_steps_drops_placeholder_extract_source_urls_for_online_research() -> None:
    request = _request("Research machine learning and email the findings.")
    steps = [
        PlannedStep(
            tool_id="marketing.web_research",
            title="Search web sources",
            params={"query": "machine learning overview"},
        ),
        PlannedStep(
            tool_id="web.extract.structured",
            title="Extract combined source insights",
            params={
                "source_urls": [
                    "https://example.com/industry_report",
                    "https://example.org/academic_paper",
                ]
            },
        ),
    ]

    normalized = normalize_steps(
        request,
        steps,
        intent={"routing_mode": "online_research"},
        web_routing={"routing_mode": "online_research"},
        deep_research_mode=False,
        company_agent_mode=False,
    )

    assert [step.tool_id for step in normalized] == ["marketing.web_research"]


def test_normalize_steps_promotes_first_real_source_url_for_structured_extract() -> None:
    request = _request("Research machine learning and summarize the findings.")
    steps = [
        PlannedStep(
            tool_id="web.extract.structured",
            title="Extract combined source insights",
            params={
                "source_urls": [
                    "https://example.com/placeholder",
                    "https://example.org/placeholder-two",
                    "https://mlsysbook.ai/contents/core/introduction.html",
                    "https://www.nature.com/articles/s42256-019-0022-0",
                ]
            },
        ),
    ]

    normalized = normalize_steps(
        request,
        steps,
        intent={"routing_mode": "online_research"},
        web_routing={"routing_mode": "online_research"},
        deep_research_mode=False,
        company_agent_mode=False,
    )

    extract_step = next(step for step in normalized if step.tool_id == "web.extract.structured")
    assert extract_step.params.get("url") == "https://mlsysbook.ai/contents/core/introduction.html"
    assert extract_step.params.get("candidate_urls") == [
        "https://mlsysbook.ai/contents/core/introduction.html",
        "https://www.nature.com/articles/s42256-019-0022-0",
    ]
    assert "source_urls" not in extract_step.params


def test_normalize_steps_keeps_explicit_target_url_extract_step() -> None:
    request = _request("Inspect https://mlsysbook.ai and summarize the findings.")
    steps = [
        PlannedStep(
            tool_id="web.extract.structured",
            title="Extract the visible content",
            params={},
        ),
    ]

    normalized = normalize_steps(
        request,
        steps,
        intent={"routing_mode": "url_scrape", "url": "https://mlsysbook.ai"},
        web_routing={"routing_mode": "url_scrape"},
        deep_research_mode=False,
        company_agent_mode=False,
    )

    assert any(step.tool_id == "browser.playwright.inspect" for step in normalized)
    extract_step = next(step for step in normalized if step.tool_id == "web.extract.structured")
    assert extract_step.params.get("url") == "https://mlsysbook.ai"


def test_enforce_contract_synthesis_step_inserts_report_generate_after_research() -> None:
    request = _request("Research machine learning and email the findings.")
    task_prep = TaskPreparation(
        task_intelligence=SimpleNamespace(target_url=""),
        user_preferences={},
        research_depth_profile={},
        conversation_summary="",
        rewritten_task="Research machine learning and email the findings.",
        planned_deliverables=[],
        planned_constraints=[],
        task_contract={},
        contract_objective="Create a cited machine learning research brief.",
        contract_outputs=[
            "Structured overview report with citations",
            "Source attribution table",
        ],
        contract_facts=[],
        contract_actions=[],
        contract_target="",
        contract_missing_requirements=[],
        contract_success_checks=[],
        memory_context_snippets=[],
        clarification_blocked=False,
        clarification_questions=[],
    )
    steps = [
        PlannedStep(
            tool_id="marketing.web_research",
            title="Search online sources",
            params={"query": "machine learning overview"},
        ),
        PlannedStep(
            tool_id="gmail.draft",
            title="Draft email",
            params={"to": "user@example.com"},
        ),
    ]

    enforced = enforce_contract_synthesis_step(
        request=request,
        task_prep=task_prep,
        steps=steps,
    )

    tool_ids = [step.tool_id for step in enforced]
    assert tool_ids == ["marketing.web_research", "report.generate", "gmail.draft"]


def test_enforce_contract_synthesis_step_uses_request_scope_when_contract_outputs_are_empty() -> None:
    request = _request("Research machine learning, write a summary, and email the findings.")
    task_prep = TaskPreparation(
        task_intelligence=SimpleNamespace(target_url=""),
        user_preferences={},
        research_depth_profile={},
        conversation_summary="",
        rewritten_task="Research machine learning, write a summary, and email the findings.",
        planned_deliverables=[],
        planned_constraints=[],
        task_contract={},
        contract_objective="",
        contract_outputs=[],
        contract_facts=[],
        contract_actions=[],
        contract_target="",
        contract_missing_requirements=[],
        contract_success_checks=[],
        memory_context_snippets=[],
        clarification_blocked=False,
        clarification_questions=[],
    )
    steps = [
        PlannedStep(
            tool_id="marketing.web_research",
            title="Search online sources",
            params={"query": "machine learning overview"},
        ),
    ]

    enforced = enforce_contract_synthesis_step(
        request=request,
        task_prep=task_prep,
        steps=steps,
    )

    assert [step.tool_id for step in enforced] == ["marketing.web_research", "report.generate"]
