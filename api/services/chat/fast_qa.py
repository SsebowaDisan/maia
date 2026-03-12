from __future__ import annotations

import logging
from typing import Any
from decouple import config
from ktem.llms.manager import llms
from ktem.pages.chat.common import STATE
from maia.mindmap.indexer import build_knowledge_map
from api.services.mindmap_service import _generate_reasoning_steps_llm as _gen_reasoning_steps
from api.context import ApiContext
from api.schemas import ChatRequest

from .citations import (
    assign_fast_source_refs,
    build_citation_quality_metrics,
    build_claim_signal_summary,
    build_fast_info_html,
    build_source_usage,
    enforce_required_citations,
    normalize_fast_answer,
    render_fast_citation_links,
    resolve_required_citation_mode,
)
from .constants import (
    API_FAST_QA_MAX_IMAGES,
    API_FAST_QA_MAX_SNIPPETS,
    API_FAST_QA_MAX_SOURCES,
    API_FAST_QA_SOURCE_SCAN,
    API_FAST_QA_TEMPERATURE,
    DEFAULT_SETTING,
    MAIA_CITATION_DOMINANCE_WARNING_THRESHOLD,
    MAIA_CITATION_STRENGTH_ORDERING_ENABLED,
    MAIA_SOURCE_USAGE_HEATMAP_ENABLED,
)
from .conversation_store import (
    build_selected_payload,
    get_or_create_conversation,
    maybe_autoname_conversation,
    persist_conversation,
)
from .fast_qa_evidence_helpers import (
    annotate_primary_sources,
    apply_mindmap_focus,
    assess_evidence_sufficiency_with_llm,
    build_no_relevant_evidence_answer,
    finalize_retrieved_snippets,
    normalize_outline,
    plan_adaptive_outline,
    prioritize_primary_evidence,
    selected_source_ids,
    select_relevant_snippets_with_llm,
    snippet_score,
)
from .fast_qa_generation_helpers import call_openai_fast_qa_impl
from .fast_qa_retrieval import load_recent_chunks_for_fast_qa
from .fast_qa_runtime_helpers import (
    call_openai_chat_text as call_openai_chat_text_impl,
    extract_text_content as extract_text_content_impl,
    normalize_request_attachments as normalize_request_attachments_impl,
    parse_json_object as parse_json_object_impl,
    resolve_fast_qa_llm_config as resolve_fast_qa_llm_config_impl,
    truncate_for_log as truncate_for_log_impl,
)
from .fast_qa_turn_helpers import run_fast_chat_turn_impl
from .fast_qa_url_helpers import (
    expand_retrieval_query_for_gap,
    extract_first_url,
    extract_urls,
    extract_urls_from_history,
    host_matches,
    normalize_host,
    normalize_http_url,
    resolve_contextual_url_targets,
    rewrite_followup_question_for_retrieval,
)
from .info_panel_copy import build_info_panel_copy
from .language import build_response_language_rule, resolve_response_language
from .pipeline import is_placeholder_api_key
from .verification_contract import (
    VERIFICATION_CONTRACT_VERSION,
    build_verification_evidence_items,
    build_web_review_content,
)

logger = logging.getLogger(__name__)
_ARTIFACT_URL_PATH_SEGMENTS = {
    "extract",
    "source",
    "link",
    "evidence",
    "citation",
    "title",
    "markdown",
    "content",
    "published",
    "time",
    "url",
}
MAIA_FAST_QA_EVIDENCE_SUFFICIENCY_ENABLED = bool(
    config("MAIA_FAST_QA_EVIDENCE_SUFFICIENCY_ENABLED", default=True, cast=bool)
)
MAIA_FAST_QA_EVIDENCE_SUFFICIENCY_MIN_CONFIDENCE = float(
    config("MAIA_FAST_QA_EVIDENCE_SUFFICIENCY_MIN_CONFIDENCE", default=0.58, cast=float)
)


def _normalize_request_attachments(request: ChatRequest) -> list[dict[str, str]]:
    return normalize_request_attachments_impl(request)


def _extract_text_content(raw_content: Any) -> str:
    return extract_text_content_impl(raw_content)


def _call_openai_chat_text(
    *,
    api_key: str,
    base_url: str,
    request_payload: dict[str, Any],
    timeout_seconds: int = 20,
) -> str | None:
    return call_openai_chat_text_impl(
        api_key=api_key,
        base_url=base_url,
        request_payload=request_payload,
        timeout_seconds=timeout_seconds,
        extract_text_content_fn=_extract_text_content,
    )


def _parse_json_object(raw_text: str) -> dict[str, Any] | None:
    return parse_json_object_impl(raw_text)


def _truncate_for_log(value: Any, limit: int = 1600) -> str:
    return truncate_for_log_impl(value, limit)


def _extract_first_url(text: str) -> str:
    return extract_first_url(text)


def _normalize_http_url(raw_value: Any) -> str:
    return normalize_http_url(raw_value, artifact_url_path_segments=_ARTIFACT_URL_PATH_SEGMENTS)


def _extract_urls(text: str, *, max_urls: int = 6) -> list[str]:
    return extract_urls(
        text,
        max_urls=max_urls,
        normalize_http_url_fn=_normalize_http_url,
    )


def _extract_urls_from_history(
    chat_history: list[list[str]],
    *,
    max_urls: int = 6,
) -> list[str]:
    return extract_urls_from_history(
        chat_history,
        max_urls=max_urls,
        extract_urls_fn=_extract_urls,
    )


def _resolve_contextual_url_targets(
    *,
    question: str,
    chat_history: list[list[str]],
    max_urls: int = 6,
) -> list[str]:
    return resolve_contextual_url_targets(
        question=question,
        chat_history=chat_history,
        max_urls=max_urls,
        extract_urls_fn=_extract_urls,
        extract_urls_from_history_fn=_extract_urls_from_history,
        resolve_fast_qa_llm_config_fn=_resolve_fast_qa_llm_config,
        is_placeholder_api_key_fn=is_placeholder_api_key,
        call_openai_chat_text_fn=_call_openai_chat_text,
        parse_json_object_fn=_parse_json_object,
        normalize_http_url_fn=_normalize_http_url,
        logger=logger,
    )


def _rewrite_followup_question_for_retrieval(
    *,
    question: str,
    chat_history: list[list[str]],
    target_urls: list[str] | None = None,
) -> tuple[str, bool, str]:
    return rewrite_followup_question_for_retrieval(
        question=question,
        chat_history=chat_history,
        target_urls=target_urls,
        normalize_http_url_fn=_normalize_http_url,
        extract_urls_fn=_extract_urls,
        resolve_fast_qa_llm_config_fn=_resolve_fast_qa_llm_config,
        is_placeholder_api_key_fn=is_placeholder_api_key,
        call_openai_chat_text_fn=_call_openai_chat_text,
        parse_json_object_fn=_parse_json_object,
        logger=logger,
    )


def _expand_retrieval_query_for_gap(
    *,
    question: str,
    current_query: str,
    chat_history: list[list[str]],
    snippets: list[dict[str, Any]],
    insufficiency_reason: str,
    target_urls: list[str] | None = None,
) -> tuple[str, str]:
    return expand_retrieval_query_for_gap(
        question=question,
        current_query=current_query,
        chat_history=chat_history,
        snippets=snippets,
        insufficiency_reason=insufficiency_reason,
        target_urls=target_urls,
        normalize_http_url_fn=_normalize_http_url,
        extract_urls_fn=_extract_urls,
        resolve_fast_qa_llm_config_fn=_resolve_fast_qa_llm_config,
        is_placeholder_api_key_fn=is_placeholder_api_key,
        call_openai_chat_text_fn=_call_openai_chat_text,
        parse_json_object_fn=_parse_json_object,
        logger=logger,
    )


def _normalize_host(raw_value: Any) -> str:
    return normalize_host(raw_value, normalize_http_url_fn=_normalize_http_url)


def _host_matches(left_host: str, right_host: str) -> bool:
    return host_matches(left_host, right_host)


def _selected_source_ids(selected_payload: dict[str, list[Any]]) -> set[str]:
    return selected_source_ids(selected_payload)


def _snippet_score(row: dict[str, Any]) -> float:
    return snippet_score(row)


def _annotate_primary_sources(
    *,
    question: str,
    snippets: list[dict[str, Any]],
    selected_payload: dict[str, list[Any]],
    target_urls: list[str] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    return annotate_primary_sources(
        question=question,
        snippets=snippets,
        selected_payload=selected_payload,
        target_urls=target_urls,
        selected_source_ids_fn=_selected_source_ids,
        normalize_http_url_fn=_normalize_http_url,
        extract_urls_fn=_extract_urls,
        normalize_host_fn=_normalize_host,
        host_matches_fn=_host_matches,
        snippet_score_fn=_snippet_score,
    )


def _prioritize_primary_evidence(
    snippets: list[dict[str, Any]],
    *,
    max_keep: int,
    max_secondary: int = 2,
) -> list[dict[str, Any]]:
    return prioritize_primary_evidence(
        snippets,
        max_keep=max_keep,
        max_secondary=max_secondary,
        snippet_score_fn=_snippet_score,
    )


def _build_no_relevant_evidence_answer(
    question: str,
    *,
    target_url: str = "",
    response_language: str | None = None,
) -> str:
    return build_no_relevant_evidence_answer(
        question,
        target_url=target_url,
        response_language=response_language,
        normalize_http_url_fn=_normalize_http_url,
        extract_first_url_fn=_extract_first_url,
    )


def _resolve_fast_qa_llm_config() -> tuple[str, str, str, str]:
    return resolve_fast_qa_llm_config_impl(
        config_fn=config,
        is_placeholder_api_key_fn=is_placeholder_api_key,
        llms_manager=llms,
    )


def _normalize_outline(raw_outline: dict[str, Any] | None) -> dict[str, Any]:
    return normalize_outline(raw_outline)


def _apply_mindmap_focus(
    snippets: list[dict[str, Any]],
    focus: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    return apply_mindmap_focus(snippets, focus)


def _select_relevant_snippets_with_llm(
    *,
    question: str,
    chat_history: list[list[str]],
    snippets: list[dict[str, Any]],
    max_keep: int,
) -> list[dict[str, Any]]:
    return select_relevant_snippets_with_llm(
        question=question,
        chat_history=chat_history,
        snippets=snippets,
        max_keep=max_keep,
        resolve_fast_qa_llm_config_fn=_resolve_fast_qa_llm_config,
        is_placeholder_api_key_fn=is_placeholder_api_key,
        call_openai_chat_text_fn=_call_openai_chat_text,
        parse_json_object_fn=_parse_json_object,
        logger=logger,
    )


def _assess_evidence_sufficiency_with_llm(
    *,
    question: str,
    chat_history: list[list[str]],
    snippets: list[dict[str, Any]],
    primary_source_note: str = "",
    require_primary_source: bool = False,
) -> tuple[bool, float, str]:
    return assess_evidence_sufficiency_with_llm(
        question=question,
        chat_history=chat_history,
        snippets=snippets,
        primary_source_note=primary_source_note,
        require_primary_source=require_primary_source,
        sufficiency_enabled=MAIA_FAST_QA_EVIDENCE_SUFFICIENCY_ENABLED,
        sufficiency_min_confidence=MAIA_FAST_QA_EVIDENCE_SUFFICIENCY_MIN_CONFIDENCE,
        resolve_fast_qa_llm_config_fn=_resolve_fast_qa_llm_config,
        is_placeholder_api_key_fn=is_placeholder_api_key,
        call_openai_chat_text_fn=_call_openai_chat_text,
        parse_json_object_fn=_parse_json_object,
        logger=logger,
    )


def _finalize_retrieved_snippets(
    *,
    question: str,
    chat_history: list[list[str]],
    retrieved_snippets: list[dict[str, Any]],
    selected_payload: dict[str, list[Any]],
    target_urls: list[str],
    mindmap_focus: dict[str, Any] | None,
    max_keep: int,
) -> tuple[list[dict[str, Any]], str, str]:
    return finalize_retrieved_snippets(
        question=question,
        chat_history=chat_history,
        retrieved_snippets=retrieved_snippets,
        selected_payload=selected_payload,
        target_urls=target_urls,
        mindmap_focus=mindmap_focus,
        max_keep=max_keep,
        annotate_primary_sources_fn=_annotate_primary_sources,
        apply_mindmap_focus_fn=_apply_mindmap_focus,
        snippet_score_fn=_snippet_score,
        select_relevant_snippets_with_llm_fn=_select_relevant_snippets_with_llm,
        prioritize_primary_evidence_fn=_prioritize_primary_evidence,
    )


def _plan_adaptive_outline(
    *,
    api_key: str,
    base_url: str,
    model: str,
    temperature: float,
    question: str,
    history_text: str,
    refs_text: str,
    context_text: str,
) -> dict[str, Any]:
    return plan_adaptive_outline(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=temperature,
        question=question,
        history_text=history_text,
        refs_text=refs_text,
        context_text=context_text,
        truncate_for_log_fn=_truncate_for_log,
        call_openai_chat_text_fn=_call_openai_chat_text,
        parse_json_object_fn=_parse_json_object,
        normalize_outline_fn=_normalize_outline,
        logger=logger,
    )


def call_openai_fast_qa(
    question: str,
    snippets: list[dict[str, Any]],
    chat_history: list[list[str]],
    refs: list[dict[str, Any]],
    citation_mode: str | None,
    primary_source_note: str = "",
    requested_language: str | None = None,
    allow_general_knowledge: bool = False,
    is_follow_up: bool = False,
    all_project_sources: list[str] | None = None,
) -> str | None:
    return call_openai_fast_qa_impl(
        question=question,
        snippets=snippets,
        chat_history=chat_history,
        refs=refs,
        citation_mode=citation_mode,
        primary_source_note=primary_source_note,
        requested_language=requested_language,
        allow_general_knowledge=allow_general_knowledge,
        is_follow_up=is_follow_up,
        all_project_sources=all_project_sources,
        logger=logger,
        resolve_fast_qa_llm_config_fn=_resolve_fast_qa_llm_config,
        truncate_for_log_fn=_truncate_for_log,
        is_placeholder_api_key_fn=is_placeholder_api_key,
        resolve_required_citation_mode_fn=resolve_required_citation_mode,
        build_response_language_rule_fn=build_response_language_rule,
        plan_adaptive_outline_fn=_plan_adaptive_outline,
        call_openai_chat_text_fn=_call_openai_chat_text,
        API_FAST_QA_MAX_SNIPPETS=API_FAST_QA_MAX_SNIPPETS,
        API_FAST_QA_MAX_IMAGES=API_FAST_QA_MAX_IMAGES,
        API_FAST_QA_TEMPERATURE=API_FAST_QA_TEMPERATURE,
    )


def _build_knowledge_map_with_llm_steps(
    *,
    question: str,
    context: str,
    documents=None,
    answer_text: str = "",
    max_depth: int = 4,
    include_reasoning_map: bool = True,
    source_type_hint: str = "",
    focus=None,
    node_limit=None,
    map_type: str = "structure",
    reasoning_steps=None,
    **kwargs,
) -> dict[str, Any]:
    """build_knowledge_map wrapper that pre-generates reasoning steps via LLM."""
    if include_reasoning_map and answer_text.strip() and reasoning_steps is None:
        try:
            reasoning_steps = _gen_reasoning_steps(answer_text, question) or None
        except Exception:
            reasoning_steps = None
    kw: dict[str, Any] = dict(
        question=question,
        context=context,
        documents=documents,
        answer_text=answer_text,
        max_depth=max_depth,
        include_reasoning_map=include_reasoning_map,
        source_type_hint=source_type_hint,
        focus=focus,
        map_type=map_type,
        reasoning_steps=reasoning_steps,
    )
    if node_limit is not None:
        kw["node_limit"] = node_limit
    return build_knowledge_map(**kw)


def run_fast_chat_turn(
    context: ApiContext,
    user_id: str,
    request: ChatRequest,
) -> dict[str, Any] | None:
    return run_fast_chat_turn_impl(
        context=context,
        user_id=user_id,
        request=request,
        logger=logger,
        default_setting=DEFAULT_SETTING,
        get_or_create_conversation_fn=get_or_create_conversation,
        maybe_autoname_conversation_fn=maybe_autoname_conversation,
        resolve_response_language_fn=resolve_response_language,
        build_selected_payload_fn=build_selected_payload,
        resolve_contextual_url_targets_fn=_resolve_contextual_url_targets,
        rewrite_followup_question_for_retrieval_fn=_rewrite_followup_question_for_retrieval,
        load_recent_chunks_for_fast_qa_fn=load_recent_chunks_for_fast_qa,
        finalize_retrieved_snippets_fn=_finalize_retrieved_snippets,
        assess_evidence_sufficiency_with_llm_fn=_assess_evidence_sufficiency_with_llm,
        expand_retrieval_query_for_gap_fn=_expand_retrieval_query_for_gap,
        call_openai_fast_qa_fn=call_openai_fast_qa,
        normalize_fast_answer_fn=normalize_fast_answer,
        build_no_relevant_evidence_answer_fn=_build_no_relevant_evidence_answer,
        resolve_required_citation_mode_fn=resolve_required_citation_mode,
        render_fast_citation_links_fn=render_fast_citation_links,
        build_fast_info_html_fn=build_fast_info_html,
        enforce_required_citations_fn=enforce_required_citations,
        build_source_usage_fn=build_source_usage,
        build_claim_signal_summary_fn=build_claim_signal_summary,
        build_citation_quality_metrics_fn=build_citation_quality_metrics,
        build_info_panel_copy_fn=build_info_panel_copy,
        build_knowledge_map_fn=_build_knowledge_map_with_llm_steps,
        build_verification_evidence_items_fn=build_verification_evidence_items,
        build_web_review_content_fn=build_web_review_content,
        persist_conversation_fn=persist_conversation,
        normalize_request_attachments_fn=_normalize_request_attachments,
        constants={
            "STATE": STATE,
            "truncate_for_log_fn": _truncate_for_log,
            "API_FAST_QA_SOURCE_SCAN": API_FAST_QA_SOURCE_SCAN,
            "API_FAST_QA_MAX_SOURCES": API_FAST_QA_MAX_SOURCES,
            "API_FAST_QA_MAX_SNIPPETS": API_FAST_QA_MAX_SNIPPETS,
            "assign_fast_source_refs_fn": assign_fast_source_refs,
            "MAIA_SOURCE_USAGE_HEATMAP_ENABLED": MAIA_SOURCE_USAGE_HEATMAP_ENABLED,
            "MAIA_CITATION_DOMINANCE_WARNING_THRESHOLD": MAIA_CITATION_DOMINANCE_WARNING_THRESHOLD,
            "VERIFICATION_CONTRACT_VERSION": VERIFICATION_CONTRACT_VERSION,
            "MAIA_CITATION_STRENGTH_ORDERING_ENABLED": MAIA_CITATION_STRENGTH_ORDERING_ENABLED,
        },
    )
