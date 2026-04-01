from __future__ import annotations

import os
import queue
import logging
import threading
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
from .canvas_turn import attach_canvas_document
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
    infer_openai_compatible_provider as infer_openai_compatible_provider_impl,
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
from .streaming import chunk_text_for_stream, make_activity_stream_event

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

# New RAG pipeline (feature flag)
_USE_NEW_RAG = config("MAIA_USE_NEW_RAG", default="true", cast=str).lower() == "true"


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


def _infer_openai_compatible_provider(*, base_url: str, model: str) -> str:
    return infer_openai_compatible_provider_impl(base_url=base_url, model=model)


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
        infer_provider_label_fn=_infer_openai_compatible_provider,
        API_FAST_QA_MAX_SNIPPETS=API_FAST_QA_MAX_SNIPPETS,
        API_FAST_QA_MAX_IMAGES=API_FAST_QA_MAX_IMAGES,
        API_FAST_QA_TEMPERATURE=API_FAST_QA_TEMPERATURE,
    )


def _build_analysis_and_gaps(
    question: str, answer: str, api_key: str, base_url: str, model: str,
) -> dict[str, Any]:
    """Ask the LLM to generate analysis, gaps, and next steps from the answer."""
    try:
        import httpx as _httpx
        import json as _json

        resp = _httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You analyse an AI assistant's answer and return JSON with three fields:\n"
                            "1. \"analysis\": a list of 3-5 key topics covered in the answer, each as {\"topic\": \"...\", \"covered\": true/false, \"depth\": \"shallow|moderate|deep\"}\n"
                            "2. \"gaps\": a list of 2-4 important aspects that were NOT covered or need more depth, each as {\"topic\": \"...\", \"reason\": \"why it matters\"}\n"
                            "3. \"next_steps\": a list of 2-3 follow-up questions the user might want to ask next\n\n"
                            "Return ONLY valid JSON. No markdown, no explanation."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Question: {question}\n\nAnswer:\n{answer[:3000]}",
                    },
                ],
                "temperature": 0.3,
            },
            timeout=30.0,
        )
        if resp.status_code == 200:
            text = resp.json()["choices"][0]["message"]["content"]
            # Parse JSON from response
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
            return _json.loads(text)
    except Exception as exc:
        logger.debug("Analysis/gaps generation failed (non-fatal): %s", exc)
    return {}


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
    # Determine if RAG mode should be used
    _has_attachments = hasattr(request, "attachments") and request.attachments and any(
        getattr(att, "file_id", None) or (att.get("file_id") if isinstance(att, dict) else None)
        for att in request.attachments
    )
    _has_selected_files = hasattr(request, "index_selection") and request.index_selection and any(
        (hasattr(sel, "file_ids") and sel.file_ids) or (isinstance(sel, dict) and sel.get("file_ids"))
        for sel in request.index_selection.values()
    )
    _rag_mode_selected = str(getattr(request, "agent_mode", "") or "").strip().lower() == "rag"
    _use_rag_for_this_request = _USE_NEW_RAG and (_has_attachments or _has_selected_files or _rag_mode_selected)

    # ── Standard mode (no files, not Library mode): direct LLM, no citations ───
    if not _use_rag_for_this_request:
        try:
            import httpx
            from dotenv import load_dotenv
            load_dotenv()  # Ensure .env is loaded

            api_key = os.environ.get("MAIA_LLM_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
            base_url = os.environ.get("MAIA_LLM_API_BASE", "") or os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
            model = os.environ.get("MAIA_LLM_CHAT_MODEL", "") or os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini")
            logger.info("Standard LLM call: key=%s... base=%s model=%s", api_key[:10] if api_key else "NONE", base_url, model)

            if api_key:
                resp = httpx.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "You are Maia, an intelligent assistant.\n\n"

                                    "Rules:\n"
                                    "1. Start every response with a # title in sentence case — the FIRST letter MUST be uppercase. Capitalise the first word and proper nouns only (e.g. '# Machine learning is a data-driven approach to AI', NOT '# machine learning is a data-driven approach to AI').\n"
                                    "2. Give the direct answer first. No greeting, no preamble.\n"
                                    "3. Explain in depth. Write full paragraphs, not just bullet points. "
                                    "Each section should have 2-4 sentences of explanation before or after any list.\n"
                                    "4. Explain WHY things work, not just WHAT they are. Help the reader understand the reasoning.\n"
                                    "5. Use real-world examples with specific details — names, numbers, scenarios that feel concrete.\n"
                                    "6. When comparing things, state which is better and why with reasoning.\n"
                                    "7. Point out common mistakes and misconceptions the user should know about.\n"
                                    "8. End with a key insight that changes how they think about the topic.\n\n"

                                    "Format:\n"
                                    "- Use ## headings in sentence case (first letter UPPERCASE, e.g. '## How it learns from data' not '## how it learns from data').\n"
                                    "- Write explanatory paragraphs between headings — do not rely solely on lists.\n"
                                    "- Use **bold** for key terms and the most important point in each section.\n"
                                    "- Use tables when comparing 2+ items side by side.\n"
                                    "- Use numbered lists for sequential steps. Use bullet lists for non-sequential items.\n"
                                    "- For numbered lists, always put the number and content on the SAME line: '1. **Title** — explanation text here' not '1.\\n\\nTitle\\n\\ntext'.\n"
                                    "- Use ```code blocks``` for code, commands, or technical syntax.\n"
                                    "- Always provide context and explanation around lists and tables, not just the list alone.\n\n"

                                    "Never:\n"
                                    "- Never say 'Great question!' or 'Sure!' or 'Of course!'\n"
                                    "- Never repeat the question back.\n"
                                    "- Never give a response that is just bullet points without explanatory text.\n"
                                    "- Never use 'In conclusion' or 'To summarize' — just end when done.\n"
                                    "- Never use citation markers like [1], [2], [3]. You are answering from your own knowledge, not from sources."
                                ),
                            },
                            {"role": "user", "content": request.message},
                        ],
                        "temperature": 0.7,
                    },
                    timeout=120.0,
                )
                logger.info("Standard LLM response: status=%d", resp.status_code)
                if resp.status_code != 200:
                    logger.error("Standard LLM error: %s", resp.text[:300])
                if resp.status_code == 200:
                    answer = resp.json()["choices"][0]["message"]["content"]
                    conv_id = getattr(request, "conversation_id", "") or ""

                    # Persist conversation to database so it survives refresh
                    try:
                        _conv_id, conv_name, _data_source, _icon = get_or_create_conversation(
                            user_id=user_id,
                            conversation_id=conv_id,
                        )
                        conv_id = _conv_id
                        maybe_autoname_conversation(
                            user_id=user_id,
                            conversation_id=conv_id,
                            current_name=conv_name,
                            message=request.message,
                            agent_mode=getattr(request, "agent_mode", "ask") or "ask",
                        )
                        messages = _data_source.get("messages", []) if isinstance(_data_source, dict) else []
                        messages.append([request.message, answer])
                        retrieval_messages = _data_source.get("retrieval_messages", []) if isinstance(_data_source, dict) else []
                        retrieval_messages.append("")
                        plot_history = _data_source.get("plot_history", []) if isinstance(_data_source, dict) else []
                        plot_history.append(None)
                        message_meta = _data_source.get("message_meta", []) if isinstance(_data_source, dict) else []
                        # message_meta entry added after blocks are built (below)
                    except Exception as persist_exc:
                        logger.warning("Conversation persist failed (non-fatal): %s", persist_exc)
                        messages = []
                        retrieval_messages = []
                        plot_history = []
                        message_meta = []

                    # Build mind map from the answer
                    mindmap_data = {}
                    try:
                        mindmap_data = _build_knowledge_map_with_llm_steps(
                            question=request.message,
                            context=answer,
                            answer_text=answer,
                            max_depth=4,
                            include_reasoning_map=True,
                            map_type="structure",
                        )
                    except Exception as map_exc:
                        logger.debug("Mind map generation failed (non-fatal): %s", map_exc)

                    # Build analysis and gaps via LLM
                    analysis_and_gaps = _build_analysis_and_gaps(
                        request.message, answer, api_key, base_url, model,
                    )

                    info_panel: dict[str, Any] = {}
                    if mindmap_data:
                        info_panel["mindmap"] = mindmap_data
                    if analysis_and_gaps.get("analysis"):
                        info_panel["analysis"] = analysis_and_gaps["analysis"]
                    if analysis_and_gaps.get("gaps"):
                        info_panel["gaps"] = analysis_and_gaps["gaps"]

                    blocks, documents, canvas_payload = attach_canvas_document(
                        user_id=user_id,
                        question=request.message,
                        answer_text=answer,
                        info_html="",
                        info_panel=info_panel,
                        mode_variant="ask",
                        blocks=[{"type": "markdown", "markdown": answer}],
                        documents=[],
                    )
                    if canvas_payload:
                        info_panel["canvas_document_id"] = str(canvas_payload.get("id") or "")
                        info_panel["canvas_title"] = str(canvas_payload.get("title") or "")

                    # Persist with correct format for frontend reload
                    try:
                        turn_attachments = normalize_request_attachments_impl(request)
                        message_meta.append({
                            "mode": "ask",
                            "actions_taken": [],
                            "sources_used": [],
                            "source_usage": [],
                            "attachments": turn_attachments,
                            "next_recommended_steps": analysis_and_gaps.get("next_steps", []),
                            "info_panel": info_panel,
                            "mindmap": mindmap_data,
                            "blocks": blocks,
                            "documents": documents,
                        })
                        persist_conversation(conv_id, {
                            "messages": messages,
                            "retrieval_messages": retrieval_messages,
                            "plot_history": plot_history,
                            "message_meta": message_meta,
                        })
                    except Exception as meta_exc:
                        logger.warning("Message meta persist failed (non-fatal): %s", meta_exc)

                    return {
                        "conversation_id": conv_id,
                        "conversation_name": "",
                        "message": request.message,
                        "answer": answer,
                        "info": "",
                        "blocks": blocks,
                        "documents": documents,
                        "plot": None,
                        "state": {"mindmap": mindmap_data} if mindmap_data else {},
                        "mode": "ask",
                        "actions_taken": [],
                        "sources_used": [],
                        "source_usage": [],
                        "next_recommended_steps": analysis_and_gaps.get("next_steps", []),
                        "needs_human_review": False,
                        "info_panel": info_panel,
                        "infoPanel": info_panel,
                    }
        except Exception as exc:
            logger.warning("Direct LLM call failed: %s", exc, exc_info=True)
        # Fall through to old pipeline

    if _use_rag_for_this_request:
        import asyncio
        from api.services.rag.bridge import run_rag_query_bridge

        # Extract source IDs from request
        selected_ids = []
        group_id = ""
        try:
            # 1. From index_selection (selected files via @ picker)
            if hasattr(request, "index_selection") and request.index_selection:
                for _idx_key, sel in request.index_selection.items():
                    if hasattr(sel, "file_ids") and sel.file_ids:
                        selected_ids.extend([str(f) for f in sel.file_ids])
                    elif isinstance(sel, dict) and sel.get("file_ids"):
                        selected_ids.extend([str(f) for f in sel["file_ids"]])

            # 2. From attachments (chat-uploaded PDFs) — add to selected_ids
            if hasattr(request, "attachments") and request.attachments:
                for att in request.attachments:
                    fid = getattr(att, "file_id", None) or (att.get("file_id") if isinstance(att, dict) else None)
                    if fid and str(fid) not in selected_ids:
                        selected_ids.append(str(fid))
        except Exception:
            pass

        # In Library mode: ALWAYS search ALL library files (not just attached ones).
        # The attached file is included too, but we search the whole library.
        # Pass empty source_ids so the bridge queries all user documents.
        # Only scope to specific files if user explicitly selected via @ or #.
        query_source_ids = selected_ids if (selected_ids and not _rag_mode_selected) else []
        if _rag_mode_selected and selected_ids:
            # Library mode + files attached/selected: search all, but the attached
            # files are already in the index so they'll be found naturally.
            # Pass empty to search everything.
            query_source_ids = []

        try:
            # Handle both sync and async contexts
            try:
                loop = asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(
                        asyncio.run,
                        run_rag_query_bridge(
                            question=request.message,
                            source_ids=query_source_ids,
                            group_id=group_id,
                            owner_id=user_id,
                        )
                    ).result(timeout=60)
            except RuntimeError:
                result = asyncio.run(
                    run_rag_query_bridge(
                        question=request.message,
                        source_ids=query_source_ids,
                        group_id=group_id,
                        owner_id=user_id,
                    )
                )

            if result and result.get("answer_text"):
                conv_id = getattr(request, "conversation_id", "") or ""

                # Persist conversation to database
                try:
                    _conv_id, conv_name, _data_source, _icon = get_or_create_conversation(
                        user_id=user_id,
                        conversation_id=conv_id,
                    )
                    conv_id = _conv_id
                    maybe_autoname_conversation(
                        user_id=user_id,
                        conversation_id=conv_id,
                        current_name=conv_name,
                        message=request.message,
                        agent_mode=getattr(request, "agent_mode", "ask") or "ask",
                    )
                    messages = _data_source.get("messages", []) if isinstance(_data_source, dict) else []
                    retrieval_messages = _data_source.get("retrieval_messages", []) if isinstance(_data_source, dict) else []
                    plot_history = _data_source.get("plot_history", []) if isinstance(_data_source, dict) else []
                    message_meta = _data_source.get("message_meta", []) if isinstance(_data_source, dict) else []
                except Exception as persist_exc:
                    logger.warning("RAG conversation persist failed (non-fatal): %s", persist_exc)
                    messages = []
                    retrieval_messages = []
                    plot_history = []
                    message_meta = []

                # Use citation-rich HTML answer (with <a class="citation"> tags)
                answer_html = result.get("answer_html", result["answer_text"])

                # Build infoPanel for the evidence right panel
                info_panel = result.get("info_panel", {})
                blocks, documents, canvas_payload = attach_canvas_document(
                    user_id=user_id,
                    question=request.message,
                    answer_text=answer_html,
                    info_html=str(result.get("info_html", "") or ""),
                    info_panel=info_panel if isinstance(info_panel, dict) else {},
                    mode_variant="rag",
                    blocks=[{"type": "markdown", "markdown": answer_html}],
                    documents=[],
                )
                if canvas_payload and isinstance(info_panel, dict):
                    info_panel["canvas_document_id"] = str(canvas_payload.get("id") or "")
                    info_panel["canvas_title"] = str(canvas_payload.get("title") or "")

                # Persist with correct format for frontend reload
                try:
                    turn_attachments = normalize_request_attachments_impl(request)
                    messages.append([request.message, answer_html])
                    retrieval_messages.append(result.get("info_html", ""))
                    plot_history.append(None)
                    rag_sources_used = [
                        {
                            "source_type": s.get("source_type", "file"),
                            "label": s.get("source_name", "") or s.get("label", "source"),
                            "source_id": s.get("source_id", ""),
                            "source_name": s.get("source_name", ""),
                            "score": s.get("relevance_score", 0),
                        }
                        for s in result.get("sources_used", [])
                    ]
                    message_meta.append({
                        "mode": "ask",
                        "actions_taken": [],
                        "sources_used": rag_sources_used,
                        "source_usage": [],
                        "attachments": turn_attachments,
                        "next_recommended_steps": [],
                        "info_panel": info_panel,
                        "mindmap": {},
                        "blocks": blocks,
                        "documents": documents,
                    })
                    persist_conversation(conv_id, {
                        "messages": messages,
                        "retrieval_messages": retrieval_messages,
                        "plot_history": plot_history,
                        "message_meta": message_meta,
                    })
                except Exception as meta_exc:
                    logger.warning("RAG message meta persist failed (non-fatal): %s", meta_exc)

                return {
                    "conversation_id": conv_id,
                    "conversation_name": "",
                    "message": request.message,
                    "answer": answer_html,
                    "info": result.get("info_html", ""),
                    "info_panel": info_panel,
                    "infoPanel": info_panel,
                    "blocks": blocks,
                    "documents": documents,
                    "plot": None,
                    "state": {},
                    "mode": "ask",
                    "actions_taken": [],
                    "sources_used": [
                        {
                            "source_type": s.get("source_type", "file"),
                            "label": s.get("source_name", "") or s.get("label", "source"),
                            "source_id": s.get("source_id", ""),
                            "source_name": s.get("source_name", ""),
                            "score": s.get("relevance_score", 0),
                            "relevance": s.get("relevance_score", 0),
                        }
                        for s in result.get("sources_used", [])
                    ],
                    "source_usage": [],
                    "next_recommended_steps": [],
                    "needs_human_review": False,
                }
        except Exception as exc:
            logger.warning("New RAG pipeline failed, falling back to old: %s", exc, exc_info=True)
        # Fall through to old pipeline

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


def stream_fast_chat_turn(
    context: ApiContext,
    user_id: str,
    request: ChatRequest,
):
    event_queue: queue.Queue[Any] = queue.Queue()
    result_holder: dict[str, Any] = {}
    error_holder: dict[str, BaseException] = {}
    sentinel = object()

    def emit_stream_event(payload: dict[str, Any]) -> None:
        event_queue.put(payload)

    def worker() -> None:
        try:
            result_holder["value"] = run_fast_chat_turn_impl(
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
                emit_stream_event_fn=emit_stream_event,
                make_activity_event_fn=make_activity_stream_event,
                chunk_text_for_stream_fn=chunk_text_for_stream,
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
        except BaseException as exc:  # pragma: no cover - surfaced to stream caller
            error_holder["error"] = exc
        finally:
            event_queue.put(sentinel)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    while True:
        item = event_queue.get()
        if item is sentinel:
            break
        yield item

    if "error" in error_holder:
        raise error_holder["error"]
    return result_holder.get("value") or {}
