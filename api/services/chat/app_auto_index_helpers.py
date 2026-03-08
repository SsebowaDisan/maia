from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from time import monotonic
from typing import Any, Callable

from api.context import ApiContext
from api.schemas import ChatRequest, IndexSelection

from .constants import logger

def auto_index_urls_for_request(
    *,
    context: ApiContext,
    user_id: str,
    request: ChatRequest,
    settings: dict[str, Any] | None,
    _extract_message_urls: Callable[..., list[str]],
    load_user_settings: Callable[..., dict[str, Any]],
    _auto_url_cache_key: Callable[..., str],
    _auto_url_cache_get: Callable[..., list[str] | None],
    _auto_url_cache_put: Callable[..., None],
    _normalized_request_selection: Callable[..., dict[str, IndexSelection]],
    _pick_target_index_id: Callable[..., int | None],
    _merge_request_index_selection: Callable[..., dict[str, IndexSelection]],
    _errors_indicate_already_indexed: Callable[..., bool],
    index_urls: Callable[..., dict[str, Any]],
    _resolve_existing_url_source_ids: Callable[..., list[str]],
    _apply_url_grounded_index_selection: Callable[..., dict[str, IndexSelection]],
    _source_ids_have_document_relations: Callable[..., bool],
    _request_with_updates: Callable[..., ChatRequest],
    _override_request_index_selection: Callable[..., dict[str, IndexSelection]],
    _AUTO_URL_INDEX_MARKER: str,
    env_bool_fn: Callable[..., bool],
    web_search_command: str,
    int_or_default_fn: Callable[..., int],
    flowsettings_obj: object,
) -> ChatRequest:
    if not env_bool_fn("MAIA_CHAT_AUTO_INDEX_URLS_ENABLED", default=True):
        return request
    if str(request.command or "").strip().lower() == str(web_search_command).strip().lower():
        return request
    existing_overrides = (
        dict(request.setting_overrides)
        if isinstance(request.setting_overrides, dict)
        else {}
    )
    if bool(existing_overrides.get(_AUTO_URL_INDEX_MARKER)):
        return request
    urls = _extract_message_urls(request.message, max_urls=8)
    if not urls:
        return request
    strict_url_grounding = env_bool_fn("MAIA_CHAT_STRICT_URL_GROUNDING", default=True)

    target_index_id = _pick_target_index_id(request, context)
    if target_index_id is None:
        logger.warning("auto_url_indexing_skipped reason=no_target_index urls=%s", ",".join(urls[:3]))
        existing_overrides[_AUTO_URL_INDEX_MARKER] = True
        return _request_with_updates(request, {"setting_overrides": existing_overrides})

    cache_ttl_seconds = max(
        0,
        int_or_default_fn(
            getattr(flowsettings_obj, "MAIA_CHAT_AUTO_INDEX_URLS_CACHE_TTL_SECONDS", 1800),
            1800,
        ),
    )
    cache_max_entries = max(
        1,
        int_or_default_fn(
            getattr(flowsettings_obj, "MAIA_CHAT_AUTO_INDEX_URLS_CACHE_MAX_ENTRIES", 1024),
            1024,
        ),
    )
    cached_file_ids = _auto_url_cache_get(
        user_id=user_id,
        index_id=target_index_id,
        urls=urls,
        ttl_seconds=cache_ttl_seconds,
    )
    if cached_file_ids:
        merged_selection = _apply_url_grounded_index_selection(
            request,
            index_id=target_index_id,
            file_ids=cached_file_ids,
            strict_url_grounding=strict_url_grounding,
        )
        existing_overrides[_AUTO_URL_INDEX_MARKER] = True
        logger.warning(
            "auto_url_indexing_cache_hit index_id=%s urls=%s file_ids=%d",
            target_index_id,
            ",".join(urls[:3]),
            len(cached_file_ids),
        )
        return _request_with_updates(
            request,
            {
                "index_selection": merged_selection,
                "setting_overrides": existing_overrides,
            },
        )

    existing_source_ids = _resolve_existing_url_source_ids(
        context=context,
        user_id=user_id,
        index_id=target_index_id,
        urls=urls,
    )
    existing_sources_have_docs = (
        _source_ids_have_document_relations(
            context=context,
            index_id=target_index_id,
            source_ids=existing_source_ids,
        )
        if existing_source_ids
        else False
    )

    resolved_settings = settings if isinstance(settings, dict) else load_user_settings(context, user_id)
    auto_reindex = env_bool_fn("MAIA_CHAT_AUTO_INDEX_URLS_REINDEX", default=False)
    auto_include_pdfs = env_bool_fn("MAIA_CHAT_AUTO_INDEX_URLS_INCLUDE_PDFS", default=False)
    auto_include_images = env_bool_fn("MAIA_CHAT_AUTO_INDEX_URLS_INCLUDE_IMAGES", default=False)
    auto_crawl_depth = max(
        0,
        int_or_default_fn(
            getattr(flowsettings_obj, "MAIA_CHAT_AUTO_INDEX_URLS_CRAWL_DEPTH", 1),
            1,
        ),
    )
    auto_crawl_max_pages = max(
        0,
        int_or_default_fn(
            getattr(flowsettings_obj, "MAIA_CHAT_AUTO_INDEX_URLS_MAX_PAGES", 4),
            4,
        ),
    )
    auto_timeout_seconds = max(
        6,
        int_or_default_fn(
            getattr(flowsettings_obj, "MAIA_CHAT_AUTO_INDEX_URLS_TIMEOUT_SECONDS", 40),
            40,
        ),
    )

    if existing_source_ids and existing_sources_have_docs and not auto_reindex:
        _auto_url_cache_put(
            user_id=user_id,
            index_id=target_index_id,
            urls=urls,
            file_ids=existing_source_ids,
            ttl_seconds=cache_ttl_seconds,
            max_entries=cache_max_entries,
        )
        merged_selection = _apply_url_grounded_index_selection(
            request,
            index_id=target_index_id,
            file_ids=existing_source_ids,
            strict_url_grounding=strict_url_grounding,
        )
        existing_overrides[_AUTO_URL_INDEX_MARKER] = True
        logger.warning(
            "auto_url_indexing_reused_existing_sources index_id=%s urls=%s file_ids=%d",
            target_index_id,
            ",".join(urls[:3]),
            len(existing_source_ids),
        )
        return _request_with_updates(
            request,
            {
                "index_selection": merged_selection,
                "setting_overrides": existing_overrides,
            },
        )

    if existing_source_ids and not existing_sources_have_docs:
        auto_reindex = True
        logger.warning(
            "auto_url_indexing_stale_sources_no_docs index_id=%s urls=%s source_ids=%d",
            target_index_id,
            ",".join(urls[:3]),
            len(existing_source_ids),
        )

    logger.warning(
        "auto_url_indexing_start index_id=%s urls=%s reindex=%s crawl_depth=%d max_pages=%d include_pdfs=%s include_images=%s timeout_seconds=%d",
        target_index_id,
        ",".join(urls[:3]),
        str(bool(auto_reindex)).lower(),
        auto_crawl_depth,
        auto_crawl_max_pages,
        str(bool(auto_include_pdfs)).lower(),
        str(bool(auto_include_images)).lower(),
        auto_timeout_seconds,
    )
    started_at = monotonic()

    def _run_index_urls_call(*, reindex_flag: bool) -> dict[str, Any]:
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(
                index_urls,
                context=context,
                user_id=user_id,
                urls=urls,
                index_id=target_index_id,
                reindex=reindex_flag,
                settings=resolved_settings,
                web_crawl_depth=auto_crawl_depth,
                web_crawl_max_pages=auto_crawl_max_pages,
                web_crawl_same_domain_only=True,
                include_pdfs=auto_include_pdfs,
                include_images=auto_include_images,
                scope="chat_temp",
            )
            return future.result(timeout=auto_timeout_seconds)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    try:
        result = _run_index_urls_call(reindex_flag=auto_reindex)
    except FutureTimeoutError:
        timeout_source_ids = _resolve_existing_url_source_ids(
            context=context,
            user_id=user_id,
            index_id=target_index_id,
            urls=urls,
        )
        timeout_sources_have_docs = (
            _source_ids_have_document_relations(
                context=context,
                index_id=target_index_id,
                source_ids=timeout_source_ids,
            )
            if timeout_source_ids
            else False
        )
        if timeout_source_ids and timeout_sources_have_docs:
            _auto_url_cache_put(
                user_id=user_id,
                index_id=target_index_id,
                urls=urls,
                file_ids=timeout_source_ids,
                ttl_seconds=cache_ttl_seconds,
                max_entries=cache_max_entries,
            )
            merged_selection = _apply_url_grounded_index_selection(
                request,
                index_id=target_index_id,
                file_ids=timeout_source_ids,
                strict_url_grounding=strict_url_grounding,
            )
            existing_overrides[_AUTO_URL_INDEX_MARKER] = True
            logger.warning(
                "auto_url_indexing_timeout_reused_existing_sources index_id=%s urls=%s file_ids=%d timeout_seconds=%d",
                target_index_id,
                ",".join(urls[:3]),
                len(timeout_source_ids),
                auto_timeout_seconds,
            )
            return _request_with_updates(
                request,
                {
                    "index_selection": merged_selection,
                    "setting_overrides": existing_overrides,
                },
            )
        logger.warning(
            "auto_url_indexing_timeout index_id=%s urls=%s timeout_seconds=%d",
            target_index_id,
            ",".join(urls[:3]),
            auto_timeout_seconds,
        )
        existing_overrides[_AUTO_URL_INDEX_MARKER] = True
        updates: dict[str, Any] = {"setting_overrides": existing_overrides}
        if strict_url_grounding:
            updates["index_selection"] = _override_request_index_selection(
                request,
                index_id=target_index_id,
                mode="disabled",
                file_ids=[],
            )
        return _request_with_updates(request, updates)
    except Exception as exc:
        error_source_ids = _resolve_existing_url_source_ids(
            context=context,
            user_id=user_id,
            index_id=target_index_id,
            urls=urls,
        )
        error_sources_have_docs = (
            _source_ids_have_document_relations(
                context=context,
                index_id=target_index_id,
                source_ids=error_source_ids,
            )
            if error_source_ids
            else False
        )
        if error_source_ids and error_sources_have_docs:
            _auto_url_cache_put(
                user_id=user_id,
                index_id=target_index_id,
                urls=urls,
                file_ids=error_source_ids,
                ttl_seconds=cache_ttl_seconds,
                max_entries=cache_max_entries,
            )
            merged_selection = _apply_url_grounded_index_selection(
                request,
                index_id=target_index_id,
                file_ids=error_source_ids,
                strict_url_grounding=strict_url_grounding,
            )
            existing_overrides[_AUTO_URL_INDEX_MARKER] = True
            logger.warning(
                "auto_url_indexing_error_reused_existing_sources index_id=%s urls=%s file_ids=%d",
                target_index_id,
                ",".join(urls[:3]),
                len(error_source_ids),
            )
            return _request_with_updates(
                request,
                {
                    "index_selection": merged_selection,
                    "setting_overrides": existing_overrides,
                },
            )
        logger.warning(
            "auto_url_indexing_failed urls=%s error=%s",
            ",".join(urls[:3]),
            " ".join(str(exc).split())[:240],
        )
        existing_overrides[_AUTO_URL_INDEX_MARKER] = True
        updates = {"setting_overrides": existing_overrides}
        if strict_url_grounding:
            updates["index_selection"] = _override_request_index_selection(
                request,
                index_id=target_index_id,
                mode="disabled",
                file_ids=[],
            )
        return _request_with_updates(request, updates)

    file_ids = [
        str(item).strip()
        for item in (result.get("file_ids", []) if isinstance(result, dict) else [])
        if str(item).strip()
    ]
    error_rows = [
        " ".join(str(item or "").split()).strip()
        for item in (result.get("errors", []) if isinstance(result, dict) else [])
        if " ".join(str(item or "").split()).strip()
    ]
    if not file_ids and _errors_indicate_already_indexed(error_rows):
        existing_source_ids = _resolve_existing_url_source_ids(
            context=context,
            user_id=user_id,
            index_id=target_index_id,
            urls=urls,
        )
        if existing_source_ids and _source_ids_have_document_relations(
            context=context,
            index_id=target_index_id,
            source_ids=existing_source_ids,
        ):
            file_ids = existing_source_ids
            logger.warning(
                "auto_url_indexing_reused_existing_sources index_id=%s urls=%s file_ids=%d",
                target_index_id,
                ",".join(urls[:3]),
                len(file_ids),
            )
    if not file_ids:
        existing_source_ids = _resolve_existing_url_source_ids(
            context=context,
            user_id=user_id,
            index_id=target_index_id,
            urls=urls,
        )
        if existing_source_ids and _source_ids_have_document_relations(
            context=context,
            index_id=target_index_id,
            source_ids=existing_source_ids,
        ):
            file_ids = existing_source_ids
            logger.warning(
                "auto_url_indexing_reused_existing_sources_post_index index_id=%s urls=%s file_ids=%d",
                target_index_id,
                ",".join(urls[:3]),
                len(file_ids),
            )
    if not file_ids:
        logger.warning("auto_url_indexing_no_file_ids urls=%s", ",".join(urls[:3]))
        existing_overrides[_AUTO_URL_INDEX_MARKER] = True
        updates = {"setting_overrides": existing_overrides}
        if strict_url_grounding:
            updates["index_selection"] = _override_request_index_selection(
                request,
                index_id=target_index_id,
                mode="disabled",
                file_ids=[],
            )
        return _request_with_updates(request, updates)

    _auto_url_cache_put(
        user_id=user_id,
        index_id=target_index_id,
        urls=urls,
        file_ids=file_ids,
        ttl_seconds=cache_ttl_seconds,
        max_entries=cache_max_entries,
    )
    merged_selection = _apply_url_grounded_index_selection(
        request,
        index_id=target_index_id,
        file_ids=file_ids,
        strict_url_grounding=strict_url_grounding,
    )
    existing_overrides[_AUTO_URL_INDEX_MARKER] = True
    logger.warning(
        "auto_url_indexing_completed index_id=%s urls=%s file_ids=%d",
        target_index_id,
        ",".join(urls[:3]),
        len(file_ids),
    )
    elapsed_ms = int((monotonic() - started_at) * 1000)
    logger.warning(
        "auto_url_indexing_timing index_id=%s urls=%s elapsed_ms=%d",
        target_index_id,
        ",".join(urls[:3]),
        elapsed_ms,
    )
    return _request_with_updates(
        request,
        {
            "index_selection": merged_selection,
            "setting_overrides": existing_overrides,
        },
    )
