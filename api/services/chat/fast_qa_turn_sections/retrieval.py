from __future__ import annotations

import time
from copy import deepcopy
from typing import Any, Callable
from urllib.parse import urlparse

from sqlmodel import Session, select

from ktem.db.models import engine

from api.services.observability.citation_trace import record_trace_event


def _selected_source_credibility(label: str, source_type: str) -> str:
    normalized_type = str(source_type or "").strip().lower()
    normalized_label = str(label or "").strip().lower()
    if normalized_type in {"file", "pdf"}:
        return "platform"
    try:
        host = (urlparse(normalized_label).netloc or "").strip().lower()
    except Exception:
        host = ""
    if host.startswith("www."):
        host = host[4:]
    if host in {"example.com", "example.org", "example.net", "localhost", "127.0.0.1"}:
        return "low"
    if host.endswith(".gov") or host.endswith(".edu") or host.startswith(("docs.", "developer.", "developers.", "research.")):
        return "high"
    if host.endswith(("nature.com", "arxiv.org", "openml.org", "jmlr.org", "ibm.com", "microsoft.com", "google.com", "openai.com")):
        return "high"
    if host.endswith(("w3schools.com", "geeksforgeeks.org", "tutorialspoint.com", "javatpoint.com")):
        return "low"
    return "medium"


def _resolve_selected_scope_sources(
    *,
    context,
    user_id: str,
    selected_payload: dict[str, Any],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_index_id, payload in (selected_payload or {}).items():
        if not isinstance(payload, list) or len(payload) < 2:
            continue
        mode = str(payload[0] or "").strip().lower()
        if mode != "select":
            continue
        selected_ids = [
            str(item).strip()
            for item in (payload[1] if isinstance(payload[1], list) else [])
            if str(item).strip()
        ]
        if not selected_ids:
            continue
        try:
            index = context.get_index(int(str(raw_index_id)))
        except Exception:
            try:
                index = context.get_index(raw_index_id)
            except Exception:
                continue
        Source = index._resources.get("Source")
        if Source is None:
            continue
        with Session(engine) as session:
            stmt = select(Source.id, Source.name).where(Source.id.in_(selected_ids))
            if index.config.get("private", False):
                stmt = stmt.where(Source.user == user_id)
            result_rows = session.execute(stmt).all()
        name_by_id = {str(row[0]): str(row[1] or "").strip() for row in result_rows}
        for source_id in selected_ids:
            if source_id in seen:
                continue
            seen.add(source_id)
            label = name_by_id.get(source_id, source_id)
            source_type = "web" if label.startswith(("http://", "https://")) else ("pdf" if label.lower().endswith(".pdf") else "file")
            rows.append(
                {
                    "file_id": source_id,
                    "label": label,
                    "source_type": source_type,
                    "credibility_tier": _selected_source_credibility(label, source_type),
                    "url": label if source_type == "web" else "",
                }
            )
    return rows


def run_retrieval_phase(
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
    constants: dict[str, Any],
    selected_scope_file_ids_fn: Callable[[dict[str, Any]], list[str]],
    emit_activity_fn: Callable[..., None],
) -> dict[str, Any] | None:
    message = request.message.strip()
    record_trace_event(
        "retrieval.started",
        {
            "message": message[:400],
            "agent_mode": str(getattr(request, "agent_mode", "") or ""),
        },
    )
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
    record_trace_event(
        "retrieval.query_rewritten",
        {
            "is_follow_up": bool(is_follow_up),
            "rewrite_reason": rewrite_reason,
            "query": retrieval_query[:400],
            "target_url_count": len(url_targets),
        },
    )
    logger.warning(
        "fast_qa_retrieval_query follow_up=%s rewrite_reason=%s query=%s targets=%s question=%s",
        bool(is_follow_up),
        constants["truncate_for_log_fn"](rewrite_reason, 120),
        constants["truncate_for_log_fn"](retrieval_query, 220),
        ",".join(url_targets[:3]) if url_targets else "(none)",
        constants["truncate_for_log_fn"](message, 220),
    )

    turn_start_ms = int(time.monotonic() * 1000)
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
    normalized_agent_mode = str(request.agent_mode or "").strip().lower()
    mode_variant = (
        "rag"
        if normalized_agent_mode == "rag" or (normalized_agent_mode == "ask" and rag_enabled)
        else ""
    )
    display_mode = mode_variant or "ask"

    retrieval_max_sources = max(constants["API_FAST_QA_SOURCE_SCAN"], constants["API_FAST_QA_MAX_SOURCES"])
    retrieval_max_chunks = max(18, int(constants["API_FAST_QA_MAX_SNIPPETS"]) * 3)
    max_keep = max(1, int(constants["API_FAST_QA_MAX_SNIPPETS"]))
    selected_scope_ids = selected_scope_file_ids_fn(selected_payload)
    selected_scope_sources = _resolve_selected_scope_sources(
        context=context,
        user_id=user_id,
        selected_payload=selected_payload,
    )

    if mode_variant == "rag":
        scope_detail = (
            f"Checking {len(selected_scope_ids)} selected files before answering."
            if selected_scope_ids
            else "Checking indexed files and URLs already selected in Maia."
        )
        emit_activity_fn(
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
    seen_sources: dict[str, None] = {}
    for row in raw_snippets:
        name = str(row.get("source_name", "") or row.get("source_url", "") or "").strip()
        if name:
            seen_sources[name] = None
    all_project_sources = list(seen_sources.keys())
    record_trace_event(
        "retrieval.candidates_loaded",
        {
            "raw_snippet_count": len(raw_snippets),
            "source_count": len(all_project_sources),
            "selected_scope_count": len(selected_scope_ids),
        },
    )

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
            emit_activity_fn(
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

    retrieval_end_ms = int(time.monotonic() * 1000)
    snippets, primary_source_note, selection_reason, focus_meta = finalize_retrieved_snippets_fn(
        question=message,
        chat_history=chat_history,
        retrieved_snippets=raw_snippets,
        selected_payload=selected_payload,
        target_urls=url_targets,
        mindmap_focus=request.mindmap_focus,
        max_keep=max_keep,
    )
    record_trace_event(
        "retrieval.selected",
        {
            "snippet_count": len(snippets),
            "selection_reason": selection_reason,
            "primary_source_note_present": bool(primary_source_note),
        },
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
        snippets, primary_source_note, selection_reason, focus_meta = finalize_retrieved_snippets_fn(
            question=message,
            chat_history=chat_history,
            retrieved_snippets=raw_snippets,
            selected_payload=selected_payload,
            target_urls=url_targets,
            mindmap_focus=request.mindmap_focus,
            max_keep=max_keep,
        )

    if selection_reason in {
        "no_snippets",
        "no_primary_for_url",
        "no_primary_after_selection",
        "no_relevant_snippets_for_url",
    }:
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
        else:
            logger.warning(
                "fast_qa_skipped reason=%s targets=%s question=%s",
                selection_reason,
                ",".join(url_targets[:3]),
                constants["truncate_for_log_fn"](message, 220),
            )
        record_trace_event(
            "retrieval.skipped",
            {
                "reason": selection_reason,
                "snippet_count": len(snippets),
                "raw_snippet_count": len(raw_snippets),
            },
        )
        if mode_variant == "rag":
            return {
                "skip": False,
                "message": message,
                "conversation_id": conversation_id,
                "conversation_name": conversation_name,
                "data_source": data_source,
                "chat_history": chat_history,
                "chat_state": chat_state,
                "requested_language": requested_language,
                "selected_payload": selected_payload,
                "selected_scope_ids": selected_scope_ids,
                "selected_scope_count": len(selected_scope_ids),
                "selected_scope_sources": selected_scope_sources,
                "covered_scope_count": 0,
                "url_targets": url_targets,
                "retrieval_query": retrieval_query,
                "is_follow_up": is_follow_up,
                "mode_variant": mode_variant,
                "display_mode": display_mode,
                "turn_start_ms": turn_start_ms,
                "retrieval_end_ms": int(time.monotonic() * 1000),
                "raw_snippets": raw_snippets,
                "snippets": [],
                "primary_source_note": primary_source_note,
                "focus_meta": focus_meta,
                "evidence_confidence": 0.0,
                "evidence_reason": (
                    "No directly relevant evidence was found in Maia files, documents, or indexed URLs for this request."
                ),
                "all_project_sources": all_project_sources,
            }
        return {"skip": True, "skip_reason": selection_reason}

    selected_scope_count = len(selected_scope_ids)
    evidence_sufficient, evidence_confidence, evidence_reason = assess_evidence_sufficiency_with_llm_fn(
        question=message,
        chat_history=chat_history,
        snippets=snippets,
        primary_source_note=primary_source_note,
        require_primary_source=bool(url_targets),
    )
    record_trace_event(
        "retrieval.sufficiency_checked",
        {
            "evidence_sufficient": bool(evidence_sufficient),
            "evidence_confidence": round(float(evidence_confidence), 4),
            "evidence_reason": evidence_reason[:400],
            "snippet_count": len(snippets),
        },
    )
    should_retry_retrieval = (
        not evidence_sufficient
        and bool(message)
        and (bool(url_targets) or bool(is_follow_up) or bool(chat_history))
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
        record_trace_event(
            "retrieval.second_pass_started",
            {
                "expanded_query": expanded_query[:400],
                "expansion_reason": expansion_reason[:240],
                "insufficiency_reason": evidence_reason[:240],
            },
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
            second_snippets, second_primary_note, second_selection_reason, second_focus_meta = finalize_retrieved_snippets_fn(
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
                if second_snippets and (second_sufficient or second_confidence > evidence_confidence or not snippets):
                    snippets = second_snippets
                    primary_source_note = second_primary_note
                    evidence_sufficient = second_sufficient
                    evidence_confidence = second_confidence
                    evidence_reason = second_reason
                    retrieval_query = expanded_query
                    focus_meta = second_focus_meta
                    logger.warning(
                        "fast_qa_retrieval_second_pass_applied sufficient=%s confidence=%.3f note=%s",
                        bool(evidence_sufficient),
                        float(evidence_confidence),
                        constants["truncate_for_log_fn"](evidence_reason, 180),
                    )
                    record_trace_event(
                        "retrieval.second_pass_applied",
                        {
                            "snippet_count": len(snippets),
                            "evidence_sufficient": bool(evidence_sufficient),
                            "evidence_confidence": round(float(evidence_confidence), 4),
                        },
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
            f"Selected scope review: {covered_scope_count} of {len(selected_scope_ids)} selected files surfaced candidate material during retrieval."
        )
        if primary_source_note:
            primary_source_note = f"{primary_source_note}\n{scope_review_note}"
        else:
            primary_source_note = scope_review_note

    if mode_variant == "rag":
        emit_activity_fn(
            event_type="document_synthesis_started",
            title="Synthesizing answer from selected sources",
            detail=scope_review_note or "Reconciling evidence across the indexed selection.",
            data={
                "scene_surface": "document",
                "scene_family": "document",
                "selected_file_count": len(selected_scope_ids),
                "covered_file_count": covered_scope_count,
                "evidence_confidence": round(float(evidence_confidence), 4),
                "evidence_reason": evidence_reason,
            },
            stage="planning",
        )

    if bool(url_targets) and not evidence_sufficient and mode_variant != "rag":
        logger.warning(
            "fast_qa_skipped reason=insufficient_evidence_for_url targets=%s confidence=%.3f note=%s question=%s",
            ",".join(url_targets[:3]),
            float(evidence_confidence),
            constants["truncate_for_log_fn"](evidence_reason, 180),
            constants["truncate_for_log_fn"](message, 220),
        )
        record_trace_event(
            "retrieval.skipped",
            {
                "reason": "insufficient_evidence_for_url",
                "evidence_confidence": round(float(evidence_confidence), 4),
            },
        )
        return {"skip": True, "skip_reason": "insufficient_evidence_for_url"}

    record_trace_event(
        "retrieval.completed",
        {
            "snippet_count": len(snippets),
            "covered_scope_count": covered_scope_count,
            "selected_scope_count": len(selected_scope_ids),
            "evidence_sufficient": bool(evidence_sufficient),
            "evidence_confidence": round(float(evidence_confidence), 4),
        },
    )
    return {
        "skip": False,
        "message": message,
        "conversation_id": conversation_id,
        "conversation_name": conversation_name,
        "data_source": data_source,
        "chat_history": chat_history,
        "chat_state": chat_state,
        "requested_language": requested_language,
        "selected_payload": selected_payload,
        "selected_scope_ids": selected_scope_ids,
        "selected_scope_count": len(selected_scope_ids),
        "selected_scope_sources": selected_scope_sources,
        "covered_scope_count": covered_scope_count,
        "url_targets": url_targets,
        "retrieval_query": retrieval_query,
        "is_follow_up": is_follow_up,
        "mode_variant": mode_variant,
        "display_mode": display_mode,
        "turn_start_ms": turn_start_ms,
        "retrieval_end_ms": retrieval_end_ms,
        "raw_snippets": raw_snippets,
        "snippets": snippets,
        "primary_source_note": primary_source_note,
        "focus_meta": focus_meta,
        "evidence_confidence": evidence_confidence,
        "evidence_reason": evidence_reason,
        "all_project_sources": all_project_sources,
    }
