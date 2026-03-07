from __future__ import annotations

from typing import Any

from api.schemas import ChatRequest
from api.services.chat.fast_qa import call_openai_fast_qa, run_fast_chat_turn


def test_call_openai_fast_qa_general_fallback_prompt(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        "api.services.chat.fast_qa._resolve_fast_qa_llm_config",
        lambda: ("test-key", "https://api.openai.com/v1", "gpt-4o-mini", "env"),
    )
    monkeypatch.setattr(
        "api.services.chat.fast_qa._plan_adaptive_outline",
        lambda **_: {
            "style": "direct",
            "detail_level": "medium",
            "sections": [{"title": "Answer", "goal": "Respond directly", "format": "paragraphs"}],
            "tone": "professional",
        },
    )

    def _fake_openai_call(*, api_key: str, base_url: str, request_payload: dict[str, Any], timeout_seconds: int) -> str:
        captured["payload"] = request_payload
        return "Machine learning is a method where models learn patterns from data."

    monkeypatch.setattr("api.services.chat.fast_qa._call_openai_chat_text", _fake_openai_call)

    answer = call_openai_fast_qa(
        question="what is machine learning",
        snippets=[],
        chat_history=[],
        refs=[],
        citation_mode="inline",
        allow_general_knowledge=True,
    )

    assert answer and "Machine learning" in answer
    payload = captured.get("payload")
    assert isinstance(payload, dict)
    messages = payload.get("messages", [])
    assert isinstance(messages, list) and len(messages) >= 2
    user_content = messages[1].get("content", [])
    assert isinstance(user_content, list) and user_content
    prompt = str(user_content[0].get("text", ""))
    assert "No indexed evidence matched this request." in prompt
    assert "Not visible in indexed content" not in prompt


def test_run_fast_chat_turn_falls_back_to_llm_without_indexed_snippets(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        "api.services.chat.fast_qa.get_or_create_conversation",
        lambda user_id, conversation_id: ("conv-1", "Chat", {}, "spark"),
    )
    monkeypatch.setattr(
        "api.services.chat.fast_qa.maybe_autoname_conversation",
        lambda **kwargs: ("Chat", "spark"),
    )
    monkeypatch.setattr("api.services.chat.fast_qa.build_selected_payload", lambda **kwargs: {})
    monkeypatch.setattr("api.services.chat.fast_qa._resolve_contextual_url_targets", lambda **kwargs: [])
    monkeypatch.setattr(
        "api.services.chat.fast_qa._rewrite_followup_question_for_retrieval",
        lambda **kwargs: (str(kwargs.get("question", "") or ""), False, "direct"),
    )
    monkeypatch.setattr("api.services.chat.fast_qa.load_recent_chunks_for_fast_qa", lambda **kwargs: [])
    monkeypatch.setattr(
        "api.services.chat.fast_qa._finalize_retrieved_snippets",
        lambda **kwargs: ([], "", "no_relevant_snippets"),
    )
    monkeypatch.setattr(
        "api.services.chat.fast_qa._assess_evidence_sufficiency_with_llm",
        lambda **kwargs: (True, 1.0, "sufficient"),
    )
    monkeypatch.setattr("api.services.chat.fast_qa.resolve_response_language", lambda language, message: "en")
    monkeypatch.setattr("api.services.chat.fast_qa.persist_conversation", lambda *args, **kwargs: None)

    def _fake_call_openai_fast_qa(**kwargs):
        captured["allow_general_knowledge"] = kwargs.get("allow_general_knowledge")
        return "Machine learning is a branch of AI where systems learn from data."

    monkeypatch.setattr("api.services.chat.fast_qa.call_openai_fast_qa", _fake_call_openai_fast_qa)

    result = run_fast_chat_turn(
        context=None,
        user_id="user-1",
        request=ChatRequest(message="what is machine learning", agent_mode="ask"),
    )

    assert result is not None
    assert captured.get("allow_general_knowledge") is True
    assert "Machine learning is a branch of AI" in str(result.get("answer", ""))
    assert "Not visible in indexed content" not in str(result.get("answer", ""))
    assert "internal execution trace" not in str(result.get("answer", ""))
    info_panel = result.get("info_panel", {})
    assert isinstance(info_panel, dict)
    assert info_panel.get("answer_origin") == "llm_general_knowledge"
