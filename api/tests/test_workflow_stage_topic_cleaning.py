from api.services.agents.workflow_executor_sections import common as module


def test_clean_stage_topic_uses_llm_extraction_for_operational_wrapper(monkeypatch) -> None:
    monkeypatch.setattr(module, "call_json_response", lambda **_: {"topic": "machine learning"})
    module._extract_stage_topic.cache_clear()

    assert module._clean_stage_topic("Make research online about machine learning?") == "machine learning"


def test_clean_stage_topic_falls_back_when_llm_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(module, "call_json_response", lambda **_: None)
    module._extract_stage_topic.cache_clear()

    assert module._clean_stage_topic("Make research online about machine learning?") == "machine learning"
