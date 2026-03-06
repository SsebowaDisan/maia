from __future__ import annotations

from api.services.agent import research_depth_profile as depth_module
from api.services.agent.research_depth_profile import derive_research_depth_profile


def test_depth_profile_uses_llm_budget_for_deep_research(monkeypatch) -> None:
    monkeypatch.setattr(
        depth_module,
        "call_json_response",
        lambda **kwargs: {
            "tier": "deep_research",
            "rationale": "Need broad multi-source coverage.",
            "source_budget_min": 50,
            "source_budget_max": 100,
            "max_query_variants": 9,
            "results_per_query": 12,
            "fused_top_k": 120,
            "max_live_inspections": 24,
            "min_unique_sources": 55,
            "min_keywords": 18,
            "simple_explanation_required": False,
            "include_execution_why": False,
        },
    )
    profile = derive_research_depth_profile(
        message="Research energy market trends in depth.",
        agent_goal="Create a comprehensive report.",
        user_preferences={},
        agent_mode="company_agent",
    )
    assert profile.tier == "deep_research"
    assert profile.source_budget_min >= 50
    assert profile.source_budget_max >= 100
    assert profile.min_unique_sources >= 50
    assert profile.file_source_budget_min >= 100
    assert profile.file_source_budget_max >= 200
    assert profile.max_file_sources >= 100


def test_depth_profile_accepts_quick_tier_from_llm(monkeypatch) -> None:
    monkeypatch.setattr(
        depth_module,
        "call_json_response",
        lambda **kwargs: {
            "tier": "quick",
            "rationale": "Simple direct question.",
            "max_query_variants": 2,
            "results_per_query": 4,
        },
    )
    profile = derive_research_depth_profile(
        message="What is machine learning?",
        agent_goal="",
        user_preferences={},
        agent_mode="ask",
    )
    assert profile.tier == "quick"
    assert profile.max_query_variants == 2


def test_depth_profile_enables_simple_explanation_from_llm(monkeypatch) -> None:
    monkeypatch.setattr(
        depth_module,
        "call_json_response",
        lambda **kwargs: {
            "tier": "standard",
            "rationale": "Audience requires simplification.",
            "simple_explanation_required": True,
        },
    )
    profile = derive_research_depth_profile(
        message="Explain machine learning for children.",
        agent_goal="",
        user_preferences={},
        agent_mode="company_agent",
    )
    assert profile.simple_explanation_required is True


def test_depth_profile_forces_deep_research_for_deep_search_mode(monkeypatch) -> None:
    monkeypatch.setattr(
        depth_module,
        "call_json_response",
        lambda **kwargs: {
            "tier": "quick",
            "rationale": "Short question.",
            "max_query_variants": 2,
            "results_per_query": 4,
        },
    )
    profile = derive_research_depth_profile(
        message="Find latest renewable energy breakthroughs.",
        agent_goal="",
        user_preferences={},
        agent_mode="deep_search",
    )
    assert profile.tier == "deep_research"
