from api.services.agent import llm_intent
from api.services.agent.llm_intent import (
    classify_intent_tags,
    detect_web_routing_mode,
    enrich_task_intelligence,
)


def test_enrich_task_intelligence_disabled(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_INTENT_ENABLED", "0")
    result = enrich_task_intelligence(
        message="Analyze website and send report",
        agent_goal=None,
        heuristic={"requires_delivery": True},
    )
    assert result == {}


def test_enrich_task_intelligence_sanitizes(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_INTENT_ENABLED", "1")
    monkeypatch.setattr(
        llm_intent,
        "call_json_response",
        lambda **kwargs: {
            "objective": "Do analysis",
            "requires_delivery": "true",
            "requires_web_inspection": "false",
            "requested_report": "1",
            "preferred_tone": "executive",
        },
    )
    result = enrich_task_intelligence(
        message="Analyze",
        agent_goal=None,
        heuristic={},
    )
    assert result["objective"] == "Do analysis"
    assert result["requires_delivery"] is True
    assert result["requires_web_inspection"] is False
    assert result["requested_report"] is True


def test_classify_intent_tags_uses_structured_heuristic_when_llm_disabled(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_INTENT_TAGS_ENABLED", "0")
    tags = classify_intent_tags(
        message="Analyze https://example.com, write docs, update sheet tracker, and send email.",
        agent_goal=None,
        heuristic={
            "requires_web_inspection": True,
            "requested_report": True,
            "requires_delivery": True,
            "wants_docs_output": True,
            "wants_sheets_output": True,
        },
    )
    assert "web_research" in tags
    assert "docs_write" in tags
    assert "sheets_update" in tags
    assert "email_delivery" in tags


def test_classify_intent_tags_merges_and_sanitizes_llm_tags(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_INTENT_TAGS_ENABLED", "1")
    monkeypatch.setattr(
        llm_intent,
        "call_json_response",
        lambda **kwargs: {
            "intent_tags": [
                "docs_write",
                "sheets_update",
                "not_allowed",
                "docs_write",
            ]
        },
    )
    tags = classify_intent_tags(
        message="Write this to docs and keep a tracker",
        agent_goal=None,
        heuristic={},
    )
    assert "docs_write" in tags
    assert "sheets_update" in tags
    assert "not_allowed" not in tags


def test_detect_web_routing_mode_falls_back_to_online_research_when_web_discovery_signal(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_WEB_ROUTING_ENABLED", "0")
    routing = detect_web_routing_mode(
        message="Research online competitors",
        agent_goal=None,
        heuristic={"explicit_web_discovery": True},
    )
    assert routing["routing_mode"] == "online_research"
    assert routing["llm_used"] is False
