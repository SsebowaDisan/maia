from api.services.agent import llm_response_formatter
from api.services.agent.llm_response_formatter import polish_final_response


def test_polish_final_response_disabled(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_RESPONSE_POLISH_ENABLED", "0")
    text = "## Execution\n- Done"
    assert polish_final_response(request_message="x", answer_text=text) == text


def test_polish_final_response_uses_fallback(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_RESPONSE_POLISH_ENABLED", "1")
    monkeypatch.setattr(llm_response_formatter, "call_json_response", lambda **kwargs: None)
    monkeypatch.setattr(llm_response_formatter, "call_text_response", lambda **kwargs: "")
    text = "## Execution\n- Done"
    assert polish_final_response(request_message="x", answer_text=text) == text


def test_polish_final_response_adaptive_blueprint_and_citation_preserve(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_RESPONSE_POLISH_ENABLED", "1")
    monkeypatch.setattr(
        llm_response_formatter,
        "call_json_response",
        lambda **kwargs: {
            "response_style": "adaptive_detailed",
            "detail_level": "high",
            "tone": "professional",
            "sections": [
                {"title": "Industrial airflow system", "purpose": "Explain scope", "format": "paragraphs"}
            ],
        },
    )
    monkeypatch.setattr(
        llm_response_formatter,
        "call_text_response",
        lambda **kwargs: "The document describes industrial airflow treatment components in detail.",
    )
    text = "## Findings\n- Item\n\n## Evidence Citations\n- [1] Example | https://example.com"
    polished = polish_final_response(request_message="what is this pdf about", answer_text=text)
    assert "industrial airflow treatment" in polished.lower()
    assert "## Evidence Citations" in polished
    assert "[1]" in polished
