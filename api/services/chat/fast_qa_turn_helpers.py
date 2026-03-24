from __future__ import annotations

import time
import uuid
from copy import deepcopy
from typing import Any, Callable

from fastapi import HTTPException

from api.services.canvas.document_store import create_document, document_to_dict
from api.services.chat.block_builder import build_turn_blocks


def _selected_scope_file_ids(selected_payload: dict[str, Any]) -> list[str]:
    selected_ids: list[str] = []
    seen: set[str] = set()
    for payload in selected_payload.values():
        if not isinstance(payload, list) or len(payload) < 2:
            continue
        mode = str(payload[0] or "").strip().lower()
        if mode != "select":
            continue
        file_ids = payload[1] if isinstance(payload[1], list) else []
        for raw_file_id in file_ids:
            file_id = str(raw_file_id or "").strip()
            if not file_id or file_id in seen:
                continue
            seen.add(file_id)
            selected_ids.append(file_id)
    return selected_ids


def _build_sources_used(
    *,
    snippets_with_refs: list[dict[str, Any]],
    refs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    candidates = list(snippets_with_refs) + list(refs)
    for row in candidates:
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("file_id") or row.get("source_id") or "").strip()
        source_name = str(row.get("source_name") or row.get("label") or "Indexed source").strip() or "Indexed source"
        source_url = str(
            row.get("source_url") or row.get("page_url") or row.get("url") or ""
        ).strip()
        source_key = source_id or source_url or source_name.lower()
        if not source_key or source_key in seen:
            continue
        seen.add(source_key)
        source_type = str(row.get("source_type", "") or "").strip().lower()
        if not source_type:
            source_type = "web" if source_url.startswith(("http://", "https://")) and not source_id else "file"
        rows.append(
            {
                "source_type": source_type,
                "label": source_name,
                "url": source_url or None,
                "file_id": source_id or None,
                "score": row.get("strength_score") or row.get("score"),
                "metadata": {
                    "page_label": str(row.get("page_label", "") or "").strip() or None,
                    "unit_id": str(row.get("unit_id", "") or "").strip() or None,
                },
            }
        )
    return rows


def _derive_rag_canvas_title(question: str, answer: str) -> str:
    first_heading = ""
    for line in str(answer or "").splitlines():
        candidate = str(line or "").strip()
        if not candidate:
            continue
        if candidate.startswith("#"):
            first_heading = candidate.lstrip("#").strip()
            break
        if len(candidate) > 24:
            break
    if first_heading:
        return first_heading[:140]
    normalized_question = str(question or "").strip().rstrip("?.! ")
    if normalized_question:
        return normalized_question[:140]
    return "RAG workspace draft"


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

    _turn_start_ms = int(time.monotonic() * 1000)
    setting_overrides = (
        dict(request.setting_overrides)
        if isinstance(request.setting_overrides, dict)
        else {}
    )
    rag_enabled = str(setting_overrides.get("__rag_mode_enabled") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    mode_variant = (
        "rag"
        if str(request.agent_mode or "").strip().lower() == "ask"
        and rag_enabled
        else ""
    )
    display_mode = mode_variant or "ask"
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

    retrieval_max_sources = max(constants["API_FAST_QA_SOURCE_SCAN"], constants["API_FAST_QA_MAX_SOURCES"])
    retrieval_max_chunks = max(18, int(constants["API_FAST_QA_MAX_SNIPPETS"]) * 3)
    max_keep = max(1, int(constants["API_FAST_QA_MAX_SNIPPETS"]))
    selected_scope_ids = _selected_scope_file_ids(selected_payload)
    if mode_variant == "rag":
        scope_detail = (
            f"Checking {len(selected_scope_ids)} selected files before answering."
            if selected_scope_ids
            else "Checking indexed files and URLs already selected in Maia."
        )
        emit_activity(
            event_type="document_review_started",
            title="Reviewing selected knowledge sources",
            detail=scope_detail,
            data={
                "scene_surface": "document",
                "scene_family": "document",
                "selected_file_count": len(selected_scope_ids),
                "query": retrieval_query,
                "mode_variant": mode_variant,
            },
            stage="planning",
        )

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
    if mode_variant == "rag":
        reviewed_sources: dict[str, dict[str, Any]] = {}
        for row in raw_snippets:
            if not isinstance(row, dict):
                continue
            source_id = str(row.get("source_id", "") or "").strip()
            source_name = str(row.get("source_name", "") or source_id or "Indexed file").strip() or "Indexed file"
            if not source_id or source_id in reviewed_sources:
                continue
            reviewed_sources[source_id] = {
                "source_id": source_id,
                "source_name": source_name,
                "page_label": str(row.get("page_label", "") or "").strip(),
                "source_url": str(row.get("source_url", "") or "").strip(),
            }
        for source_id in selected_scope_ids:
            review = reviewed_sources.get(source_id)
            emit_activity(
                event_type="pdf_review_checkpoint",
                title=review["source_name"] if review else "Selected file scanned",
                detail=(
                    f"Scanning page {review['page_label']} for relevant evidence."
                    if review and review.get("page_label")
                    else (
                        "Scanned this selected file for relevant evidence."
                        if review
                        else "No directly relevant evidence surfaced from this selected file."
                    )
                ),
                data={
                    "scene_surface": "document",
                    "scene_family": "document",
                    "file_id": source_id,
                    "source_id": source_id,
                    "file_name": review["source_name"] if review else "Selected file",
                    "source_name": review["source_name"] if review else "Selected file",
                    "source_url": review["source_url"] if review else "",
                    "page_label": review["page_label"] if review else "",
                },
                stage="execution",
            )

    _retrieval_end_ms = int(time.monotonic() * 1000)
    snippets, primary_source_note, selection_reason, _focus_meta = finalize_retrieved_snippets_fn(
        question=message,
        chat_history=chat_history,
        retrieved_snippets=raw_snippets,
        selected_payload=selected_payload,
        target_urls=url_targets,
        mindmap_focus=request.mindmap_focus,
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
        snippets, primary_source_note, selection_reason, _focus_meta = finalize_retrieved_snippets_fn(
            question=message,
            chat_history=chat_history,
            retrieved_snippets=raw_snippets,
            selected_payload=selected_payload,
            target_urls=url_targets,
            mindmap_focus=request.mindmap_focus,
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

    selected_scope_count = len(selected_scope_ids)

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
            second_snippets, second_primary_note, second_selection_reason, _second_focus_meta = finalize_retrieved_snippets_fn(
                question=message,
                chat_history=chat_history,
                retrieved_snippets=second_raw_snippets,
                selected_payload=selected_payload,
                target_urls=url_targets,
                mindmap_focus=request.mindmap_focus,
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

    covered_scope_ids = {
        str(row.get("source_id", "") or "").strip()
        for row in snippets
        if isinstance(row, dict) and str(row.get("source_id", "") or "").strip()
    }
    covered_scope_count = len(covered_scope_ids.intersection(set(selected_scope_ids))) if selected_scope_ids else len(covered_scope_ids)
    scope_review_note = ""
    if selected_scope_ids:
        scope_review_note = (
            f"Selected scope review: {covered_scope_count} of {selected_scope_count} selected files surfaced relevant evidence during retrieval."
        )
        if primary_source_note:
            primary_source_note = f"{primary_source_note}\n{scope_review_note}"
        else:
            primary_source_note = scope_review_note

    if mode_variant == "rag":
        emit_activity(
            event_type="document_synthesis_started",
            title="Synthesizing answer from selected sources",
            detail=scope_review_note or "Reconciling evidence across the indexed selection.",
            data={
                "scene_surface": "document",
                "scene_family": "document",
                "selected_file_count": selected_scope_count,
                "covered_file_count": covered_scope_count,
                "evidence_confidence": round(float(evidence_confidence), 4),
                "evidence_reason": evidence_reason,
            },
            stage="planning",
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

    _llm_start_ms = int(time.monotonic() * 1000)
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

    if mode_variant == "rag":
        emit_activity(
            event_type="doc_writing_started",
            title="Drafting evidence-grounded answer",
            detail="Writing the answer from the reviewed PDFs and indexed sources.",
            data={
                "scene_surface": "document",
                "scene_family": "document",
                "document_name": "RAG answer draft",
                "selected_file_count": selected_scope_count,
                "covered_file_count": covered_scope_count,
            },
            stage="execution",
        )

    resolved_citation_mode = resolve_required_citation_mode_fn(request.citation)
    if refs:
        answer = render_fast_citation_links_fn(
            answer=answer,
            refs=refs,
            citation_mode=resolved_citation_mode,
        )

    info_block_budget = max(12, min(max(len(refs), len(snippets_with_refs)), 24))
    info_text = build_fast_info_html_fn(snippets_with_refs, max_blocks=info_block_budget)
    if refs or not used_general_fallback:
        answer = enforce_required_citations_fn(
            answer=answer,
            info_html=info_text,
            citation_mode=resolved_citation_mode,
        )
        try:
            from api.services.chat.citation_sections.anchors import _anchors_to_bracket_markers
            from api.services.chat.citation_sections.refs import evaluate_citation_quality_gate

            citation_gate = evaluate_citation_quality_gate(answer_text=answer, refs=refs)
            if refs and not bool(citation_gate.get("passed", True)):
                repaired_answer = enforce_required_citations_fn(
                    answer=_anchors_to_bracket_markers(answer),
                    info_html=info_text,
                    citation_mode=resolved_citation_mode,
                )
                repaired_gate = evaluate_citation_quality_gate(answer_text=repaired_answer, refs=refs)
                if bool(repaired_gate.get("passed", False)) or repaired_answer != answer:
                    answer = repaired_answer
                citation_gate = repaired_gate
        except Exception:
            citation_gate = {}
    else:
        citation_gate = {}

    if mode_variant == "rag" and chunk_text_for_stream_fn is not None:
        typed_preview = ""
        for chunk in chunk_text_for_stream_fn(answer, 260):
            if not chunk:
                continue
            typed_preview += chunk
            emit_activity(
                event_type="doc_type_text",
                title="Writing answer",
                detail=chunk,
                data={
                    "scene_surface": "document",
                    "scene_family": "document",
                    "typed_preview": typed_preview,
                    "document_name": "RAG answer draft",
                },
                stage="execution",
            )
            emit_stream_event({"type": "chat_delta", "delta": chunk, "text": typed_preview})

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
    sources_used = _build_sources_used(
        snippets_with_refs=snippets_with_refs,
        refs=refs,
    )
    info_panel = build_info_panel_copy_fn(
        request_message=message,
        answer_text=answer,
        info_html=info_text,
        mode="ask",
        next_steps=[],
        web_summary={},
    )
    if mode_variant:
        info_panel["mode_variant"] = mode_variant

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
            focus=request.mindmap_focus.model_dump() if hasattr(request.mindmap_focus, "model_dump") else dict(request.mindmap_focus or {}),
            map_type=build_map_type,
        )
        if map_type == "context_mindmap":
            mindmap_payload["map_type"] = "context_mindmap"
            mindmap_payload["kind"] = "context_mindmap"
            settings_payload = mindmap_payload.get("settings")
            if isinstance(settings_payload, dict):
                settings_payload["map_type"] = "context_mindmap"
        # Backfill available_map_types when the indexer path omits it
        if "available_map_types" not in mindmap_payload:
            _all_map_keys = ["work_graph", "context_mindmap", "structure", "evidence"]
            _present = {mindmap_payload.get("map_type")} | set(
                (mindmap_payload.get("variants") or {}).keys()
            )
            mindmap_payload["available_map_types"] = [
                k for k in _all_map_keys if k in _present
            ]
        info_panel["mindmap"] = mindmap_payload

    if source_usage:
        info_panel["source_usage"] = source_usage
    if selected_scope_ids:
        info_panel["selected_scope"] = {
            "file_count": selected_scope_count,
            "covered_file_count": covered_scope_count,
            "file_ids": selected_scope_ids[:40],
        }
    if _focus_meta.get("focus_applied"):
        info_panel["mindmap_focus_metadata"] = _focus_meta
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
    if citation_gate:
        info_panel["citation_quality_gate"] = citation_gate
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
    blocks, documents = build_turn_blocks(answer_text=answer, question=message)
    chat_answer = answer
    if mode_variant == "rag":
        canvas_title = _derive_rag_canvas_title(message, answer)
        canvas_doc = create_document(
            user_id,
            canvas_title,
            answer,
            info_html=info_text,
            info_panel=info_panel,
            user_prompt=message,
            mode_variant="rag",
            source_agent_id="rag",
        )
        canvas_record = {
            **document_to_dict(canvas_doc),
            "mode_variant": "rag",
        }
        documents = [canvas_record]
        blocks = [
            {
                "type": "document_action",
                "action": {
                    "kind": "open_canvas",
                    "title": canvas_title,
                    "documentId": canvas_doc.id,
                },
            }
        ]
        chat_answer = ""
        info_panel["rag_canvas_document_id"] = canvas_doc.id
        info_panel["rag_canvas_title"] = canvas_title

    messages = chat_history + [[message, answer]]
    retrieval_history = deepcopy(data_source.get("retrieval_messages", []))
    retrieval_history.append(info_text)
    plot_history = deepcopy(data_source.get("plot_history", []))
    plot_history.append(None)
    _turn_end_ms = int(time.monotonic() * 1000)
    _cited_count = sum(
        1 for row in snippets_with_refs
        if str(row.get("ref", "") or "") and f"[{row.get('ref', '')}]" in answer
    )
    _score_vals = [
        float(row.get("score", 0.0) or 0.0)
        for row in snippets_with_refs
        if row.get("score") is not None
    ]
    _perf: dict[str, Any] = {
        "snippets_retrieved": len(raw_snippets),
        "snippets_after_focus": _focus_meta.get("focus_filter_count_after", len(snippets)),
        "snippets_sent_to_llm": len(snippets_with_refs),
        "snippets_cited": _cited_count,
        "retrieval_score_avg": round(sum(_score_vals) / len(_score_vals), 4) if _score_vals else None,
        "retrieval_score_p50": None,
        "context_tokens_used": _focus_meta.get("context_budget_used", 0),
        "context_tokens_budget": _focus_meta.get("context_budget_limit", 6000),
        "mode_requested": display_mode,
        "mode_actually_used": display_mode,
        "halt_reason": None,
        "mindmap_generated": bool(mindmap_payload),
        "focus_applied": bool(_focus_meta.get("focus_applied")),
        "focus_filter_count_before": _focus_meta.get("focus_filter_count_before", 0),
        "focus_filter_count_after": _focus_meta.get("focus_filter_count_after", 0),
        "retrieval_ms": _retrieval_end_ms - _turn_start_ms,
        "llm_ms": _turn_end_ms - _llm_start_ms,
        "total_turn_ms": _turn_end_ms - _turn_start_ms,
    }
    info_panel["perf"] = _perf
    if mode_variant == "rag":
        emit_activity(
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
            "perf": _perf,
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
