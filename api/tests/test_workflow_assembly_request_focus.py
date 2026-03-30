from api.services.agent.brain.workflow_assembly_sections import request_shape as module


def test_derive_request_focus_uses_llm_for_operational_wrapper(monkeypatch) -> None:
    monkeypatch.setattr(module, "call_json_response", lambda **_: {"focus": "machine learning"})
    module._derive_request_focus_with_llm.cache_clear()

    assert module._derive_request_focus("Make research online about machine learning?") == "machine learning"


def test_derive_request_focus_fallback_handles_online_research_wrapper(monkeypatch) -> None:
    monkeypatch.setattr(module, "call_json_response", lambda **_: None)
    module._derive_request_focus_with_llm.cache_clear()

    assert module._derive_request_focus("Make research online about machine learning?") == "machine learning"
