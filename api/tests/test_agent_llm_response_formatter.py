from api.services.agent import llm_response_formatter
from api.services.agent.llm_response_formatter import polish_final_response


def test_polish_final_response_disabled(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_RESPONSE_POLISH_ENABLED", "0")
    text = "## Execution\n- Done"
    assert polish_final_response(request_message="x", answer_text=text) == text


def test_polish_final_response_uses_fallback(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_RESPONSE_POLISH_ENABLED", "1")
    monkeypatch.setattr(llm_response_formatter, "call_text_response", lambda **kwargs: "")
    text = "## Execution\n- Done"
    assert polish_final_response(request_message="x", answer_text=text) == text
