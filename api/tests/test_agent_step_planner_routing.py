from types import SimpleNamespace

from api.schemas import ChatRequest
from api.services.agent.orchestration.models import TaskPreparation
from api.services.agent.orchestration.step_planner_sections.app import (
    _apply_stage_scoped_web_routing_override,
)


def _task_prep(*, target_url: str = "") -> TaskPreparation:
    intelligence = SimpleNamespace(
        is_analytics_request=False,
        requires_web_inspection=False,
        requires_delivery=False,
        target_url=target_url,
    )
    return TaskPreparation(
        task_intelligence=intelligence,
        user_preferences={},
        research_depth_profile={},
        conversation_summary="",
        rewritten_task="",
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


def test_stage_scoped_web_tools_force_online_research_when_router_returns_none() -> None:
    request = ChatRequest(
        message="Make research online about machine learning",
        conversation_id="conv_1",
        agent_mode="company_agent",
    )
    routing = _apply_stage_scoped_web_routing_override(
        request=request,
        task_prep=_task_prep(),
        available_tool_ids={"marketing.web_research", "web.extract.structured"},
        allowlist_provided=True,
        web_routing={"routing_mode": "none", "reasoning": "llm_unavailable", "llm_used": False},
    )
    assert routing["routing_mode"] == "online_research"
    assert routing["reasoning"] == "workflow_stage_tool_scope"
    assert routing["target_url"] == ""


def test_stage_scoped_browser_tools_force_url_scrape_when_target_url_exists() -> None:
    request = ChatRequest(
        message="Review this page and extract the key points",
        conversation_id="conv_1",
        agent_mode="company_agent",
    )
    routing = _apply_stage_scoped_web_routing_override(
        request=request,
        task_prep=_task_prep(target_url="https://mlsysbook.ai"),
        available_tool_ids={"browser.playwright.inspect", "web.extract.structured"},
        allowlist_provided=True,
        web_routing={"routing_mode": "none", "reasoning": "llm_unavailable", "llm_used": False},
    )
    assert routing["routing_mode"] == "url_scrape"
    assert routing["target_url"] == "https://mlsysbook.ai"


def test_stage_scope_does_not_override_existing_non_none_route() -> None:
    request = ChatRequest(
        message="Research machine learning",
        conversation_id="conv_1",
        agent_mode="company_agent",
    )
    routing = _apply_stage_scoped_web_routing_override(
        request=request,
        task_prep=_task_prep(),
        available_tool_ids={"marketing.web_research", "web.extract.structured"},
        allowlist_provided=True,
        web_routing={"routing_mode": "online_research", "reasoning": "llm_router", "llm_used": True},
    )
    assert routing["routing_mode"] == "online_research"
    assert routing["reasoning"] == "llm_router"
