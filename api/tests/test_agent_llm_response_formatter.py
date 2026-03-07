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


def test_polish_final_response_includes_language_rule_from_user_message(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_RESPONSE_POLISH_ENABLED", "1")
    observed: dict[str, str] = {}

    def _fake_json_response(**kwargs):
        observed["blueprint_prompt"] = str(kwargs.get("user_prompt") or "")
        observed["blueprint_system"] = str(kwargs.get("system_prompt") or "")
        return {
            "response_style": "adaptive_detailed",
            "detail_level": "high",
            "tone": "professional",
            "sections": [{"title": "Respuesta", "purpose": "Responder", "format": "paragraphs"}],
        }

    def _fake_text_response(**kwargs):
        observed["polish_prompt"] = str(kwargs.get("user_prompt") or "")
        observed["polish_system"] = str(kwargs.get("system_prompt") or "")
        return "Respuesta final."

    monkeypatch.setattr(llm_response_formatter, "call_json_response", _fake_json_response)
    monkeypatch.setattr(llm_response_formatter, "call_text_response", _fake_text_response)

    polish_final_response(
        request_message="Que hace esta empresa y como funciona?",
        answer_text="## Findings\n- Item",
    )

    assert "Language rule: respond in Spanish" in observed["blueprint_prompt"]
    assert "Language rule: respond in Spanish" in observed["blueprint_system"]
    assert "Language rule: respond in Spanish" in observed["polish_prompt"]
    assert "Language rule: respond in Spanish" in observed["polish_system"]


def test_polish_final_response_prefers_explicit_requested_language(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_RESPONSE_POLISH_ENABLED", "1")
    observed: dict[str, str] = {}

    def _fake_json_response(**kwargs):
        observed["blueprint_prompt"] = str(kwargs.get("user_prompt") or "")
        observed["blueprint_system"] = str(kwargs.get("system_prompt") or "")
        return {
            "response_style": "adaptive_detailed",
            "detail_level": "high",
            "tone": "professional",
            "sections": [{"title": "Respuesta", "purpose": "Responder", "format": "paragraphs"}],
        }

    def _fake_text_response(**kwargs):
        observed["polish_prompt"] = str(kwargs.get("user_prompt") or "")
        observed["polish_system"] = str(kwargs.get("system_prompt") or "")
        return "Respuesta final."

    monkeypatch.setattr(llm_response_formatter, "call_json_response", _fake_json_response)
    monkeypatch.setattr(llm_response_formatter, "call_text_response", _fake_text_response)

    polish_final_response(
        request_message='analysis https://axongroup.com/ and send report to "ops@example.com"',
        requested_language="en",
        answer_text="## Findings\n- Item",
    )

    assert "Language rule: respond in English" in observed["blueprint_prompt"]
    assert "Language rule: respond in English" in observed["blueprint_system"]
    assert "Language rule: respond in English" in observed["polish_prompt"]
    assert "Language rule: respond in English" in observed["polish_system"]


def test_polish_final_response_reverts_when_language_drifts(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_RESPONSE_POLISH_ENABLED", "1")
    monkeypatch.setattr(
        llm_response_formatter,
        "call_json_response",
        lambda **kwargs: {
            "response_style": "adaptive_detailed",
            "detail_level": "high",
            "tone": "professional",
            "sections": [{"title": "Answer", "purpose": "Respond", "format": "paragraphs"}],
        },
    )
    monkeypatch.setattr(
        llm_response_formatter,
        "call_text_response",
        lambda **kwargs: (
            "## Analise\n"
            "Nao foi possivel confirmar os servicos ofertados.\n"
            "Tambem nao foi possivel validar os horarios de funcionamento sem evidencias adicionais.\n"
        ),
    )
    original = "## Key Findings\n- Website evidence was captured from the provided URL."
    polished = polish_final_response(
        request_message="Analyze the website and provide findings in English.",
        answer_text=original,
    )
    assert polished == original


def test_polish_final_response_strips_wrapping_fence_and_redacts_request_email(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_RESPONSE_POLISH_ENABLED", "1")
    monkeypatch.setattr(
        llm_response_formatter,
        "call_json_response",
        lambda **kwargs: {
            "response_style": "adaptive_detailed",
            "detail_level": "high",
            "tone": "professional",
            "sections": [{"title": "Answer", "purpose": "Respond", "format": "paragraphs"}],
        },
    )
    monkeypatch.setattr(
        llm_response_formatter,
        "call_text_response",
        lambda **kwargs: (
            "```markdown\n"
            "## Delivery Confirmation\n"
            "Report sent to ssebowadisan1@gmail.com.\n"
            "```"
        ),
    )
    polished = polish_final_response(
        request_message='analysis site and send report to "ssebowadisan1@gmail.com"',
        answer_text="## Delivery Confirmation\nReport sent successfully.",
    )
    assert "```" not in polished
    assert "ssebowadisan1@gmail.com" not in polished
    assert "the recipient" in polished.lower()
