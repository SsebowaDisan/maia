from api.services.chat.fast_qa_reasoning_helpers import (
    assess_evidence_sufficiency_with_llm,
    select_relevant_snippets_with_llm,
)


class _Logger:
    @staticmethod
    def exception(*args, **kwargs):
        return None


def test_select_relevant_snippets_skips_auxiliary_llm_calls_for_gemini_provider() -> None:
    snippets = [
        {"text": "first", "source_name": "a.pdf", "page_label": "1"},
        {"text": "second", "source_name": "a.pdf", "page_label": "2"},
    ]
    called = {"count": 0}

    def _call_openai_chat_text_fn(**kwargs):
        called["count"] += 1
        return '{"keep_ids":[2]}'

    selected = select_relevant_snippets_with_llm(
        question="Derive the component material balance.",
        chat_history=[],
        snippets=snippets,
        max_keep=1,
        resolve_fast_qa_llm_config_fn=lambda: (
            "key",
            "https://generativelanguage.googleapis.com/v1beta/openai",
            "gemini-2.5-flash",
            "env",
        ),
        is_placeholder_api_key_fn=lambda value: False,
        call_openai_chat_text_fn=_call_openai_chat_text_fn,
        parse_json_object_fn=lambda raw: {"keep_ids": [2]},
        logger=_Logger(),
    )

    assert called["count"] == 0
    assert selected == [snippets[0]]


def test_assess_evidence_sufficiency_skips_auxiliary_llm_calls_for_gemini_provider() -> None:
    called = {"count": 0}

    def _call_openai_chat_text_fn(**kwargs):
        called["count"] += 1
        return '{"sufficient": false, "confidence": 0.1, "reason": "bad"}'

    sufficient, confidence, reason = assess_evidence_sufficiency_with_llm(
        question="Derive the component material balance.",
        chat_history=[],
        snippets=[{"text": "Fx_i = Dx_i + Bx_i"}],
        primary_source_note="",
        require_primary_source=False,
        sufficiency_enabled=True,
        sufficiency_min_confidence=0.5,
        resolve_fast_qa_llm_config_fn=lambda: (
            "key",
            "https://generativelanguage.googleapis.com/v1beta/openai",
            "gemini-2.5-flash",
            "env",
        ),
        is_placeholder_api_key_fn=lambda value: False,
        call_openai_chat_text_fn=_call_openai_chat_text_fn,
        parse_json_object_fn=lambda raw: {"sufficient": False},
        logger=_Logger(),
    )

    assert called["count"] == 0
    assert sufficient is True
    assert confidence == 0.5
    assert "skipped for provider" in reason
