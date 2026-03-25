from __future__ import annotations

from types import SimpleNamespace

from api.services.chat.fast_qa_turn_sections.delivery import finalize_turn
from api.services.observability.citation_trace import begin_trace, end_trace, snapshot_trace
from api.services.upload import pdf_highlight_locator


def test_locate_pdf_highlight_target_emits_trace_events(monkeypatch, tmp_path) -> None:
    sample = tmp_path / "sample.pdf"
    sample.write_bytes(b"%PDF-1.4 fake")

    monkeypatch.setattr(
        pdf_highlight_locator,
        "_extract_page_units",
        lambda file_path, page_number: {
            "page": page_number,
            "units": [
                {
                    "text": "High humidity requires sealed enclosures.",
                    "char_start": 0,
                    "char_end": 40,
                    "highlight_boxes": [{"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.05}],
                }
            ],
        },
    )

    handle = begin_trace(kind="highlight", user_id="u-1")
    try:
        result = pdf_highlight_locator.locate_pdf_highlight_target(
            file_path=sample,
            page=1,
            text="What changes are needed for high humidity?",
            claim_text="High humidity requires sealed enclosures.",
        )
        trace = snapshot_trace()
    finally:
        end_trace(handle, emit_log=False)

    assert result["highlight_boxes"]
    event_types = [event["type"] for event in trace["events"]]
    assert "highlight.locator_started" in event_types
    assert "highlight.page_units_loaded" in event_types
    assert "highlight.candidates_built" in event_types
    assert "highlight.resolved" in event_types


def test_finalize_turn_adds_trace_summary() -> None:
    retrieval = {
        "message": "Question",
        "data_source": {"messages": [], "state": {}, "retrieval_messages": [], "plot_history": [], "message_meta": [], "likes": []},
        "chat_history": [],
        "chat_state": {},
        "mode_variant": "",
        "display_mode": "ask",
        "selected_scope_ids": [],
        "selected_scope_count": 0,
        "covered_scope_count": 0,
        "raw_snippets": [],
        "snippets": [],
        "focus_meta": {},
        "turn_start_ms": 0,
        "retrieval_end_ms": 1,
        "conversation_id": "conv-1",
        "conversation_name": "Conv",
        "activity_run_id": None,
        "selected_payload": {},
    }
    answering = {
        "answer": "Answer",
        "info_text": "Info",
        "info_panel": {},
        "mindmap_payload": {},
        "snippets_with_refs": [],
        "source_usage": [],
        "claim_signal_summary": {},
        "citation_quality_metrics": {},
        "sources_used": [],
        "llm_start_ms": 0,
    }

    handle = begin_trace(kind="chat", user_id="u-1", question="Question")
    try:
        result = finalize_turn(
            user_id="u-1",
            request=SimpleNamespace(),
            retrieval=retrieval,
            answering=answering,
            normalize_request_attachments_fn=lambda request: [],
            persist_conversation_fn=lambda conversation_id, payload: None,
            build_turn_blocks_fn=lambda answer_text, question: ([], []),
            create_document_fn=lambda *args, **kwargs: None,
            document_to_dict_fn=lambda doc: {},
            derive_rag_canvas_title_fn=lambda question, answer: "Title",
            emit_activity_fn=lambda **kwargs: None,
        )
    finally:
        end_trace(handle, emit_log=False)

    trace_summary = result["info_panel"].get("trace_summary")
    assert isinstance(trace_summary, dict)
    assert trace_summary.get("trace_id")
    assert trace_summary.get("last_event_type") == "delivery.completed"


def test_finalize_turn_rag_mirrors_answer_into_top_level_field() -> None:
    retrieval = {
        "message": "Question",
        "data_source": {"messages": [], "state": {}, "retrieval_messages": [], "plot_history": [], "message_meta": [], "likes": []},
        "chat_history": [],
        "chat_state": {},
        "mode_variant": "rag",
        "display_mode": "rag",
        "selected_scope_ids": ["file-1"],
        "selected_scope_count": 1,
        "covered_scope_count": 1,
        "raw_snippets": [],
        "snippets": [],
        "focus_meta": {},
        "turn_start_ms": 0,
        "retrieval_end_ms": 1,
        "conversation_id": "conv-1",
        "conversation_name": "Conv",
        "activity_run_id": None,
        "selected_payload": {},
    }
    answering = {
        "answer": "Grounded answer",
        "info_text": "Info",
        "info_panel": {},
        "mindmap_payload": {},
        "snippets_with_refs": [],
        "source_usage": [],
        "claim_signal_summary": {},
        "citation_quality_metrics": {},
        "sources_used": [],
        "llm_start_ms": 0,
    }

    class _Doc:
        id = "doc-1"

    result = finalize_turn(
        user_id="u-1",
        request=SimpleNamespace(),
        retrieval=retrieval,
        answering=answering,
        normalize_request_attachments_fn=lambda request: [],
        persist_conversation_fn=lambda conversation_id, payload: None,
        build_turn_blocks_fn=lambda answer_text, question: ([], []),
        create_document_fn=lambda *args, **kwargs: _Doc(),
        document_to_dict_fn=lambda doc: {"id": doc.id, "content": "Grounded answer"},
        derive_rag_canvas_title_fn=lambda question, answer: "Title",
        emit_activity_fn=lambda **kwargs: None,
    )

    assert result["answer"] == "Grounded answer"
    assert result["documents"][0]["content"] == "Grounded answer"
    assert result["info_panel"]["rag_answer_mirrored"] is True
