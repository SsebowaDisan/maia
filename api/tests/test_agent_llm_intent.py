from api.services.agent import llm_intent
from api.services.agent.llm_intent import enrich_task_intelligence


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
