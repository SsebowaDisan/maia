from __future__ import annotations

import uuid
from typing import Any, Callable

from fastapi import HTTPException

from api.services.canvas.document_store import create_document, document_to_dict
from api.services.chat.block_builder import build_turn_blocks
from api.services.chat.fast_qa_turn_sections.answering import build_answer_phase
from api.services.chat.fast_qa_turn_sections.common import (
    build_sources_used as _build_sources_used,
)
from api.services.chat.fast_qa_turn_sections.common import (
    derive_rag_canvas_title as _derive_rag_canvas_title,
)
from api.services.chat.fast_qa_turn_sections.common import (
    selected_scope_file_ids as _selected_scope_file_ids,
)
from api.services.chat.fast_qa_turn_sections.delivery import finalize_turn
from api.services.chat.fast_qa_turn_sections.retrieval import run_retrieval_phase


def run_fast_chat_turn_impl(
    *,
    context,
    user_id: str,
    request,
    logger,
    default_setting: str,
    get_or_create_conversation_fn,
    maybe_autoname_conversation_fn,
    resolve_response_language_fn,
    build_selected_payload_fn,
    resolve_contextual_url_targets_fn,
    rewrite_followup_question_for_retrieval_fn,
    load_recent_chunks_for_fast_qa_fn,
    finalize_retrieved_snippets_fn,
    assess_evidence_sufficiency_with_llm_fn,
    expand_retrieval_query_for_gap_fn,
    call_openai_fast_qa_fn,
    normalize_fast_answer_fn,
    build_no_relevant_evidence_answer_fn,
    resolve_required_citation_mode_fn,
    render_fast_citation_links_fn,
    build_fast_info_html_fn,
    enforce_required_citations_fn,
    build_source_usage_fn,
    build_claim_signal_summary_fn,
    build_citation_quality_metrics_fn,
    build_info_panel_copy_fn,
    build_knowledge_map_fn,
    build_verification_evidence_items_fn,
    build_web_review_content_fn,
    persist_conversation_fn,
    normalize_request_attachments_fn,
    constants: dict[str, Any],
    emit_stream_event_fn: Callable[[dict[str, Any]], None] | None = None,
    make_activity_event_fn: Callable[..., dict[str, Any]] | None = None,
    chunk_text_for_stream_fn: Callable[[str, int], list[str]] | None = None,
) -> dict[str, Any] | None:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is empty.")

    activity_run_id = f"rag_{uuid.uuid4().hex}"
    event_seq = 0

    def emit_stream_event(payload: dict[str, Any]) -> None:
        if emit_stream_event_fn is None:
            return
        emit_stream_event_fn(payload)

    def emit_activity(
        *,
        event_type: str,
        title: str,
        detail: str = "",
        data: dict[str, Any] | None = None,
        stage: str | None = None,
        status: str | None = None,
    ) -> None:
        nonlocal event_seq
        if emit_stream_event_fn is None or make_activity_event_fn is None:
            return
        event_seq += 1
        emit_stream_event(
            {
                "type": "activity",
                "event": make_activity_event_fn(
                    run_id=activity_run_id,
                    event_type=event_type,
                    title=title,
                    detail=detail,
                    data=data or {},
                    seq=event_seq,
                    stage=stage,
                    status=status,
                ),
            }
        )

    retrieval = run_retrieval_phase(
        context=context,
        user_id=user_id,
        request=request,
        logger=logger,
        default_setting=default_setting,
        get_or_create_conversation_fn=get_or_create_conversation_fn,
        maybe_autoname_conversation_fn=maybe_autoname_conversation_fn,
        resolve_response_language_fn=resolve_response_language_fn,
        build_selected_payload_fn=build_selected_payload_fn,
        resolve_contextual_url_targets_fn=resolve_contextual_url_targets_fn,
        rewrite_followup_question_for_retrieval_fn=rewrite_followup_question_for_retrieval_fn,
        load_recent_chunks_for_fast_qa_fn=load_recent_chunks_for_fast_qa_fn,
        finalize_retrieved_snippets_fn=finalize_retrieved_snippets_fn,
        assess_evidence_sufficiency_with_llm_fn=assess_evidence_sufficiency_with_llm_fn,
        expand_retrieval_query_for_gap_fn=expand_retrieval_query_for_gap_fn,
        constants=constants,
        selected_scope_file_ids_fn=_selected_scope_file_ids,
        emit_activity_fn=emit_activity,
    )
    if retrieval is None or retrieval.get("skip"):
        return None
    retrieval["activity_run_id"] = activity_run_id

    answering = build_answer_phase(
        request=request,
        logger=logger,
        retrieval=retrieval,
        call_openai_fast_qa_fn=call_openai_fast_qa_fn,
        normalize_fast_answer_fn=normalize_fast_answer_fn,
        build_no_relevant_evidence_answer_fn=build_no_relevant_evidence_answer_fn,
        resolve_required_citation_mode_fn=resolve_required_citation_mode_fn,
        render_fast_citation_links_fn=render_fast_citation_links_fn,
        build_fast_info_html_fn=build_fast_info_html_fn,
        enforce_required_citations_fn=enforce_required_citations_fn,
        build_source_usage_fn=build_source_usage_fn,
        build_claim_signal_summary_fn=build_claim_signal_summary_fn,
        build_citation_quality_metrics_fn=build_citation_quality_metrics_fn,
        build_info_panel_copy_fn=build_info_panel_copy_fn,
        build_knowledge_map_fn=build_knowledge_map_fn,
        build_verification_evidence_items_fn=build_verification_evidence_items_fn,
        build_web_review_content_fn=build_web_review_content_fn,
        build_sources_used_fn=_build_sources_used,
        chunk_text_for_stream_fn=chunk_text_for_stream_fn,
        emit_activity_fn=emit_activity,
        emit_stream_event_fn=emit_stream_event,
        constants=constants,
    )
    if answering is None:
        return None

    return finalize_turn(
        user_id=user_id,
        request=request,
        retrieval=retrieval,
        answering=answering,
        normalize_request_attachments_fn=normalize_request_attachments_fn,
        persist_conversation_fn=persist_conversation_fn,
        build_turn_blocks_fn=build_turn_blocks,
        create_document_fn=create_document,
        document_to_dict_fn=document_to_dict,
        derive_rag_canvas_title_fn=_derive_rag_canvas_title,
        emit_activity_fn=emit_activity,
    )
