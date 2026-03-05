from __future__ import annotations

import re

from api.services.agent import llm_research_blueprint as blueprint_module
from api.services.agent.llm_research_blueprint import build_research_blueprint


def test_research_blueprint_fallback_produces_minimum_keywords(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_RESEARCH_BLUEPRINT_ENABLED", "0")
    payload = build_research_blueprint(
        message="Analyze https://axongroup.com and map services, competitors, and opportunities.",
        agent_goal="Build outbound strategy",
        min_keywords=10,
    )
    assert isinstance(payload.get("keywords"), list)
    assert len(payload["keywords"]) >= 6
    assert isinstance(payload.get("search_terms"), list)
    assert len(payload["search_terms"]) >= 2
    assert not any(re.search(r"_[0-9]+$", item) for item in payload["keywords"])


def test_research_blueprint_uses_llm_payload_when_valid(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_RESEARCH_BLUEPRINT_ENABLED", "1")
    monkeypatch.setattr(
        blueprint_module,
        "_request_blueprint_with_llm",
        lambda **_: {
            "search_terms": ["axon industrial solutions", "axon competitors europe"],
            "keywords": [
                "axon",
                "industrial",
                "solutions",
                "noise control",
                "powder handling",
                "heat exchange",
                "fluid systems",
                "air systems",
                "companies",
                "market positioning",
            ],
            "rationale": "Prioritize domain-specific terms first.",
        },
    )
    payload = build_research_blueprint(
        message="Analyze axon group website and competitors.",
        agent_goal=None,
        min_keywords=10,
    )
    assert payload["search_terms"][:2] == ["axon industrial solutions", "axon competitors europe"]
    assert len(payload["keywords"]) >= 10
    assert "rationale" in payload


def test_research_blueprint_refills_keywords_when_llm_returns_too_few(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_RESEARCH_BLUEPRINT_ENABLED", "1")
    monkeypatch.setattr(
        blueprint_module,
        "_request_blueprint_with_llm",
        lambda **_: {
            "search_terms": ["short plan"],
            "keywords": ["axon", "solutions"],
            "rationale": "Short list from model",
        },
    )
    payload = build_research_blueprint(
        message="Analyze and prepare market plan",
        agent_goal=None,
        min_keywords=10,
    )
    assert len(payload["keywords"]) >= 4
    assert len(payload["search_terms"]) >= 2
    assert not any(re.search(r"_[0-9]+$", item) for item in payload["keywords"])


def test_research_blueprint_simple_question_has_no_placeholder_keywords(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_RESEARCH_BLUEPRINT_ENABLED", "0")
    payload = build_research_blueprint(
        message="what is machine learning",
        agent_goal="what is machine learning",
        min_keywords=10,
    )
    keywords = payload.get("keywords")
    assert isinstance(keywords, list)
    assert not any(re.search(r"_[0-9]+$", item) for item in keywords)
