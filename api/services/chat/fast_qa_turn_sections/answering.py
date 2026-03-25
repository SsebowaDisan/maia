from __future__ import annotations

import re
import time
from typing import Any, Callable

from api.services.observability.citation_trace import record_trace_event


_QUESTION_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
_BROAD_GROUNDING_RE = re.compile(
    r"\b("
    r"why|how|explain|compare|comparison|trade[- ]?off|implication|impact|mechanism|"
    r"modification|required|requirements|environment|deployment|analy[sz]e|analysis|"
    r"advantages|disadvantages|constraints|limitations|risks|mitigation"
    r")\b",
    re.IGNORECASE,
)
_NARROW_TECHNICAL_TASK_RE = re.compile(
    r"\b("
    r"derive|calcula(?:te|tion)|compute|equation|formula|prove|solve|"
    r"material balance|mass balance|component balance|write the balance|"
    r"show the derivation|extend it to include"
    r")\b",
    re.IGNORECASE,
)
_BALANCE_VISIBLE_RE = re.compile(
    r"\b(material balance|mass balance|component balance|distillation column|feed|feeds|vapor|vapour|liquid|distillate|bottoms)\b",
    re.IGNORECASE,
)
_FORMULA_VISIBLE_RE = re.compile(
    r"(?:\$\$.*?=\s*.*?\$\$|[FDVBLMQW]\s*[xXyYzZ]?\s*_\{?[A-Za-z0-9,+\-]+\}?\s*=\s*.+)",
    re.IGNORECASE | re.DOTALL,
)

_GROUNDING_STOPWORDS = {
    "about",
    "across",
    "answer",
    "based",
    "because",
    "being",
    "between",
    "column",
    "columns",
    "different",
    "document",
    "example",
    "from",
    "high",
    "include",
    "indexed",
    "material",
    "question",
    "required",
    "requirements",
    "source",
    "specified",
    "system",
    "this",
    "were",
    "what",
    "would",
}
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*]\([^)]+\)")


def _clean_user_visible_evidence_reason(reason: str) -> str:
    text = " ".join(str(reason or "").split()).strip()
    if not text:
        return ""
    lowered = text.lower()
    if (
        "fail-open" in lowered
        or lowered.startswith("check failed")
        or "auxiliary sufficiency check skipped for provider" in lowered
    ):
        return ""
    return text


def _question_tokens(question: str) -> list[str]:
    return [
        token.lower()
        for token in _QUESTION_TOKEN_RE.findall(str(question or ""))
        if token and token.lower() not in _GROUNDING_STOPWORDS
    ]


def _sanitize_visible_excerpt(text: str) -> str:
    cleaned = str(text or "")
    cleaned = _MARKDOWN_IMAGE_RE.sub(" ", cleaned)
    cleaned = _HTML_TAG_RE.sub(" ", cleaned)
    cleaned = cleaned.replace("##", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -\n\r\t")
    return cleaned


def _looks_like_noise_excerpt(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return True
    return lowered.startswith(("figure ", "table ", "nomenclature ", "contents ", "chapter "))


def _select_visible_evidence_points(
    *,
    question: str,
    snippets_with_refs: list[dict[str, Any]],
    limit: int = 2,
) -> list[str]:
    tokens = set(_question_tokens(question))
    ranked: list[tuple[float, str]] = []
    wants_technical = bool(_NARROW_TECHNICAL_TASK_RE.search(question))
    for row in snippets_with_refs:
        ref_id = int(row.get("ref_id", 0) or 0)
        excerpt = _sanitize_visible_excerpt(str(row.get("text", "") or ""))
        if len(excerpt) < 24:
            continue
        excerpt = excerpt[:220].rstrip(" ,;:")
        overlap = sum(1 for token in tokens if token in excerpt.lower())
        penalty = 0.75 if _looks_like_noise_excerpt(excerpt) else 0.0
        score = float(overlap) - penalty
        if wants_technical:
            if _FORMULA_VISIBLE_RE.search(excerpt):
                score += 8.0
            balance_hits = len(_BALANCE_VISIBLE_RE.findall(excerpt))
            if balance_hits:
                score += min(6.0, float(balance_hits) * 1.5)
            if _looks_like_noise_excerpt(excerpt):
                score -= 3.0
        ranked.append((score, f"{excerpt} [{ref_id}]" if ref_id > 0 else excerpt))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if any(score > 0 for score, _excerpt in ranked):
        ranked = [item for item in ranked if item[0] > 0]
    chosen: list[str] = []
    seen: set[str] = set()
    for _score, excerpt in ranked:
        key = excerpt.lower()
        if key in seen:
            continue
        seen.add(key)
        chosen.append(excerpt)
        if len(chosen) >= limit:
            break
    return chosen


def _requires_broad_grounding(question: str) -> bool:
    text = " ".join(str(question or "").split()).strip()
    if not text:
        return False
    if _NARROW_TECHNICAL_TASK_RE.search(text) and not _BROAD_GROUNDING_RE.search(text):
        return False
    if len(text) >= 96:
        return True
    return bool(_BROAD_GROUNDING_RE.search(text))


def _build_evidence_limited_answer(
    *,
    question: str,
    snippets_with_refs: list[dict[str, Any]],
    evidence_reason: str,
) -> str:
    visible_points = _select_visible_evidence_points(
        question=question,
        snippets_with_refs=snippets_with_refs,
        limit=2,
    )

    lead = "The indexed source does not provide enough evidence to answer that fully."
    clean_reason = _clean_user_visible_evidence_reason(evidence_reason)
    if clean_reason:
        lead += f" {clean_reason}"
    if visible_points:
        visible_summary = "; ".join(visible_points)
        return (
            f"{lead} Visible evidence is limited to {visible_summary}. "
            "Anything beyond those visible points is not supported by the indexed content."
        )
    return (
        f"{lead}\n\n"
        "Not enough directly supporting evidence is visible in the indexed content to answer the broader question safely."
    )


def _build_unsupported_by_source_answer(*, evidence_reason: str) -> str:
    lead = "The indexed source does not provide directly relevant evidence for that question."
    clean_reason = _clean_user_visible_evidence_reason(evidence_reason)
    if clean_reason:
        lead += f" {clean_reason}"
    return (
        f"{lead}\n\n"
        "No directly relevant evidence about the requested topic is visible in the indexed content, so Maia is not extrapolating beyond the source."
    )


def _build_model_failure_answer(
    *,
    question: str,
    snippets_with_refs: list[dict[str, Any]],
) -> str:
    return _build_evidence_limited_answer(
        question=question,
        snippets_with_refs=snippets_with_refs,
        evidence_reason=(
            "The answer model was unavailable for this turn, so Maia is limiting the response to directly visible evidence only."
        ),
    )


def _question_support_ratio(
    *,
    question: str,
    snippets_with_refs: list[dict[str, Any]],
) -> float:
    tokens = [
        token.lower()
        for token in _QUESTION_TOKEN_RE.findall(str(question or ""))
        if token and token.lower() not in _GROUNDING_STOPWORDS
    ]
    unique_tokens = sorted(set(tokens))
    if not unique_tokens:
        return 1.0

    evidence_text = " ".join(
        " ".join(str(row.get("text", "") or "").split()).lower()
        for row in snippets_with_refs
        if isinstance(row, dict)
    )
    if not evidence_text:
        return 0.0

    supported = sum(1 for token in unique_tokens if token in evidence_text)
    return float(supported) / float(len(unique_tokens))


def build_answer_phase(
    *,
    request,
    logger,
    retrieval: dict[str, Any],
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
    build_sources_used_fn: Callable[..., list[dict[str, Any]]],
    chunk_text_for_stream_fn: Callable[[str, int], list[str]] | None,
    emit_activity_fn: Callable[..., None],
    emit_stream_event_fn: Callable[[dict[str, Any]], None],
    constants: dict[str, Any],
) -> dict[str, Any] | None:
    message = retrieval["message"]
    snippets = retrieval["snippets"]
    chat_history = retrieval["chat_history"]
    primary_source_note = retrieval["primary_source_note"]
    requested_language = retrieval["requested_language"]
    is_follow_up = retrieval["is_follow_up"]
    mode_variant = retrieval["mode_variant"]
    selected_scope_count = retrieval["selected_scope_count"]
    covered_scope_count = retrieval["covered_scope_count"]
    selected_scope_ids = retrieval["selected_scope_ids"]
    all_project_sources = retrieval["all_project_sources"]
    focus_meta = retrieval["focus_meta"]
    evidence_confidence = float(retrieval.get("evidence_confidence", 1.0) or 1.0)
    evidence_reason = str(retrieval.get("evidence_reason", "") or "").strip()
    record_trace_event(
        "answer.started",
        {
            "snippet_count": len(snippets),
            "mode_variant": mode_variant,
            "evidence_confidence": round(float(evidence_confidence), 4),
        },
    )

    llm_start_ms = int(time.monotonic() * 1000)
    if snippets:
        snippets_with_refs, refs = constants["assign_fast_source_refs_fn"](snippets)
        record_trace_event(
            "citation.refs_assigned",
            {
                "snippet_count": len(snippets_with_refs),
                "ref_count": len(refs),
            },
        )
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
                "fast_qa_model_answer_unavailable using=evidence_only_fallback snippets=%d refs=%d question=%s",
                len(snippets_with_refs),
                len(refs),
                constants["truncate_for_log_fn"](message, 220),
            )
            answer = _build_model_failure_answer(
                question=message,
                snippets_with_refs=snippets_with_refs,
            )
        else:
            answer = normalize_fast_answer_fn(answer, question=message)
        page_count = len(
            {
                str(row.get("page_label", "") or "").strip()
                for row in snippets_with_refs
                if str(row.get("page_label", "") or "").strip()
            }
        )
        support_ratio = _question_support_ratio(
            question=message,
            snippets_with_refs=snippets_with_refs,
        )
        if (
            _requires_broad_grounding(message)
            and evidence_confidence < 0.72
            and (
                (len(refs) <= 1 and page_count <= 1)
                or page_count <= 1
                or len(snippets_with_refs) <= 2
                or support_ratio < 0.34
            )
        ):
            logger.warning(
                "fast_qa_answer_narrowed_for_grounding confidence=%.3f refs=%d pages=%d snippets=%d support=%.3f reason=%s question=%s",
                evidence_confidence,
                len(refs),
                page_count,
                len(snippets_with_refs),
                support_ratio,
                constants["truncate_for_log_fn"](evidence_reason, 180),
                constants["truncate_for_log_fn"](message, 220),
            )
            if support_ratio < 0.34:
                answer = _build_unsupported_by_source_answer(evidence_reason=evidence_reason)
                snippets_with_refs, refs = [], []
                record_trace_event(
                    "answer.gate_narrowed",
                    {
                        "mode": "unsupported_by_source",
                        "support_ratio": round(float(support_ratio), 4),
                        "evidence_confidence": round(float(evidence_confidence), 4),
                    },
                )
            else:
                answer = _build_evidence_limited_answer(
                    question=message,
                    snippets_with_refs=snippets_with_refs,
                    evidence_reason=evidence_reason,
                )
                record_trace_event(
                    "answer.gate_narrowed",
                    {
                        "mode": "evidence_limited",
                        "support_ratio": round(float(support_ratio), 4),
                        "evidence_confidence": round(float(evidence_confidence), 4),
                    },
                )
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
        record_trace_event(
            "answer.general_fallback",
            {
                "used_general_fallback": bool(used_general_fallback),
            },
        )

    if mode_variant == "rag":
        emit_activity_fn(
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
        record_trace_event(
            "citation.enforced",
            {
                "ref_count": len(refs),
                "citation_mode": resolved_citation_mode,
            },
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
            emit_activity_fn(
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
            emit_stream_event_fn({"type": "chat_delta", "delta": chunk, "text": typed_preview})

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
    claim_signal_summary = build_claim_signal_summary_fn(answer_text=answer, refs=refs)
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
        source_usage
        and max_citation_share > float(constants["MAIA_CITATION_DOMINANCE_WARNING_THRESHOLD"])
    )
    source_dominance_warning = (
        "This answer depends heavily on one source; consider reviewing other documents for broader context."
        if source_dominance_detected
        else ""
    )
    sources_used = build_sources_used_fn(snippets_with_refs=snippets_with_refs, refs=refs)
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
        if "available_map_types" not in mindmap_payload:
            all_map_keys = ["work_graph", "context_mindmap", "structure", "evidence"]
            present = {mindmap_payload.get("map_type")} | set((mindmap_payload.get("variants") or {}).keys())
            mindmap_payload["available_map_types"] = [k for k in all_map_keys if k in present]
        info_panel["mindmap"] = mindmap_payload

    if source_usage:
        info_panel["source_usage"] = source_usage
    if selected_scope_ids:
        info_panel["selected_scope"] = {
            "file_count": selected_scope_count,
            "covered_file_count": covered_scope_count,
            "file_ids": selected_scope_ids[:40],
        }
    if focus_meta.get("focus_applied"):
        info_panel["mindmap_focus_metadata"] = focus_meta
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
    elif (
        _requires_broad_grounding(message)
        and evidence_confidence < 0.72
        and (
            not refs
            or len(refs) <= 1
            or len(snippets_with_refs) <= 2
        )
    ):
        info_panel["answer_origin"] = "evidence_limited_grounded_fallback"
    info_panel["citation_strength_ordering"] = bool(constants["MAIA_CITATION_STRENGTH_ORDERING_ENABLED"])
    info_panel["citation_strength_legend"] = (
        "Citation numbers are normalized per answer: each source appears once and numbering starts at 1."
    )
    record_trace_event(
        "answer.completed",
        {
            "answer_length": len(str(answer or "")),
            "ref_count": len(refs),
            "snippet_count": len(snippets_with_refs),
            "used_general_fallback": bool(used_general_fallback),
            "citation_gate_passed": bool(citation_gate.get("passed", False)) if isinstance(citation_gate, dict) else False,
            "answer_origin": str(info_panel.get("answer_origin") or ""),
        },
    )

    return {
        "answer": answer,
        "chat_answer": answer,
        "snippets_with_refs": snippets_with_refs,
        "refs": refs,
        "info_text": info_text,
        "sources_used": sources_used,
        "source_usage": source_usage,
        "claim_signal_summary": claim_signal_summary,
        "citation_quality_metrics": citation_quality_metrics,
        "info_panel": info_panel,
        "mindmap_payload": mindmap_payload,
        "llm_start_ms": llm_start_ms,
    }
