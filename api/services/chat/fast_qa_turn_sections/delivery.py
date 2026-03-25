from __future__ import annotations

import time
from copy import deepcopy
from typing import Any, Callable

from api.services.observability.citation_trace import record_trace_event, summarize_trace


def finalize_turn(
    *,
    user_id: str,
    request,
    retrieval: dict[str, Any],
    answering: dict[str, Any],
    normalize_request_attachments_fn,
    persist_conversation_fn,
    build_turn_blocks_fn: Callable[..., tuple[list[dict[str, Any]], list[dict[str, Any]]]],
    create_document_fn,
    document_to_dict_fn,
    derive_rag_canvas_title_fn: Callable[[str, str], str],
    emit_activity_fn: Callable[..., None],
) -> dict[str, Any]:
    record_trace_event(
        "delivery.started",
        {
            "user_id": user_id,
            "mode_variant": retrieval["mode_variant"],
            "conversation_id": retrieval["conversation_id"],
        },
    )
    message = retrieval["message"]
    answer = answering["answer"]
    info_text = answering["info_text"]
    info_panel = answering["info_panel"]
    mindmap_payload = answering["mindmap_payload"]
    snippets_with_refs = answering["snippets_with_refs"]
    source_usage = answering["source_usage"]
    claim_signal_summary = answering["claim_signal_summary"]
    citation_quality_metrics = answering["citation_quality_metrics"]
    sources_used = answering["sources_used"]
    llm_start_ms = answering["llm_start_ms"]

    data_source = retrieval["data_source"]
    chat_history = retrieval["chat_history"]
    chat_state = retrieval["chat_state"]
    mode_variant = retrieval["mode_variant"]
    display_mode = retrieval["display_mode"]
    selected_scope_ids = retrieval["selected_scope_ids"]
    selected_scope_count = retrieval["selected_scope_count"]
    covered_scope_count = retrieval["covered_scope_count"]
    raw_snippets = retrieval["raw_snippets"]
    snippets = retrieval["snippets"]
    focus_meta = retrieval["focus_meta"]
    turn_start_ms = retrieval["turn_start_ms"]
    retrieval_end_ms = retrieval["retrieval_end_ms"]
    conversation_id = retrieval["conversation_id"]
    conversation_name = retrieval["conversation_name"]
    activity_run_id = retrieval["activity_run_id"]

    blocks, documents = build_turn_blocks_fn(answer_text=answer, question=message)
    chat_answer = answer
    if mode_variant == "rag":
        canvas_title = derive_rag_canvas_title_fn(message, answer)
        canvas_doc = create_document_fn(
            user_id,
            canvas_title,
            answer,
            info_html=info_text,
            info_panel=info_panel,
            user_prompt=message,
            mode_variant="rag",
            source_agent_id="rag",
        )
        canvas_record = {**document_to_dict_fn(canvas_doc), "mode_variant": "rag"}
        documents = [canvas_record]
        blocks = [{
            "type": "document_action",
            "action": {
                "kind": "open_canvas",
                "title": canvas_title,
                "documentId": canvas_doc.id,
            },
        }]
        chat_answer = answer
        info_panel["rag_canvas_document_id"] = canvas_doc.id
        info_panel["rag_canvas_title"] = canvas_title
        info_panel["rag_answer_mirrored"] = True
        record_trace_event(
            "delivery.canvas_created",
            {
                "conversation_id": conversation_id,
                "document_id": canvas_doc.id,
                "title": canvas_title,
            },
        )

    messages = chat_history + [[message, answer]]
    retrieval_history = deepcopy(data_source.get("retrieval_messages", []))
    retrieval_history.append(info_text)
    plot_history = deepcopy(data_source.get("plot_history", []))
    plot_history.append(None)
    turn_end_ms = int(time.monotonic() * 1000)
    cited_count = sum(
        1 for row in snippets_with_refs
        if str(row.get("ref", "") or "") and f"[{row.get('ref', '')}]" in answer
    )
    score_vals = [
        float(row.get("score", 0.0) or 0.0)
        for row in snippets_with_refs
        if row.get("score") is not None
    ]
    perf: dict[str, Any] = {
        "snippets_retrieved": len(raw_snippets),
        "snippets_after_focus": focus_meta.get("focus_filter_count_after", len(snippets)),
        "snippets_sent_to_llm": len(snippets_with_refs),
        "snippets_cited": cited_count,
        "retrieval_score_avg": round(sum(score_vals) / len(score_vals), 4) if score_vals else None,
        "retrieval_score_p50": None,
        "context_tokens_used": focus_meta.get("context_budget_used", 0),
        "context_tokens_budget": focus_meta.get("context_budget_limit", 6000),
        "mode_requested": display_mode,
        "mode_actually_used": display_mode,
        "halt_reason": None,
        "mindmap_generated": bool(mindmap_payload),
        "focus_applied": bool(focus_meta.get("focus_applied")),
        "focus_filter_count_before": focus_meta.get("focus_filter_count_before", 0),
        "focus_filter_count_after": focus_meta.get("focus_filter_count_after", 0),
        "retrieval_ms": retrieval_end_ms - turn_start_ms,
        "llm_ms": turn_end_ms - llm_start_ms,
        "total_turn_ms": turn_end_ms - turn_start_ms,
    }
    info_panel["perf"] = perf
    if mode_variant == "rag":
        emit_activity_fn(
            event_type="document_review_completed",
            title="RAG review complete",
            detail=(
                f"Answered from {covered_scope_count} reviewed file(s) with citations."
                if selected_scope_ids
                else "Answered from indexed sources with citations."
            ),
            data={
                "scene_surface": "document",
                "scene_family": "document",
                "selected_file_count": selected_scope_count,
                "covered_file_count": covered_scope_count,
            },
            stage="verification",
            status="success",
        )

    message_meta = deepcopy(data_source.get("message_meta", []))
    turn_attachments = normalize_request_attachments_fn(request)
    message_meta.append(
        {
            "mode": "ask",
            "activity_run_id": activity_run_id if mode_variant == "rag" else None,
            "actions_taken": [],
            "sources_used": sources_used,
            "source_usage": source_usage,
            "attachments": turn_attachments,
            "claim_signal_summary": claim_signal_summary,
            "citation_quality_metrics": citation_quality_metrics,
            "next_recommended_steps": [],
            "info_panel": info_panel,
            "mindmap": mindmap_payload,
            "blocks": blocks,
            "documents": documents,
            "halt_reason": None,
            "mode_requested": display_mode,
            "mode_actually_used": display_mode,
            "perf": perf,
        }
    )

    conversation_payload = {
        "selected": retrieval["selected_payload"],
        "messages": messages,
        "retrieval_messages": retrieval_history,
        "plot_history": plot_history,
        "message_meta": message_meta,
        "state": chat_state,
        "likes": deepcopy(data_source.get("likes", [])),
    }
    persist_conversation_fn(conversation_id, conversation_payload)
    record_trace_event(
        "delivery.completed",
        {
            "conversation_id": conversation_id,
            "answer_length": len(str(chat_answer or answer or "")),
            "block_count": len(blocks),
            "document_count": len(documents),
            "source_count": len(sources_used),
        },
    )
    info_panel["trace_summary"] = summarize_trace()

    return {
        "conversation_id": conversation_id,
        "conversation_name": conversation_name,
        "message": message,
        "answer": chat_answer,
        "blocks": blocks,
        "documents": documents,
        "info": info_text,
        "plot": None,
        "state": chat_state,
        "mode": "ask",
        "actions_taken": [],
        "sources_used": sources_used,
        "source_usage": source_usage,
        "claim_signal_summary": claim_signal_summary,
        "citation_quality_metrics": citation_quality_metrics,
        "next_recommended_steps": [],
        "activity_run_id": activity_run_id if mode_variant == "rag" else None,
        "info_panel": info_panel,
        "mindmap": mindmap_payload,
        "halt_reason": None,
        "mode_requested": display_mode,
        "mode_actually_used": display_mode,
    }
