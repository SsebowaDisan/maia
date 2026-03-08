from __future__ import annotations

from typing import Any, Callable

from api.services.agent.models import AgentSource
from api.services.agent.tools.base import (
    ToolExecutionContext,
    ToolTraceEvent,
)
from api.services.agent.tools.research_helpers import (
    extract_search_variants as _extract_search_variants,
    normalize_search_provider as _normalize_search_provider,
    safe_snippet as _safe_snippet,
    truthy as _truthy,
)
from api.services.agent.tools.research_web_helpers import (
    _as_bounded_int,
    _build_research_tree,
    _resolve_domain_scope_hosts,
    _resolve_domain_scope_mode,
    _website_scene_payload,
)
from api.services.agent.tools.research_web_stream_bing import run_bing_provider_and_materialize_stage
from api.services.agent.tools.research_web_stream_brave import run_brave_provider_stage
from api.services.agent.tools.research_web_stream_enrichment import run_enrichment_and_finalize_stage


def execute_web_research_stream(
    *,
    context: ToolExecutionContext,
    prompt: str,
    params: dict[str, Any],
    get_connector_registry_fn: Callable[..., Any],
):
    get_connector_registry = get_connector_registry_fn
    query = str(params.get("query") or prompt).strip() or "company market research"
    configured_max_variants = context.settings.get("__research_max_query_variants")
    max_query_variants = _as_bounded_int(
        params.get("max_query_variants"),
        default=_as_bounded_int(configured_max_variants, default=8, low=2, high=40),
        low=2,
        high=40,
    )
    configured_results_per_query = context.settings.get("__research_results_per_query")
    results_per_query = _as_bounded_int(
        params.get("results_per_query"),
        default=_as_bounded_int(configured_results_per_query, default=12, low=4, high=30),
        low=4,
        high=30,
    )
    configured_fused_top_k = context.settings.get("__research_fused_top_k")
    fused_top_k = _as_bounded_int(
        params.get("fused_top_k"),
        default=_as_bounded_int(configured_fused_top_k, default=60, low=8, high=600),
        low=8,
        high=600,
    )
    configured_min_sources = context.settings.get("__research_min_unique_sources")
    min_unique_sources = _as_bounded_int(
        params.get("min_unique_sources"),
        default=_as_bounded_int(configured_min_sources, default=15, low=3, high=500),
        low=3,
        high=500,
    )
    configured_search_budget = context.settings.get("__research_web_search_budget")
    requested_search_budget = _as_bounded_int(
        params.get("search_budget"),
        default=_as_bounded_int(
            configured_search_budget,
            default=max_query_variants * results_per_query,
            low=20,
            high=800,
        ),
        low=20,
        high=800,
    )
    max_search_rounds = _as_bounded_int(
        context.settings.get("__research_max_search_rounds"),
        default=1,
        low=1,
        high=4,
    )
    depth_tier = " ".join(str(params.get("research_depth_tier") or context.settings.get("__research_depth_tier") or "standard").split()).strip().lower() or "standard"
    max_live_queries = _as_bounded_int(
        context.settings.get("__research_theater_max_live_queries"),
        default=10,
        low=1,
        high=30,
    )
    max_live_clicks_per_query = _as_bounded_int(
        context.settings.get("__research_theater_clicks_per_query"),
        default=2,
        low=1,
        high=5,
    )
    requested_variants_raw = params.get("query_variants")
    requested_variants = (
        [
            " ".join(str(item).split()).strip()
            for item in requested_variants_raw
            if " ".join(str(item).split()).strip()
        ][:24]
        if isinstance(requested_variants_raw, list)
        else []
    )
    query_variants = _extract_search_variants(
        query=query,
        prompt=prompt,
        requested_variants=requested_variants,
        max_variants=max_query_variants,
    )
    if not query_variants:
        query_variants = [query]
    domain_scope_hosts = _resolve_domain_scope_hosts(
        params=params,
        context_settings=context.settings if isinstance(context.settings, dict) else {},
        query=query,
        query_variants=query_variants,
    )
    domain_scope_mode = _resolve_domain_scope_mode(
        params=params,
        domain_scope_hosts=domain_scope_hosts,
    )
    domain_scope_filtered_out = 0
    search_plan: list[tuple[str, int]] = []
    remaining_budget = requested_search_budget
    for idx, query_variant in enumerate(query_variants):
        variants_left = max(1, len(query_variants) - idx)
        allocated = remaining_budget // variants_left
        if remaining_budget % variants_left:
            allocated += 1
        per_query_limit = max(1, min(results_per_query, allocated))
        search_plan.append((query_variant, per_query_limit))
        remaining_budget = max(0, remaining_budget - per_query_limit)
    planned_result_budget = max(1, sum(limit for _query, limit in search_plan))
    requested_provider = _normalize_search_provider(
        params.get("provider") or params.get("search_provider")
    )
    allow_provider_fallback = _truthy(
        params.get("allow_provider_fallback"),
        default=True,
    )
    sources: list[AgentSource] = []
    bullets: list[str] = []
    trace_events: list[ToolTraceEvent] = []
    started_event = ToolTraceEvent(
        event_type="web_search_started",
        title="Searching online sources",
        detail=f"Query: {_safe_snippet(query, 120)}",
        data={
            "query": query,
            "query_variants": query_variants,
            "provider_requested": requested_provider,
            "research_depth_tier": depth_tier,
            "max_query_variants": max_query_variants,
            "results_per_query": results_per_query,
            "search_budget_requested": requested_search_budget,
            "search_budget_effective": planned_result_budget,
            "fused_top_k": fused_top_k,
            "min_unique_sources": min_unique_sources,
            "domain_scope_hosts": domain_scope_hosts[:6],
            "domain_scope_mode": domain_scope_mode,
        },
    )
    trace_events.append(started_event)
    yield started_event

    # ── S2: Research Tree Decomposition ─────────────────────────────────────
    _rt_registry_names = get_connector_registry().names()
    _research_branches = _build_research_tree(
        query=query,
        depth_tier=depth_tier,
        registry_names=_rt_registry_names,
    )
    if _research_branches:
        tree_started = ToolTraceEvent(
            event_type="research_tree_started",
            title="Building research tree",
            detail=f"Decomposed into {len(_research_branches)} structural branch(es)",
            data={
                "branch_count": len(_research_branches),
                "depth_tier": depth_tier,
                "branches": [b["branch_label"] for b in _research_branches],
            },
        )
        trace_events.append(tree_started)
        yield tree_started
        for _branch in _research_branches:
            _branch_event = ToolTraceEvent(
                event_type="research_branch_started",
                title=f"Branch: {_branch['branch_label']}",
                detail=_safe_snippet(_branch["sub_question"], 120),
                data={
                    "branch_label": _branch["branch_label"],
                    "sub_question": _branch["sub_question"],
                    "preferred_providers": _branch["preferred_providers"],
                },
            )
            trace_events.append(_branch_event)
            yield _branch_event

    if domain_scope_mode != "off" and domain_scope_hosts:
        scope_event = ToolTraceEvent(
            event_type="tool_progress",
            title="Apply domain scope to web research",
            detail=f"{domain_scope_mode} scope: {', '.join(domain_scope_hosts[:3])}",
            data=_website_scene_payload(
                lane="search-domain-scope",
                primary_index=1,
                payload={
                    "domain_scope_hosts": domain_scope_hosts[:6],
                    "domain_scope_mode": domain_scope_mode,
                },
            ),
        )
        trace_events.append(scope_event)
        yield scope_event
    provider_event = ToolTraceEvent(
        event_type="tool_progress",
        title="Select web research provider",
        detail=f"Provider: {requested_provider}",
        data=_website_scene_payload(
            lane="search-provider-select",
            primary_index=1,
            payload={
                "provider_requested": requested_provider,
                "provider_fallback_enabled": allow_provider_fallback,
                "research_depth_tier": depth_tier,
            },
        ),
    )
    trace_events.append(provider_event)
    yield provider_event
    rewrite_event = ToolTraceEvent(
        event_type="retrieval_query_rewrite",
        title="Generate focused search rewrites",
        detail=f"Prepared {len(query_variants)} query variant(s)",
        data={"query_variants": query_variants},
    )
    trace_events.append(rewrite_event)
    yield rewrite_event
    navigate_event = ToolTraceEvent(
        event_type="browser_navigate",
        title="Open search provider",
        detail=f"Submitting {len(query_variants)} rewritten query variant(s) to {requested_provider}",
        data=_website_scene_payload(
            lane="search-provider",
            primary_index=1,
            payload={
                "query": query,
                "provider": requested_provider,
                "query_variants": query_variants,
            },
        ),
    )
    trace_events.append(navigate_event)
    yield navigate_event


    payload: dict[str, Any] = {}
    used_provider = requested_provider
    provider_state: dict[str, Any] = {
        "payload": payload,
        "used_provider": used_provider,
        "ok": False,
        "search_runs": [],
        "provider_failures": [],
        "provider_attempted": [],
        "domain_scope_filtered_out": int(domain_scope_filtered_out),
    }

    yield from run_brave_provider_stage(
        context=context,
        requested_provider=requested_provider,
        search_plan=search_plan,
        planned_result_budget=planned_result_budget,
        requested_search_budget=requested_search_budget,
        query_variants=query_variants,
        max_live_queries=max_live_queries,
        max_live_clicks_per_query=max_live_clicks_per_query,
        domain_scope_hosts=domain_scope_hosts,
        domain_scope_mode=domain_scope_mode,
        min_unique_sources=min_unique_sources,
        fused_top_k=fused_top_k,
        query=query,
        trace_events=trace_events,
        state=provider_state,
        get_connector_registry_fn=get_connector_registry,
    )

    yield from run_bing_provider_and_materialize_stage(
        context=context,
        requested_provider=requested_provider,
        allow_provider_fallback=allow_provider_fallback,
        results_per_query=results_per_query,
        planned_result_budget=planned_result_budget,
        query_variants=query_variants,
        query=query,
        max_live_clicks_per_query=max_live_clicks_per_query,
        fused_top_k=fused_top_k,
        min_unique_sources=min_unique_sources,
        domain_scope_hosts=domain_scope_hosts,
        domain_scope_mode=domain_scope_mode,
        trace_events=trace_events,
        sources=sources,
        bullets=bullets,
        state=provider_state,
        get_connector_registry_fn=get_connector_registry,
    )

    return (
        yield from run_enrichment_and_finalize_stage(
            context=context,
            depth_tier=depth_tier,
            max_search_rounds=max_search_rounds,
            query=query,
            query_variants=query_variants,
            min_unique_sources=min_unique_sources,
            results_per_query=results_per_query,
            requested_provider=requested_provider,
            allow_provider_fallback=allow_provider_fallback,
            requested_search_budget=requested_search_budget,
            planned_result_budget=planned_result_budget,
            max_query_variants=max_query_variants,
            fused_top_k=fused_top_k,
            domain_scope_hosts=domain_scope_hosts,
            domain_scope_mode=domain_scope_mode,
            trace_events=trace_events,
            sources=sources,
            bullets=bullets,
            state=provider_state,
            _research_branches=_research_branches,
            get_connector_registry_fn=get_connector_registry,
        )
    )
