from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import HTTPException

from api.message_blocks import normalize_turn_structured_content


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
) -> dict[str, Any] | None:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is empty.")
    if request.command not in (None, "", default_setting):
        logger.warning(
            "fast_qa_skipped reason=command_override command=%s",
            str(request.command or "").strip()[:80],
        )
        return None

    conversation_id, conversation_name, data_source, conversation_icon_key = get_or_create_conversation_fn(
        user_id=user_id,
        conversation_id=request.conversation_id,
    )
    conversation_name, conversation_icon_key = maybe_autoname_conversation_fn(
        user_id=user_id,
        conversation_id=conversation_id,
        current_name=conversation_name,
        message=message,
        agent_mode=request.agent_mode,
    )
    data_source = deepcopy(data_source or {})
    data_source["conversation_icon_key"] = conversation_icon_key
    chat_history = deepcopy(data_source.get("messages", []))
    chat_state = deepcopy(data_source.get("state", constants["STATE"]))
    requested_language = resolve_response_language_fn(request.language, message)

    selected_payload = build_selected_payload_fn(
        context=context,
        user_id=user_id,
        existing_selected=data_source.get("selected", {}),
        requested_selected=request.index_selection,
    )
    url_targets = resolve_contextual_url_targets_fn(
        question=message,
        chat_history=chat_history,
        max_urls=6,
    )
    retrieval_query, is_follow_up, rewrite_reason = rewrite_followup_question_for_retrieval_fn(
        question=message,
        chat_history=chat_history,
        target_urls=url_targets,
    )
    retrieval_query = retrieval_query or message
    logger.warning(
        "fast_qa_retrieval_query follow_up=%s rewrite_reason=%s query=%s targets=%s question=%s",
        bool(is_follow_up),
        constants["truncate_for_log_fn"](rewrite_reason, 120),
        constants["truncate_for_log_fn"](retrieval_query, 220),
        ",".join(url_targets[:3]) if url_targets else "(none)",
        constants["truncate_for_log_fn"](message, 220),
    )

    retrieval_max_sources = max(constants["API_FAST_QA_SOURCE_SCAN"], constants["API_FAST_QA_MAX_SOURCES"])
    retrieval_max_chunks = max(18, int(constants["API_FAST_QA_MAX_SNIPPETS"]) * 3)
    max_keep = max(1, int(constants["API_FAST_QA_MAX_SNIPPETS"]))

    raw_snippets = load_recent_chunks_for_fast_qa_fn(
        context=context,
        user_id=user_id,
        selected_payload=selected_payload,
        query=retrieval_query,
        max_sources=retrieval_max_sources,
        max_chunks=retrieval_max_chunks,
    )
    # Collect all unique source names from the full scan — passed to the LLM so it
    # knows the project's total scope, even for sources that don't fit in the context.
    _seen_sources: dict[str, None] = {}
    for _row in raw_snippets:
        _name = str(_row.get("source_name", "") or _row.get("source_url", "") or "").strip()
        if _name:
            _seen_sources[_name] = None
    all_project_sources = list(_seen_sources.keys())

    snippets, primary_source_note, selection_reason = finalize_retrieved_snippets_fn(
        question=message,
        chat_history=chat_history,
        retrieved_snippets=raw_snippets,
        selected_payload=selected_payload,
        target_urls=url_targets,
        mindmap_focus=request.mindmap_focus if isinstance(request.mindmap_focus, dict) else {},
        max_keep=max_keep,
    )

    if selection_reason == "no_snippets" and retrieval_query != message:
        logger.warning(
            "fast_qa_retrieval_retry fallback=literal_query first_query=%s question=%s",
            constants["truncate_for_log_fn"](retrieval_query, 220),
            constants["truncate_for_log_fn"](message, 220),
        )
        raw_snippets = load_recent_chunks_for_fast_qa_fn(
            context=context,
            user_id=user_id,
            selected_payload=selected_payload,
            query=message,
            max_sources=retrieval_max_sources,
            max_chunks=retrieval_max_chunks,
        )
        snippets, primary_source_note, selection_reason = finalize_retrieved_snippets_fn(
            question=message,
            chat_history=chat_history,
            retrieved_snippets=raw_snippets,
            selected_payload=selected_payload,
            target_urls=url_targets,
            mindmap_focus=request.mindmap_focus if isinstance(request.mindmap_focus, dict) else {},
            max_keep=max_keep,
        )

    if selection_reason == "no_snippets":
        logger.warning(
            "fast_qa_skipped reason=no_snippets query=%s question=%s",
            constants["truncate_for_log_fn"](retrieval_query, 220),
            constants["truncate_for_log_fn"](message, 220),
        )
        if url_targets:
            logger.warning(
                "fast_qa_skipped reason=no_snippets_for_url_context targets=%s question=%s",
                ",".join(url_targets[:3]),
                constants["truncate_for_log_fn"](message, 220),
            )
        return None
    if selection_reason == "no_primary_for_url":
        logger.warning(
            "fast_qa_skipped reason=no_primary_for_url targets=%s question=%s",
            ",".join(url_targets[:3]),
            constants["truncate_for_log_fn"](message, 220),
        )
        return None
    if selection_reason == "no_primary_after_selection":
        logger.warning(
            "fast_qa_skipped reason=no_primary_after_selection targets=%s question=%s",
            ",".join(url_targets[:3]),
            constants["truncate_for_log_fn"](message, 220),
        )
        return None
    if selection_reason == "no_relevant_snippets_for_url":
        logger.warning(
            "fast_qa_skipped reason=no_relevant_snippets_for_url targets=%s question=%s",
            ",".join(url_targets[:3]),
            constants["truncate_for_log_fn"](message, 220),
        )
        return None

    evidence_sufficient, evidence_confidence, evidence_reason = assess_evidence_sufficiency_with_llm_fn(
        question=message,
        chat_history=chat_history,
        snippets=snippets,
        primary_source_note=primary_source_note,
        require_primary_source=bool(url_targets),
    )
    should_retry_retrieval = (
        not evidence_sufficient
        and bool(message)
        and (
            bool(url_targets)
            or bool(is_follow_up)
            or bool(chat_history)
        )
    )
    if should_retry_retrieval:
        expanded_query, expansion_reason = expand_retrieval_query_for_gap_fn(
            question=message,
            current_query=retrieval_query,
            chat_history=chat_history,
            snippets=snippets,
            insufficiency_reason=evidence_reason,
            target_urls=url_targets,
        )
        expanded_query = expanded_query or retrieval_query
        logger.warning(
            "fast_qa_retrieval_second_pass reason=%s insufficiency=%s query=%s question=%s",
            constants["truncate_for_log_fn"](expansion_reason, 140),
            constants["truncate_for_log_fn"](evidence_reason, 180),
            constants["truncate_for_log_fn"](expanded_query, 220),
            constants["truncate_for_log_fn"](message, 220),
        )
        if expanded_query != retrieval_query or selection_reason in {"no_relevant_snippets", ""}:
            second_raw_snippets = load_recent_chunks_for_fast_qa_fn(
                context=context,
                user_id=user_id,
                selected_payload=selected_payload,
                query=expanded_query,
                max_sources=max(retrieval_max_sources, constants["API_FAST_QA_MAX_SOURCES"] + 16),
                max_chunks=max(retrieval_max_chunks, int(constants["API_FAST_QA_MAX_SNIPPETS"]) * 5),
            )
            second_snippets, second_primary_note, second_selection_reason = finalize_retrieved_snippets_fn(
                question=message,
                chat_history=chat_history,
                retrieved_snippets=second_raw_snippets,
                selected_payload=selected_payload,
                target_urls=url_targets,
                mindmap_focus=request.mindmap_focus if isinstance(request.mindmap_focus, dict) else {},
                max_keep=max_keep,
            )
            if second_selection_reason in {
                "no_primary_for_url",
                "no_primary_after_selection",
                "no_relevant_snippets_for_url",
            }:
                logger.warning(
                    "fast_qa_retrieval_second_pass_skipped reason=%s targets=%s question=%s",
                    second_selection_reason,
                    ",".join(url_targets[:3]),
                    constants["truncate_for_log_fn"](message, 220),
                )
            elif second_selection_reason != "no_snippets":
                second_sufficient, second_confidence, second_reason = assess_evidence_sufficiency_with_llm_fn(
                    question=message,
                    chat_history=chat_history,
                    snippets=second_snippets,
                    primary_source_note=second_primary_note,
                    require_primary_source=bool(url_targets),
                )
                if second_snippets and (
                    second_sufficient
                    or second_confidence > evidence_confidence
                    or not snippets
                ):
                    snippets = second_snippets
                    primary_source_note = second_primary_note
                    evidence_sufficient = second_sufficient
                    evidence_confidence = second_confidence
                    evidence_reason = second_reason
                    retrieval_query = expanded_query
                    logger.warning(
                        "fast_qa_retrieval_second_pass_applied sufficient=%s confidence=%.3f note=%s",
                        bool(evidence_sufficient),
                        float(evidence_confidence),
                        constants["truncate_for_log_fn"](evidence_reason, 180),
                    )

    if bool(url_targets) and not evidence_sufficient:
        logger.warning(
            "fast_qa_skipped reason=insufficient_evidence_for_url targets=%s confidence=%.3f note=%s question=%s",
            ",".join(url_targets[:3]),
            float(evidence_confidence),
            constants["truncate_for_log_fn"](evidence_reason, 180),
            constants["truncate_for_log_fn"](message, 220),
        )
        return None

    if snippets:
        snippets_with_refs, refs = constants["assign_fast_source_refs_fn"](snippets)
        answer = call_openai_fast_qa_fn(
            question=message,
            snippets=snippets_with_refs,
            chat_history=chat_history,
            refs=refs,
            citation_mode=request.citation,
            primary_source_note=primary_source_note,
            requested_language=requested_language,
            is_follow_up=is_follow_up,
            all_project_sources=all_project_sources,
        )
        if not answer:
            logger.warning(
                "fast_qa_skipped reason=no_model_answer snippets=%d refs=%d question=%s",
                len(snippets_with_refs),
                len(refs),
                constants["truncate_for_log_fn"](message, 220),
            )
            return None
        answer = normalize_fast_answer_fn(answer, question=message)
        used_general_fallback = False
    else:
        logger.warning(
            "fast_qa_no_relevant_snippets question=%s",
            constants["truncate_for_log_fn"](message, 220),
        )
        snippets_with_refs, refs = [], []
        answer = call_openai_fast_qa_fn(
            question=message,
            snippets=[],
            chat_history=chat_history,
            refs=[],
            citation_mode=request.citation,
            primary_source_note=primary_source_note,
            requested_language=requested_language,
            allow_general_knowledge=True,
            is_follow_up=is_follow_up,
            all_project_sources=all_project_sources,
        )
        used_general_fallback = bool(answer)
        if answer:
            answer = normalize_fast_answer_fn(answer, question=message)
        else:
            answer = build_no_relevant_evidence_answer_fn(
                message,
                response_language=requested_language,
            )
            used_general_fallback = False

    resolved_citation_mode = resolve_required_citation_mode_fn(request.citation)
    if refs:
        answer = render_fast_citation_links_fn(
            answer=answer,
            refs=refs,
            citation_mode=resolved_citation_mode,
        )

    info_text = build_fast_info_html_fn(snippets_with_refs, max_blocks=6)
    if refs or not used_general_fallback:
        answer = enforce_required_citations_fn(
            answer=answer,
            info_html=info_text,
            citation_mode=resolved_citation_mode,
        )

    logger.warning(
        "fast_qa_completed snippets=%d refs=%d answer_chars=%d",
        len(snippets_with_refs),
        len(refs),
        len(answer),
    )
    source_usage = build_source_usage_fn(
        snippets_with_refs=snippets_with_refs,
        refs=refs,
        answer_text=answer,
        enabled=constants["MAIA_SOURCE_USAGE_HEATMAP_ENABLED"],
    )
    claim_signal_summary = build_claim_signal_summary_fn(
        answer_text=answer,
        refs=refs,
    )
    citation_quality_metrics = build_citation_quality_metrics_fn(
        snippets_with_refs=snippets_with_refs,
        refs=refs,
        answer_text=answer,
    )
    max_citation_share = max(
        (float(item.get("citation_share", 0.0) or 0.0) for item in source_usage),
        default=0.0,
    )
    source_dominance_detected = bool(
        source_usage and max_citation_share > float(constants["MAIA_CITATION_DOMINANCE_WARNING_THRESHOLD"])
    )
    source_dominance_warning = (
        "This answer depends heavily on one source; consider reviewing other documents for broader context."
        if source_dominance_detected
        else ""
    )
    info_panel = build_info_panel_copy_fn(
        request_message=message,
        answer_text=answer,
        info_html=info_text,
        mode="ask",
        next_steps=[],
        web_summary={},
    )

    mindmap_payload: dict[str, Any] = {}
    if bool(request.use_mindmap):
        map_settings = dict(request.mindmap_settings or {})
        try:
            map_depth = int(map_settings.get("max_depth", 4))
        except Exception:
            map_depth = 4
        map_type = str(map_settings.get("map_type", "structure") or "structure").strip().lower()
        if map_type not in {"structure", "evidence", "work_graph", "context_mindmap"}:
            map_type = "structure"
        build_map_type = "structure" if map_type == "context_mindmap" else map_type
        mindmap_payload = build_knowledge_map_fn(
            question=message,
            context="\n\n".join(str(row.get("text", "") or "") for row in snippets[:8]),
            documents=snippets,
            answer_text=answer,
            max_depth=max(2, min(8, map_depth)),
            include_reasoning_map=bool(map_settings.get("include_reasoning_map", True)),
            source_type_hint=str(map_settings.get("source_type_hint", "") or ""),
            focus=request.mindmap_focus if isinstance(request.mindmap_focus, dict) else {},
            map_type=build_map_type,
        )
        if map_type == "context_mindmap":
            mindmap_payload["map_type"] = "context_mindmap"
            mindmap_payload["kind"] = "context_mindmap"
            settings_payload = mindmap_payload.get("settings")
            if isinstance(settings_payload, dict):
                settings_payload["map_type"] = "context_mindmap"
        info_panel["mindmap"] = mindmap_payload

    if source_usage:
        info_panel["source_usage"] = source_usage
    info_panel["verification_contract_version"] = constants["VERIFICATION_CONTRACT_VERSION"]

    normalized_evidence_items = build_verification_evidence_items_fn(
        snippets_with_refs=snippets_with_refs,
        refs=refs,
    )
    if normalized_evidence_items:
        info_panel["evidence_items"] = normalized_evidence_items
        web_review_content = build_web_review_content_fn(normalized_evidence_items)
        if web_review_content:
            info_panel["web_review_content"] = web_review_content
    if claim_signal_summary:
        info_panel["claim_signal_summary"] = claim_signal_summary
    if citation_quality_metrics:
        info_panel["citation_quality_metrics"] = citation_quality_metrics
    if source_dominance_warning:
        info_panel["source_dominance_warning"] = source_dominance_warning
    if primary_source_note:
        info_panel["primary_source_note"] = primary_source_note
    if used_general_fallback:
        info_panel["answer_origin"] = "llm_general_knowledge"
    info_panel["citation_strength_ordering"] = bool(constants["MAIA_CITATION_STRENGTH_ORDERING_ENABLED"])
    info_panel["citation_strength_legend"] = (
        "Citation numbers are normalized per answer: each source appears once and numbering starts at 1."
    )
    blocks, documents = normalize_turn_structured_content(answer_text=answer)

    messages = chat_history + [[message, answer]]
    retrieval_history = deepcopy(data_source.get("retrieval_messages", []))
    retrieval_history.append(info_text)
    plot_history = deepcopy(data_source.get("plot_history", []))
    plot_history.append(None)
    message_meta = deepcopy(data_source.get("message_meta", []))
    turn_attachments = normalize_request_attachments_fn(request)
    message_meta.append(
        {
            "mode": "ask",
            "activity_run_id": None,
            "actions_taken": [],
            "sources_used": [],
            "source_usage": source_usage,
            "attachments": turn_attachments,
            "claim_signal_summary": claim_signal_summary,
            "citation_quality_metrics": citation_quality_metrics,
            "next_recommended_steps": [],
            "info_panel": info_panel,
            "mindmap": mindmap_payload,
            "blocks": blocks,
            "documents": documents,
        }
    )

    conversation_payload = {
        "selected": selected_payload,
        "messages": messages,
        "retrieval_messages": retrieval_history,
        "plot_history": plot_history,
        "message_meta": message_meta,
        "state": chat_state,
        "likes": deepcopy(data_source.get("likes", [])),
    }
    persist_conversation_fn(conversation_id, conversation_payload)

    return {
        "conversation_id": conversation_id,
        "conversation_name": conversation_name,
        "message": message,
        "answer": answer,
        "blocks": blocks,
        "documents": documents,
        "info": info_text,
        "plot": None,
        "state": chat_state,
        "mode": "ask",
        "actions_taken": [],
        "sources_used": [],
        "source_usage": source_usage,
        "claim_signal_summary": claim_signal_summary,
        "citation_quality_metrics": citation_quality_metrics,
        "next_recommended_steps": [],
        "activity_run_id": None,
        "info_panel": info_panel,
        "mindmap": mindmap_payload,
    }
