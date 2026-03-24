from __future__ import annotations

import logging

from api.schemas import ChatRequest
from api.services.chat import app_stream_helpers
from api.services.chat import fast_qa_turn_helpers
from api.services.chat.fast_qa_turn_helpers import run_fast_chat_turn_impl


def test_run_fast_chat_turn_impl_rag_emits_document_activity_and_selected_scope(monkeypatch) -> None:
    emitted: list[dict] = []
    persisted: dict[str, object] = {}
    created_docs: list[dict] = []

    monkeypatch.setattr(
        fast_qa_turn_helpers,
        "create_document",
        lambda *_args, **kwargs: type(
            "CanvasDoc",
            (),
            {
                "id": "canvas-1",
                "title": kwargs.get("title", "Canvas"),
                "content": kwargs.get("content", ""),
                "info_html": kwargs.get("info_html", ""),
                "info_panel_json": "{}",
                "info_panel": kwargs.get("info_panel", {}),
                "user_prompt": kwargs.get("user_prompt", ""),
                "mode_variant": kwargs.get("mode_variant", ""),
                "source_agent_id": kwargs.get("source_agent_id", ""),
                "created_at": 0.0,
                "updated_at": 0.0,
            },
        )(),
    )
    monkeypatch.setattr(
        fast_qa_turn_helpers,
        "document_to_dict",
        lambda doc: created_docs.append(
            {
                "id": doc.id,
                "title": doc.title,
                "content": doc.content,
                "info_html": doc.info_html,
                "info_panel": doc.info_panel,
                "user_prompt": doc.user_prompt,
                "mode_variant": doc.mode_variant,
            }
        )
        or created_docs[-1],
    )

    def _assign_fast_source_refs(snippets):
        snippets_with_refs = []
        refs = []
        for idx, row in enumerate(snippets, start=1):
            enriched = dict(row)
            enriched["ref"] = idx
            snippets_with_refs.append(enriched)
            refs.append(
                {
                    "ref": idx,
                    "source_id": row.get("source_id"),
                    "source_name": row.get("source_name"),
                    "source_url": row.get("source_url"),
                    "page_label": row.get("page_label"),
                    "unit_id": row.get("unit_id"),
                }
            )
        return snippets_with_refs, refs

    request = ChatRequest(
        message="Answer only from the selected PDFs.",
        setting_overrides={
            "__rag_mode_enabled": True,
            "__disable_auto_web_fallback": True,
        },
        citation="inline",
    )

    result = run_fast_chat_turn_impl(
        context=None,
        user_id="user-1",
        request=request,
        logger=logging.getLogger("test_fast_qa_rag_stream"),
        default_setting="default",
        get_or_create_conversation_fn=lambda **_: ("conv-1", "Chat", {}, "spark"),
        maybe_autoname_conversation_fn=lambda **_: ("Chat", "spark"),
        resolve_response_language_fn=lambda _language, _message: "en",
        build_selected_payload_fn=lambda **_: {"7": ["select", ["file-1", "file-2"]]},
        resolve_contextual_url_targets_fn=lambda **_: [],
        rewrite_followup_question_for_retrieval_fn=lambda **kwargs: (
            str(kwargs.get("question") or ""),
            False,
            "direct",
        ),
        load_recent_chunks_for_fast_qa_fn=lambda **_: [
            {
                "source_id": "file-1",
                "source_name": "Paper A",
                "source_url": "",
                "text": "Formula one",
                "page_label": "2",
                "unit_id": "u1",
                "score": 0.91,
            },
            {
                "source_id": "file-2",
                "source_name": "Paper B",
                "source_url": "",
                "text": "Formula two",
                "page_label": "5",
                "unit_id": "u2",
                "score": 0.88,
            },
        ],
        finalize_retrieved_snippets_fn=lambda **kwargs: (
            list(kwargs.get("retrieved_snippets") or []),
            "Use both selected papers.",
            "ok",
            {},
        ),
        assess_evidence_sufficiency_with_llm_fn=lambda **_: (True, 0.92, "sufficient"),
        expand_retrieval_query_for_gap_fn=lambda **kwargs: (
            str(kwargs.get("current_query") or ""),
            "unchanged",
        ),
        call_openai_fast_qa_fn=lambda **_: "Answer with evidence [1][2].",
        normalize_fast_answer_fn=lambda answer, **_: answer,
        build_no_relevant_evidence_answer_fn=lambda *_args, **_kwargs: "No evidence.",
        resolve_required_citation_mode_fn=lambda *_args, **_kwargs: "inline",
        render_fast_citation_links_fn=lambda **kwargs: kwargs["answer"],
        build_fast_info_html_fn=lambda snippets, max_blocks=6: "<div>evidence</div>",
        enforce_required_citations_fn=lambda **kwargs: kwargs["answer"],
        build_source_usage_fn=lambda **_: [],
        build_claim_signal_summary_fn=lambda **_: {},
        build_citation_quality_metrics_fn=lambda **_: {},
        build_info_panel_copy_fn=lambda **_: {},
        build_knowledge_map_fn=lambda **_: {},
        build_verification_evidence_items_fn=lambda **_: [
            {"file_id": "file-1", "page": 2},
            {"file_id": "file-2", "page": 5},
        ],
        build_web_review_content_fn=lambda *_args, **_kwargs: {},
        persist_conversation_fn=lambda conversation_id, payload: persisted.update(
            {"conversation_id": conversation_id, "payload": payload}
        ),
        normalize_request_attachments_fn=lambda _request: [],
        constants={
            "STATE": {},
            "truncate_for_log_fn": lambda value, limit=1600: str(value)[:limit],
            "API_FAST_QA_SOURCE_SCAN": 12,
            "API_FAST_QA_MAX_SOURCES": 8,
            "API_FAST_QA_MAX_SNIPPETS": 6,
            "assign_fast_source_refs_fn": _assign_fast_source_refs,
            "MAIA_SOURCE_USAGE_HEATMAP_ENABLED": False,
            "MAIA_CITATION_DOMINANCE_WARNING_THRESHOLD": 0.8,
            "VERIFICATION_CONTRACT_VERSION": "test-v1",
            "MAIA_CITATION_STRENGTH_ORDERING_ENABLED": True,
        },
        emit_stream_event_fn=emitted.append,
        make_activity_event_fn=lambda **kwargs: kwargs,
        chunk_text_for_stream_fn=lambda text, _size: [text[:12], text[12:]],
    )

    assert result is not None
    assert str(result.get("mode_actually_used")) == "rag"
    assert str(result.get("activity_run_id", "")).startswith("rag_")
    assert result.get("answer", "") == ""
    info_panel = result.get("info_panel", {})
    assert isinstance(info_panel, dict)
    selected_scope = info_panel.get("selected_scope", {})
    assert isinstance(selected_scope, dict)
    assert selected_scope.get("file_count") == 2
    assert selected_scope.get("covered_file_count") == 2
    sources_used = result.get("sources_used", [])
    assert isinstance(sources_used, list) and len(sources_used) == 2
    assert result.get("documents") == created_docs
    assert result["documents"][0]["info_html"] == "<div>evidence</div>"
    assert result["documents"][0]["info_panel"]["selected_scope"]["file_count"] == 2
    assert result["documents"][0]["user_prompt"] == "Answer only from the selected PDFs."
    assert result["documents"][0]["mode_variant"] == "rag"
    block_types = [block.get("type") for block in result.get("blocks", [])]
    assert block_types == ["document_action"]

    activity_rows = [row["event"] for row in emitted if row.get("type") == "activity"]
    activity_types = [row.get("event_type") for row in activity_rows]
    assert "document_review_started" in activity_types
    assert "document_synthesis_started" in activity_types
    assert "doc_writing_started" in activity_types
    assert "doc_type_text" in activity_types
    assert "document_review_completed" in activity_types
    assert all(row.get("run_id") == result.get("activity_run_id") for row in activity_rows)

    chat_deltas = [row for row in emitted if row.get("type") == "chat_delta"]
    assert chat_deltas
    assert persisted.get("conversation_id") == "conv-1"


def test_stream_chat_turn_routes_rag_to_fast_stream(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(app_stream_helpers, "load_user_settings", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        app_stream_helpers,
        "get_or_create_conversation",
        lambda **_: ("conv-1", "Chat", {}, "spark"),
    )
    monkeypatch.setattr(
        app_stream_helpers,
        "maybe_autoname_conversation",
        lambda **_: ("Chat", "spark"),
    )
    monkeypatch.setattr(
        app_stream_helpers,
        "build_selected_payload",
        lambda **_: {"7": ["select", ["file-1"]]},
    )

    def _fake_stream_fast_chat_turn(*, context, user_id, request):
        del context
        captured["user_id"] = user_id
        captured["message"] = request.message
        yield {"type": "activity", "event": {"event_type": "document_review_started"}}
        return {"answer": "done", "activity_run_id": "rag_test"}

    monkeypatch.setattr(app_stream_helpers, "stream_fast_chat_turn", _fake_stream_fast_chat_turn)

    iterator = app_stream_helpers.stream_chat_turn(
        context=None,
        user_id="user-1",
        request=ChatRequest(
            message="Use my selected documents only.",
            setting_overrides={
                "__rag_mode_enabled": True,
                "__disable_auto_web_fallback": True,
            },
        ),
        auto_index_urls_for_request_fn=lambda **kwargs: kwargs["request"],
        apply_deep_search_defaults_fn=lambda **kwargs: kwargs["request"],
        normalize_request_attachments_fn=lambda _request: [],
        mode_variant_from_request_fn=lambda **_: "rag",
        is_orchestrator_mode_fn=lambda _mode: False,
    )

    events: list[dict] = []
    while True:
        try:
            events.append(next(iterator))
        except StopIteration as stop:
            result = stop.value
            break

    assert captured["user_id"] == "user-1"
    assert captured["message"] == "Use my selected documents only."
    assert events[0]["type"] == "mode_committed"
    assert events[0]["mode"] == "rag"
    assert events[1]["type"] == "activity"
    assert result["activity_run_id"] == "rag_test"
