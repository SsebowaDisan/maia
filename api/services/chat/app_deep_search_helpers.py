from __future__ import annotations

from typing import Callable

from api.context import ApiContext
from api.schemas import ChatRequest, IndexSelection

from .app_prompt_helpers import (
    _DEEP_SEARCH_COMPLEX_MAX_QUERY_VARIANTS,
    _DEEP_SEARCH_COMPLEX_MIN_UNIQUE_SOURCES,
    _DEEP_SEARCH_COMPLEX_RESULTS_PER_QUERY,
    _DEEP_SEARCH_COMPLEX_WEB_BUDGET,
    _DEEP_SEARCH_COMPLEXITY_VALUES,
    _DEEP_SEARCH_DEFAULT_SOURCE_LIMIT,
    _DEEP_SEARCH_MODE,
    _DEEP_SEARCH_NORMAL_MAX_QUERY_VARIANTS,
    _DEEP_SEARCH_NORMAL_MIN_UNIQUE_SOURCES,
    _DEEP_SEARCH_NORMAL_RESULTS_PER_QUERY,
    _DEEP_SEARCH_NORMAL_WEB_BUDGET,
)


def apply_deep_search_defaults(
    *,
    context: ApiContext,
    user_id: str,
    request: ChatRequest,
    int_or_default_fn: Callable[[object, int], int],
    classify_deep_search_complexity_fn: Callable[[str], str],
    normalized_request_selection_fn: Callable[[ChatRequest], dict[str, IndexSelection]],
    resolve_prompt_scoped_pdf_ids_fn: Callable[..., dict[int, list[str]]],
    selected_index_ids_for_deep_search_fn: Callable[..., list[int]],
    list_index_source_ids_fn: Callable[..., list[str]],
    request_with_updates_fn: Callable[[ChatRequest, dict[str, object]], ChatRequest],
) -> ChatRequest:
    if str(request.agent_mode or "").strip().lower() != _DEEP_SEARCH_MODE:
        return request

    existing_overrides = (
        dict(request.setting_overrides)
        if isinstance(request.setting_overrides, dict)
        else {}
    )
    max_source_ids = max(
        40,
        min(
            int_or_default_fn(
                existing_overrides.get("__deep_search_max_source_ids"),
                _DEEP_SEARCH_DEFAULT_SOURCE_LIMIT,
            ),
            1200,
        ),
    )
    requested_complexity = " ".join(
        str(existing_overrides.get("__deep_search_complexity") or "").split()
    ).strip().lower()
    complexity = (
        requested_complexity
        if requested_complexity in _DEEP_SEARCH_COMPLEXITY_VALUES
        else classify_deep_search_complexity_fn(request.message)
    )
    normal_mode = complexity != "complex"
    budget_floor = 60 if normal_mode else 120
    budget_default = (
        _DEEP_SEARCH_NORMAL_WEB_BUDGET if normal_mode else _DEEP_SEARCH_COMPLEX_WEB_BUDGET
    )
    requested_web_budget = max(
        budget_floor,
        min(
            int_or_default_fn(
                existing_overrides.get("__research_web_search_budget"),
                budget_default,
            ),
            350,
        ),
    )
    existing_overrides.setdefault("__deep_search_enabled", True)
    existing_overrides.setdefault("__llm_only_keyword_generation", True)
    existing_overrides.setdefault("__llm_only_keyword_generation_strict", True)
    existing_overrides.setdefault("__deep_search_complexity", complexity)
    existing_overrides.setdefault("__deep_search_max_source_ids", max_source_ids)
    existing_overrides.setdefault("__research_depth_tier", "deep_research")
    existing_overrides.setdefault("__research_web_search_budget", requested_web_budget)
    existing_overrides.setdefault(
        "__research_max_query_variants",
        (
            _DEEP_SEARCH_NORMAL_MAX_QUERY_VARIANTS
            if normal_mode
            else _DEEP_SEARCH_COMPLEX_MAX_QUERY_VARIANTS
        ),
    )
    existing_overrides.setdefault(
        "__research_results_per_query",
        (
            _DEEP_SEARCH_NORMAL_RESULTS_PER_QUERY
            if normal_mode
            else _DEEP_SEARCH_COMPLEX_RESULTS_PER_QUERY
        ),
    )
    existing_overrides.setdefault("__research_fused_top_k", 220)
    existing_overrides.setdefault(
        "__research_min_unique_sources",
        (
            _DEEP_SEARCH_NORMAL_MIN_UNIQUE_SOURCES
            if normal_mode
            else _DEEP_SEARCH_COMPLEX_MIN_UNIQUE_SOURCES
        ),
    )
    existing_overrides.setdefault(
        "__research_source_budget_min",
        60 if normal_mode else 120,
    )
    existing_overrides.setdefault(
        "__research_source_budget_max",
        100 if normal_mode else 180,
    )
    existing_overrides.setdefault("__file_research_source_budget_min", 120)
    existing_overrides.setdefault("__file_research_source_budget_max", 220)
    existing_overrides.setdefault("__file_research_max_sources", 220)
    existing_overrides.setdefault("__file_research_max_chunks", 1800)
    existing_overrides.setdefault("__file_research_max_scan_pages", 200)

    merged_selection = normalized_request_selection_fn(request)
    user_selected_files = any(
        str(getattr(selection, "mode", "") or "").strip().lower() == "select"
        and any(str(item).strip() for item in (getattr(selection, "file_ids", []) or []))
        for selection in merged_selection.values()
    )
    prompt_scoped_pdf_ids = resolve_prompt_scoped_pdf_ids_fn(
        context=context,
        user_id=user_id,
        request=request,
        limit=max_source_ids,
    )
    existing_overrides["__deep_search_prompt_scoped_pdfs"] = bool(prompt_scoped_pdf_ids)
    existing_overrides["__deep_search_user_selected_files"] = bool(user_selected_files)
    selected_index_ids = selected_index_ids_for_deep_search_fn(request=request, context=context)
    selected_index_ids = list(dict.fromkeys([*selected_index_ids, *prompt_scoped_pdf_ids.keys()]))
    for index_id in selected_index_ids:
        key = str(index_id)
        existing_selection = merged_selection.get(key)
        existing_ids = (
            [
                str(item).strip()
                for item in getattr(existing_selection, "file_ids", [])
                if str(item).strip()
            ]
            if existing_selection
            else []
        )
        scoped_ids = prompt_scoped_pdf_ids.get(index_id, [])
        auto_ids = (
            [
                str(item).strip()
                for item in scoped_ids
                if str(item).strip()
            ]
            if scoped_ids
            else list_index_source_ids_fn(
                context=context,
                user_id=user_id,
                index_id=index_id,
                limit=max_source_ids,
            )
        )
        merged_ids: list[str] = []
        seen: set[str] = set()
        for source_id in [*existing_ids, *auto_ids]:
            normalized = str(source_id).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged_ids.append(normalized)
            if len(merged_ids) >= max_source_ids:
                break
        if merged_ids:
            merged_selection[key] = IndexSelection(mode="select", file_ids=merged_ids)

    return request_with_updates_fn(
        request,
        {
            "index_selection": merged_selection,
            "setting_overrides": existing_overrides,
        },
    )
