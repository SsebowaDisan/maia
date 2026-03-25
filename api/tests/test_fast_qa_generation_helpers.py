from api.services.chat import fast_qa_generation_helpers as helpers


def test_call_openai_fast_qa_impl_caches_identical_requests(monkeypatch) -> None:
    helpers._FAST_QA_RESPONSE_CACHE.clear()
    monkeypatch.setenv("MAIA_FAST_QA_RESPONSE_CACHE_SIZE", "16")

    calls = {"count": 0}

    def _call_openai_chat_text_fn(**kwargs):
        calls["count"] += 1
        return "cached answer"

    kwargs = dict(
        question="Derive the full component material balance.",
        snippets=[
            {
                "ref_id": 1,
                "source_id": "file-1",
                "source_name": "distillation.pdf",
                "page_label": "21",
                "text": "Fx_{iF}=Dx_{iD}+Bx_{iB}",
            }
        ],
        chat_history=[],
        refs=[{"id": 1, "label": "1"}],
        citation_mode="required",
        primary_source_note="Primary source target from user-selected file(s): file-1",
        requested_language=None,
        allow_general_knowledge=False,
        is_follow_up=False,
        all_project_sources=["distillation.pdf"],
        logger=type("L", (), {"warning": staticmethod(lambda *args, **kwargs: None), "exception": staticmethod(lambda *args, **kwargs: None)})(),
        resolve_fast_qa_llm_config_fn=lambda: (
            "key",
            "https://generativelanguage.googleapis.com/v1beta/openai",
            "gemini-2.5-flash-lite",
            "env",
        ),
        truncate_for_log_fn=lambda value, limit=1600: str(value),
        is_placeholder_api_key_fn=lambda value: False,
        resolve_required_citation_mode_fn=lambda value: value or "required",
        build_response_language_rule_fn=lambda requested_language, latest_message: "Respond in English.",
        plan_adaptive_outline_fn=lambda **kwargs: {
            "style": "adaptive-detailed",
            "detail_level": "high",
            "sections": [{"title": "Answer", "goal": "Respond directly", "format": "mixed"}],
            "tone": "professional",
        },
        call_openai_chat_text_fn=_call_openai_chat_text_fn,
        API_FAST_QA_MAX_SNIPPETS=12,
        API_FAST_QA_MAX_IMAGES=0,
        API_FAST_QA_TEMPERATURE=0.0,
        infer_provider_label_fn=lambda base_url, model: "generativelanguage.googleapis.com",
    )

    first = helpers.call_openai_fast_qa_impl(**kwargs)
    second = helpers.call_openai_fast_qa_impl(**kwargs)

    assert first == "cached answer"
    assert second == "cached answer"
    assert calls["count"] == 1
