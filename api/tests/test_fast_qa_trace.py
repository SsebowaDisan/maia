from __future__ import annotations

from types import SimpleNamespace

from api.services.chat.citation_sections.public_ops import enforce_required_citations
from api.services.chat.fast_qa_turn_sections.answering import build_answer_phase
from api.services.chat.fast_qa_turn_sections.retrieval import run_retrieval_phase
from api.services.observability.citation_trace import begin_trace, end_trace, snapshot_trace


def test_run_retrieval_phase_emits_trace_events() -> None:
    request = SimpleNamespace(
        message="What does the source say about separation units?",
        command="",
        conversation_id="conv-1",
        language=None,
        index_selection={},
        agent_mode="ask",
        setting_overrides={},
        mindmap_focus={},
    )

    handle = begin_trace(kind="chat", user_id="u-1", question=request.message)
    try:
        result = run_retrieval_phase(
            context=object(),
            user_id="u-1",
            request=request,
            logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
            default_setting="",
            get_or_create_conversation_fn=lambda **kwargs: ("conv-1", "Conv", {"messages": [], "state": {}}, ""),
            maybe_autoname_conversation_fn=lambda **kwargs: ("Conv", ""),
            resolve_response_language_fn=lambda language, message: None,
            build_selected_payload_fn=lambda **kwargs: {},
            resolve_contextual_url_targets_fn=lambda **kwargs: [],
            rewrite_followup_question_for_retrieval_fn=lambda **kwargs: (kwargs["question"], False, "literal"),
            load_recent_chunks_for_fast_qa_fn=lambda **kwargs: [
                {
                    "text": "The text discusses optimal design of separation units.",
                    "source_id": "file-1",
                    "source_name": "distillation.pdf",
                    "page_label": "7",
                }
            ],
            finalize_retrieved_snippets_fn=lambda **kwargs: (
                kwargs["retrieved_snippets"],
                "Primary source note",
                "selected",
                {},
            ),
            assess_evidence_sufficiency_with_llm_fn=lambda **kwargs: (True, 0.91, "Sufficient evidence."),
            expand_retrieval_query_for_gap_fn=lambda **kwargs: (kwargs["current_query"], "none"),
            constants={
                "STATE": {},
                "API_FAST_QA_SOURCE_SCAN": 8,
                "API_FAST_QA_MAX_SOURCES": 8,
                "API_FAST_QA_MAX_SNIPPETS": 4,
                "truncate_for_log_fn": lambda value, limit=1600: str(value),
            },
            selected_scope_file_ids_fn=lambda payload: [],
            emit_activity_fn=lambda **kwargs: None,
        )
        trace = snapshot_trace()
    finally:
        end_trace(handle, emit_log=False)

    assert result is not None
    assert result["skip"] is False
    event_types = [event["type"] for event in trace["events"]]
    assert "retrieval.started" in event_types
    assert "retrieval.query_rewritten" in event_types
    assert "retrieval.candidates_loaded" in event_types
    assert "retrieval.selected" in event_types
    assert "retrieval.sufficiency_checked" in event_types
    assert "retrieval.completed" in event_types


def test_build_answer_phase_emits_trace_events() -> None:
    retrieval = {
        "message": "What does the source say about material balances?",
        "snippets": [
            {
                "text": "The source derives steady-state material balances for distillation columns.",
                "page_label": "12",
                "score": 0.8,
                "source_id": "file-1",
                "source_name": "distillation.pdf",
            }
        ],
        "chat_history": [],
        "primary_source_note": "",
        "requested_language": None,
        "is_follow_up": False,
        "mode_variant": "rag",
        "selected_scope_count": 1,
        "covered_scope_count": 1,
        "selected_scope_ids": ["file-1"],
        "all_project_sources": ["distillation.pdf"],
        "focus_meta": {},
        "evidence_confidence": 0.9,
        "evidence_reason": "Sufficient evidence.",
    }

    handle = begin_trace(kind="chat", user_id="u-1", question=retrieval["message"])
    try:
        answering = build_answer_phase(
            request=SimpleNamespace(
                citation="required",
                use_mindmap=False,
                mindmap_settings={},
                mindmap_focus={},
            ),
            logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
            retrieval=retrieval,
            call_openai_fast_qa_fn=lambda **kwargs: "The source derives material balances.",
            normalize_fast_answer_fn=lambda answer, question: answer,
            build_no_relevant_evidence_answer_fn=lambda message, response_language=None: "no evidence",
            resolve_required_citation_mode_fn=lambda value: value,
            render_fast_citation_links_fn=lambda answer, refs, citation_mode: answer,
            build_fast_info_html_fn=lambda snippets_with_refs, max_blocks=12: "<div>info</div>",
            enforce_required_citations_fn=lambda answer, info_html, citation_mode: answer,
            build_source_usage_fn=lambda *args, **kwargs: [],
            build_claim_signal_summary_fn=lambda *args, **kwargs: {},
            build_citation_quality_metrics_fn=lambda *args, **kwargs: {},
            build_info_panel_copy_fn=lambda *args, **kwargs: {},
            build_knowledge_map_fn=lambda *args, **kwargs: {},
            build_verification_evidence_items_fn=lambda *args, **kwargs: [],
            build_web_review_content_fn=lambda *args, **kwargs: {},
            build_sources_used_fn=lambda *args, **kwargs: [],
            chunk_text_for_stream_fn=None,
            emit_activity_fn=lambda **kwargs: None,
            emit_stream_event_fn=lambda payload: None,
            constants={
                "assign_fast_source_refs_fn": lambda snippets: (
                    [{**snippets[0], "ref_id": 1, "ref": "1"}],
                    [{"id": 1, "label": "1"}],
                ),
                "truncate_for_log_fn": lambda value, limit=1600: str(value),
                "MAIA_SOURCE_USAGE_HEATMAP_ENABLED": True,
                "MAIA_CITATION_DOMINANCE_WARNING_THRESHOLD": 0.8,
                "VERIFICATION_CONTRACT_VERSION": "test",
                "MAIA_CITATION_STRENGTH_ORDERING_ENABLED": True,
            },
        )
        trace = snapshot_trace()
    finally:
        end_trace(handle, emit_log=False)

    assert answering is not None
    event_types = [event["type"] for event in trace["events"]]
    assert "answer.started" in event_types
    assert "citation.refs_assigned" in event_types
    assert "citation.enforced" in event_types
    assert "answer.completed" in event_types


def test_enforce_required_citations_emits_trace_events() -> None:
    handle = begin_trace(kind="chat", user_id="u-1", question="Q")
    try:
        result = enforce_required_citations(
            answer="Plain answer without refs.",
            info_html="",
            citation_mode="required",
        )
        trace = snapshot_trace()
    finally:
        end_trace(handle, emit_log=False)

    assert result == "Plain answer without refs."
    event_types = [event["type"] for event in trace["events"]]
    assert "citation.enforce_started" in event_types
    assert "citation.enforce_completed" in event_types
