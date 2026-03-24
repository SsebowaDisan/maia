from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from copy import deepcopy
from typing import Any, Generator

from theflow.settings import settings as flowsettings

from ktem.pages.chat.common import STATE
from ktem.utils.commands import WEB_SEARCH_COMMAND

from api.context import ApiContext
from api.services.chat.block_builder import build_turn_blocks
from api.schemas import ChatRequest, HaltReason
from api.services.agent.llm_runtime import call_json_response, env_bool
from api.services.settings_service import load_user_settings
from api.services.upload_service import index_urls

from . import app_index_helpers as _index_helpers
from . import app_prompt_helpers as _prompt_helpers
from .app_auto_index_helpers import auto_index_urls_for_request as _auto_index_urls_for_request_impl
from .app_deep_search_helpers import apply_deep_search_defaults as _apply_deep_search_defaults_impl
from .app_route_helpers import should_auto_web_fallback as _should_auto_web_fallback_impl
from .app_stream_helpers import stream_chat_turn as _stream_chat_turn_impl
from .app_timeout_helpers import resolve_chat_timeout_seconds as _resolve_chat_timeout_seconds_impl
from .constants import API_CHAT_FAST_PATH, DEFAULT_SETTING, logger
from .conversation_store import get_or_create_conversation, maybe_autoname_conversation, persist_conversation
from .fallbacks import build_extractive_timeout_answer
from .fast_qa import run_fast_chat_turn
from .info_panel_copy import build_info_panel_copy
from .citations import enforce_required_citations, normalize_info_evidence_html
from .verification_contract import VERIFICATION_CONTRACT_VERSION

# Re-exported constants for backward compatibility and tests.
_HTTP_URL_RE = _index_helpers._HTTP_URL_RE
_AUTO_URL_INDEX_MARKER = _index_helpers._AUTO_URL_INDEX_MARKER
_AUTO_URL_CACHE_LOCK = _index_helpers._AUTO_URL_CACHE_LOCK
_AUTO_URL_INDEX_CACHE = _index_helpers._AUTO_URL_INDEX_CACHE
_DEEP_SEARCH_MODE = _prompt_helpers._DEEP_SEARCH_MODE
_ORCHESTRATOR_MODES = _prompt_helpers._ORCHESTRATOR_MODES
_DEEP_SEARCH_DEFAULT_WEB_SEARCH_BUDGET = _prompt_helpers._DEEP_SEARCH_DEFAULT_WEB_SEARCH_BUDGET
_DEEP_SEARCH_DEFAULT_SOURCE_LIMIT = _prompt_helpers._DEEP_SEARCH_DEFAULT_SOURCE_LIMIT
_DEEP_SEARCH_NORMAL_WEB_BUDGET = _prompt_helpers._DEEP_SEARCH_NORMAL_WEB_BUDGET
_DEEP_SEARCH_COMPLEX_WEB_BUDGET = _prompt_helpers._DEEP_SEARCH_COMPLEX_WEB_BUDGET
_DEEP_SEARCH_NORMAL_MAX_QUERY_VARIANTS = _prompt_helpers._DEEP_SEARCH_NORMAL_MAX_QUERY_VARIANTS
_DEEP_SEARCH_COMPLEX_MAX_QUERY_VARIANTS = _prompt_helpers._DEEP_SEARCH_COMPLEX_MAX_QUERY_VARIANTS
_DEEP_SEARCH_NORMAL_RESULTS_PER_QUERY = _prompt_helpers._DEEP_SEARCH_NORMAL_RESULTS_PER_QUERY
_DEEP_SEARCH_COMPLEX_RESULTS_PER_QUERY = _prompt_helpers._DEEP_SEARCH_COMPLEX_RESULTS_PER_QUERY
_DEEP_SEARCH_NORMAL_MIN_UNIQUE_SOURCES = _prompt_helpers._DEEP_SEARCH_NORMAL_MIN_UNIQUE_SOURCES
_DEEP_SEARCH_COMPLEX_MIN_UNIQUE_SOURCES = _prompt_helpers._DEEP_SEARCH_COMPLEX_MIN_UNIQUE_SOURCES
_DEEP_SEARCH_COMPLEXITY_VALUES = _prompt_helpers._DEEP_SEARCH_COMPLEXITY_VALUES

# Re-exported helpers for compatibility and tests.
_default_model_looks_local_ollama = _prompt_helpers._default_model_looks_local_ollama
_float_or_default = _prompt_helpers._float_or_default
_int_or_default = _prompt_helpers._int_or_default
_is_orchestrator_mode = _prompt_helpers._is_orchestrator_mode
_truthy_flag = _prompt_helpers._truthy_flag
_normalize_scope_phrase = _prompt_helpers._normalize_scope_phrase
_prompt_mentions_phrase = _prompt_helpers._prompt_mentions_phrase
_source_row_looks_pdf = _prompt_helpers._source_row_looks_pdf
_list_index_pdf_source_ids = _prompt_helpers._list_index_pdf_source_ids
_list_named_group_file_ids = _prompt_helpers._list_named_group_file_ids
_mentioned_index_ids_in_prompt = _prompt_helpers._mentioned_index_ids_in_prompt
_resolve_prompt_scoped_pdf_ids = _prompt_helpers._resolve_prompt_scoped_pdf_ids
_classify_deep_search_complexity = _prompt_helpers._classify_deep_search_complexity
_mode_variant_from_request = _prompt_helpers._mode_variant_from_request

_normalize_http_url = _index_helpers._normalize_http_url
_normalize_request_attachments = _index_helpers._normalize_request_attachments
_request_with_command = _index_helpers._request_with_command
_request_with_updates = _index_helpers._request_with_updates
_extract_message_urls = _index_helpers._extract_message_urls
_first_available_index_id = _index_helpers._first_available_index_id
_pick_target_index_id = _index_helpers._pick_target_index_id
_merge_request_index_selection = _index_helpers._merge_request_index_selection
_errors_indicate_already_indexed = _index_helpers._errors_indicate_already_indexed
_resolve_existing_url_source_ids = _index_helpers._resolve_existing_url_source_ids
_source_ids_have_document_relations = _index_helpers._source_ids_have_document_relations
_override_request_index_selection = _index_helpers._override_request_index_selection
_apply_url_grounded_index_selection = _index_helpers._apply_url_grounded_index_selection
_auto_url_cache_key = _index_helpers._auto_url_cache_key
_auto_url_cache_get = _index_helpers._auto_url_cache_get
_auto_url_cache_put = _index_helpers._auto_url_cache_put
_normalized_request_selection = _index_helpers._normalized_request_selection
_selected_index_ids_for_deep_search = _index_helpers._selected_index_ids_for_deep_search
_list_index_source_ids = _index_helpers._list_index_source_ids


def _should_auto_web_fallback(
    *,
    message: str,
    chat_history: list[list[str]],
    disable_auto_web_fallback: bool = False,
) -> bool:
    return _should_auto_web_fallback_impl(
        message=message,
        chat_history=chat_history,
        disable_auto_web_fallback=disable_auto_web_fallback,
        call_json_response_fn=call_json_response,
        env_bool_fn=env_bool,
    )


def _apply_deep_search_defaults(
    *,
    context: ApiContext,
    user_id: str,
    request: ChatRequest,
) -> ChatRequest:
    return _apply_deep_search_defaults_impl(
        context=context,
        user_id=user_id,
        request=request,
        int_or_default_fn=_int_or_default,
        classify_deep_search_complexity_fn=_classify_deep_search_complexity,
        normalized_request_selection_fn=_normalized_request_selection,
        resolve_prompt_scoped_pdf_ids_fn=_resolve_prompt_scoped_pdf_ids,
        selected_index_ids_for_deep_search_fn=_selected_index_ids_for_deep_search,
        list_index_source_ids_fn=_list_index_source_ids,
        request_with_updates_fn=_request_with_updates,
    )


def _auto_index_urls_for_request(
    *,
    context: ApiContext,
    user_id: str,
    request: ChatRequest,
    settings: dict[str, Any] | None,
) -> ChatRequest:
    return _auto_index_urls_for_request_impl(
        context=context,
        user_id=user_id,
        request=request,
        settings=settings,
        _extract_message_urls=_extract_message_urls,
        load_user_settings=load_user_settings,
        _auto_url_cache_key=_auto_url_cache_key,
        _auto_url_cache_get=_auto_url_cache_get,
        _auto_url_cache_put=_auto_url_cache_put,
        _normalized_request_selection=_normalized_request_selection,
        _pick_target_index_id=_pick_target_index_id,
        _merge_request_index_selection=_merge_request_index_selection,
        _errors_indicate_already_indexed=_errors_indicate_already_indexed,
        index_urls=index_urls,
        _resolve_existing_url_source_ids=_resolve_existing_url_source_ids,
        _apply_url_grounded_index_selection=_apply_url_grounded_index_selection,
        _source_ids_have_document_relations=_source_ids_have_document_relations,
        _request_with_updates=_request_with_updates,
        _override_request_index_selection=_override_request_index_selection,
        _AUTO_URL_INDEX_MARKER=_AUTO_URL_INDEX_MARKER,
        env_bool_fn=env_bool,
        web_search_command=WEB_SEARCH_COMMAND,
        int_or_default_fn=_int_or_default,
        flowsettings_obj=flowsettings,
    )


def stream_chat_turn(
    context: ApiContext,
    user_id: str,
    request: ChatRequest,
) -> Generator[dict[str, Any], None, dict[str, Any]]:
    return _stream_chat_turn_impl(
        context=context,
        user_id=user_id,
        request=request,
        auto_index_urls_for_request_fn=_auto_index_urls_for_request,
        apply_deep_search_defaults_fn=_apply_deep_search_defaults,
        normalize_request_attachments_fn=_normalize_request_attachments,
        mode_variant_from_request_fn=_mode_variant_from_request,
        is_orchestrator_mode_fn=_is_orchestrator_mode,
    )


def _resolve_chat_timeout_seconds(*, requested_mode: str) -> int:
    return _resolve_chat_timeout_seconds_impl(
        requested_mode=requested_mode,
        flowsettings_obj=flowsettings,
        default_model_looks_local_ollama_fn=_default_model_looks_local_ollama,
        deep_search_mode=_DEEP_SEARCH_MODE,
    )


def run_chat_turn(context: ApiContext, user_id: str, request: ChatRequest) -> dict[str, Any]:
    request = _auto_index_urls_for_request(
        context=context,
        user_id=user_id,
        request=request,
        settings=None,
    )
    requested_mode = str(request.agent_mode or "").strip().lower() or "ask"
    if API_CHAT_FAST_PATH and not _is_orchestrator_mode(requested_mode):
        try:
            fast_result = run_fast_chat_turn(context=context, user_id=user_id, request=request)
            if fast_result is not None:
                logger.warning("chat_path_selected path=fast_qa")
                return fast_result
            if request.command in (None, "", DEFAULT_SETTING):
                try:
                    _conversation_id, _conversation_name, data_source, _conversation_icon_key = get_or_create_conversation(
                        user_id=user_id,
                        conversation_id=request.conversation_id,
                    )
                    chat_history = deepcopy(data_source.get("messages", []))
                except Exception:
                    chat_history = []
                request_overrides = (
                    dict(request.setting_overrides)
                    if isinstance(request.setting_overrides, dict)
                    else {}
                )
                disable_auto_web_fallback = _truthy_flag(
                    request_overrides.get("__disable_auto_web_fallback")
                )
                if _should_auto_web_fallback(
                    message=request.message,
                    chat_history=chat_history,
                    disable_auto_web_fallback=disable_auto_web_fallback,
                ):
                    request = _request_with_command(request, WEB_SEARCH_COMMAND)
                    logger.warning("chat_path_selected path=web_fallback_llm")
            logger.warning("chat_path_fallback reason=fast_qa_returned_none")
        except Exception as exc:
            logger.exception("Fast ask path failed; falling back to streaming pipeline: %s", exc)
    elif _is_orchestrator_mode(requested_mode):
        logger.warning("chat_path_selected path=%s", requested_mode)
    elif not API_CHAT_FAST_PATH:
        logger.warning("chat_path_fallback reason=fast_path_disabled")

    timeout_seconds = _resolve_chat_timeout_seconds(requested_mode=requested_mode)

    def consume_stream() -> dict[str, Any]:
        iterator = stream_chat_turn(context=context, user_id=user_id, request=request)
        try:
            while True:
                next(iterator)
        except StopIteration as stop:
            return stop.value

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(consume_stream)
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError:
        message = request.message.strip()
        timeout_mode = requested_mode if _is_orchestrator_mode(requested_mode) else "ask"
        timeout_mode_variant = _mode_variant_from_request(request=request, requested_mode=timeout_mode)
        turn_attachments = _normalize_request_attachments(request)
        conversation_id, conversation_name, data_source, conversation_icon_key = get_or_create_conversation(
            user_id=user_id,
            conversation_id=request.conversation_id,
        )
        conversation_name, conversation_icon_key = maybe_autoname_conversation(
            user_id=user_id,
            conversation_id=conversation_id,
            current_name=conversation_name,
            message=message,
            agent_mode=request.agent_mode,
        )
        data_source = deepcopy(data_source or {})
        data_source["conversation_icon_key"] = conversation_icon_key
        timeout_answer, timeout_info = build_extractive_timeout_answer(
            context=context,
            user_id=user_id,
        )
        timeout_display_mode = timeout_mode_variant or timeout_mode
        timeout_info = normalize_info_evidence_html(timeout_info)
        timeout_answer = enforce_required_citations(
            answer=timeout_answer,
            info_html=timeout_info,
            citation_mode=request.citation,
        )
        timeout_info_panel = build_info_panel_copy(
            request_message=message,
            answer_text=timeout_answer,
            info_html=timeout_info,
            mode=timeout_mode,
            next_steps=[],
            web_summary={},
        )
        timeout_info_panel["verification_contract_version"] = VERIFICATION_CONTRACT_VERSION
        if timeout_mode_variant:
            timeout_info_panel["mode_variant"] = timeout_mode_variant
        blocks, documents = build_turn_blocks(answer_text=timeout_answer, question=message)

        messages = deepcopy(data_source.get("messages", []))
        if message:
            messages.append([message, timeout_answer])
        retrieval_history = deepcopy(data_source.get("retrieval_messages", []))
        retrieval_history.append(timeout_info)
        plot_history = deepcopy(data_source.get("plot_history", []))
        plot_history.append(None)
        message_meta = deepcopy(data_source.get("message_meta", []))
        message_meta.append(
            {
                "mode": timeout_mode,
                "activity_run_id": None,
                "actions_taken": [],
                "sources_used": [],
                "source_usage": [],
                "attachments": turn_attachments,
                "next_recommended_steps": [],
                "needs_human_review": False,
                "human_review_notes": None,
                "web_summary": {},
                "info_panel": timeout_info_panel,
                "mindmap": {},
                "blocks": blocks,
                "documents": documents,
                "halt_reason": HaltReason.llm_timeout,
                "mode_requested": timeout_display_mode,
                "mode_actually_used": "extractive_fallback",
            }
        )

        conversation_payload = {
            "selected": deepcopy(data_source.get("selected", {})),
            "messages": messages,
            "retrieval_messages": retrieval_history,
            "plot_history": plot_history,
            "message_meta": message_meta,
            "state": deepcopy(data_source.get("state", STATE)),
            "likes": deepcopy(data_source.get("likes", [])),
        }
        persist_conversation(conversation_id, conversation_payload)

        return {
            "conversation_id": conversation_id,
            "conversation_name": conversation_name,
            "message": message,
            "answer": timeout_answer,
            "blocks": blocks,
            "documents": documents,
            "info": timeout_info,
            "plot": None,
            "state": deepcopy(data_source.get("state", STATE)),
            "mode": timeout_mode,
            "actions_taken": [],
            "sources_used": [],
            "source_usage": [],
            "next_recommended_steps": [],
            "needs_human_review": False,
            "human_review_notes": None,
            "web_summary": {},
            "activity_run_id": None,
            "info_panel": timeout_info_panel,
            "mindmap": {},
            "halt_reason": HaltReason.llm_timeout,
            "mode_requested": timeout_display_mode,
            "mode_actually_used": "extractive_fallback",
        }
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
