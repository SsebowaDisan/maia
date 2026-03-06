from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import quote_plus, urlparse

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.models import AgentSource
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolMetadata,
    ToolTraceEvent,
)
from api.services.agent.tools.research_helpers import (
    classify_provider_failure as _classify_provider_failure,
    extract_search_variants as _extract_search_variants,
    fuse_search_results as _fuse_search_results,
    normalize_search_provider as _normalize_search_provider,
    safe_snippet as _safe_snippet,
    truthy as _truthy,
)
from api.services.agent.tools.theater_cursor import with_scene


def _as_bounded_int(value: Any, *, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = int(default)
    return max(low, min(high, parsed))


def _search_results_url(provider: str, query: str) -> str:
    normalized = " ".join(str(query or "").split()).strip()
    if not normalized:
        return ""
    if provider == "brave_search":
        return f"https://search.brave.com/search?q={quote_plus(normalized)}"
    if provider == "bing_search":
        return f"https://www.bing.com/search?q={quote_plus(normalized)}"
    return ""


def _hostname_label(url: str) -> str:
    try:
        host = str(urlparse(url).netloc or "").strip().lower()
    except Exception:
        host = ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _website_scene_payload(
    *,
    lane: str,
    primary_index: int,
    secondary_index: int = 1,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return with_scene(
        payload or {},
        scene_surface="website",
        lane=lane,
        primary_index=primary_index,
        secondary_index=secondary_index,
    )


class WebResearchTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="marketing.web_research",
        action_class="read",
        risk_level="low",
        required_permissions=["web.read"],
        execution_policy="auto_execute",
        description="Search the web and synthesize source-backed insights.",
    )

    def execute_stream(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ):
        query = str(params.get("query") or prompt).strip() or "company market research"
        configured_max_variants = context.settings.get("__research_max_query_variants")
        max_query_variants = _as_bounded_int(
            params.get("max_query_variants"),
            default=_as_bounded_int(configured_max_variants, default=4, low=2, high=20),
            low=2,
            high=20,
        )
        configured_results_per_query = context.settings.get("__research_results_per_query")
        results_per_query = _as_bounded_int(
            params.get("results_per_query"),
            default=_as_bounded_int(configured_results_per_query, default=8, low=4, high=25),
            low=4,
            high=25,
        )
        configured_fused_top_k = context.settings.get("__research_fused_top_k")
        fused_top_k = _as_bounded_int(
            params.get("fused_top_k"),
            default=_as_bounded_int(configured_fused_top_k, default=24, low=8, high=220),
            low=8,
            high=220,
        )
        configured_min_sources = context.settings.get("__research_min_unique_sources")
        min_unique_sources = _as_bounded_int(
            params.get("min_unique_sources"),
            default=_as_bounded_int(configured_min_sources, default=8, low=3, high=200),
            low=3,
            high=200,
        )
        configured_search_budget = context.settings.get("__research_web_search_budget")
        requested_search_budget = _as_bounded_int(
            params.get("search_budget"),
            default=_as_bounded_int(
                configured_search_budget,
                default=max_query_variants * results_per_query,
                low=20,
                high=350,
            ),
            low=20,
            high=350,
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
            },
        )
        trace_events.append(started_event)
        yield started_event
        provider_event = ToolTraceEvent(
            event_type="tool_progress",
            title="Select web research provider",
            detail=f"Provider: {requested_provider}",
            data={
                "provider_requested": requested_provider,
                "provider_fallback_enabled": allow_provider_fallback,
                "research_depth_tier": depth_tier,
            },
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
        ok = False
        search_runs: list[dict[str, Any]] = []
        provider_failures: list[dict[str, Any]] = []
        provider_attempted: list[str] = []

        if requested_provider == "brave_search":
            try:
                provider_attempted.append("brave_search")
                trace_events.append(
                    ToolTraceEvent(
                        event_type="api_call_started",
                        title="Call Brave Search API",
                        detail=(
                            f"Running {len(search_plan)} query variant(s) "
                            f"with {planned_result_budget} total result slots"
                        ),
                        data={
                            "provider": "brave_search",
                            "search_budget_requested": requested_search_budget,
                            "search_budget_effective": planned_result_budget,
                        },
                    )
                )
                yield trace_events[-1]
                brave = get_connector_registry().build("brave_search", settings=context.settings)
                for idx, (query_variant, per_query_limit) in enumerate(search_plan, start=1):
                    search_url = _search_results_url("brave_search", query_variant)
                    if idx <= max_live_queries and search_url:
                        live_navigate_event = ToolTraceEvent(
                            event_type="browser_navigate",
                            title=f"Open Brave results {idx}/{len(query_variants)}",
                            detail=_safe_snippet(query_variant, 140),
                            data=_website_scene_payload(
                                lane="search-results-open",
                                primary_index=idx,
                                payload={
                                    "provider": "brave_search",
                                    "query": query_variant,
                                    "variant_index": idx,
                                    "url": search_url,
                                    "source_url": search_url,
                                    "render_quality": "live",
                                },
                            ),
                        )
                        trace_events.append(live_navigate_event)
                        yield live_navigate_event
                    query_event = ToolTraceEvent(
                        event_type="brave.search.query",
                        title=f"Run Brave query {idx}/{len(query_variants)}",
                        detail=_safe_snippet(query_variant, 140),
                        data={
                            "query": query_variant,
                            "variant_index": idx,
                            "provider": "brave_search",
                            "result_limit": per_query_limit,
                        },
                    )
                    trace_events.append(query_event)
                    yield query_event
                    run_payload = brave.web_search(query=query_variant, count=per_query_limit)
                    if not isinstance(run_payload, dict):
                        continue
                    run_payload["query_variant"] = query_variant
                    run_payload["result_limit"] = per_query_limit
                    search_runs.append(run_payload)
                    run_rows = run_payload.get("results") if isinstance(run_payload.get("results"), list) else []
                    run_urls = [
                        str(item.get("url") or "")
                        for item in run_rows
                        if isinstance(item, dict)
                    ][:5]
                    result_event = ToolTraceEvent(
                        event_type="brave.search.results",
                        title=f"Brave results for query {idx}",
                        detail=f"Captured {len(run_urls)} URL(s) from limit {per_query_limit}",
                        data={
                            "query": query_variant,
                            "top_urls": run_urls,
                            "provider": "brave_search",
                            "result_limit": per_query_limit,
                        },
                    )
                    trace_events.append(result_event)
                    yield result_event
                    if idx <= max_live_queries and search_url:
                        hover_event = ToolTraceEvent(
                            event_type="browser_hover",
                            title=f"Hover search results {idx}/{len(query_variants)}",
                            detail="Reviewing top-ranked result cards",
                            data=_website_scene_payload(
                                lane="search-results-hover",
                                primary_index=idx,
                                payload={
                                    "provider": "brave_search",
                                    "query": query_variant,
                                    "variant_index": idx,
                                    "url": search_url,
                                    "source_url": search_url,
                                },
                            ),
                        )
                        trace_events.append(hover_event)
                        yield hover_event
                        scroll_targets = [14.0, 36.0, 62.0]
                        if len(run_rows) >= 8:
                            scroll_count = 3
                        elif len(run_rows) >= 4:
                            scroll_count = 2
                        else:
                            scroll_count = 1
                        for scroll_step, scroll_percent in enumerate(scroll_targets[:scroll_count], start=1):
                            scroll_event = ToolTraceEvent(
                                event_type="browser_scroll",
                                title=f"Scroll Brave results {scroll_step}/{scroll_count}",
                                detail=f"Reviewing result cards ({int(round(scroll_percent))}%)",
                                data=_website_scene_payload(
                                    lane="search-results-scroll",
                                    primary_index=idx,
                                    secondary_index=scroll_step,
                                    payload={
                                        "provider": "brave_search",
                                        "query": query_variant,
                                        "variant_index": idx,
                                        "url": search_url,
                                        "source_url": search_url,
                                        "scroll_percent": float(scroll_percent),
                                        "scroll_direction": "down",
                                    },
                                ),
                            )
                            trace_events.append(scroll_event)
                            yield scroll_event
                        for rank, clicked_url in enumerate(run_urls[:max_live_clicks_per_query], start=1):
                            if not clicked_url:
                                continue
                            host_label = _hostname_label(clicked_url)
                            result_click_event = ToolTraceEvent(
                                event_type="browser_click",
                                title=f"Click result {rank}",
                                detail=(f"Open {host_label}" if host_label else f"Open result {rank}"),
                                data=_website_scene_payload(
                                    lane="search-result-click",
                                    primary_index=idx,
                                    secondary_index=rank,
                                    payload={
                                        "provider": "brave_search",
                                        "query": query_variant,
                                        "variant_index": idx,
                                        "result_rank": rank,
                                        "selector": f"result_rank_{rank}",
                                        "url": search_url,
                                        "source_url": search_url,
                                        "target_url": clicked_url,
                                    },
                                ),
                            )
                            trace_events.append(result_click_event)
                            yield result_click_event
                            click_event = ToolTraceEvent(
                                event_type="web_result_opened",
                                title=f"Open result {rank}",
                                detail=(f"Opening {host_label}" if host_label else f"Opening result {rank}"),
                                data=_website_scene_payload(
                                    lane="source-opened",
                                    primary_index=idx,
                                    secondary_index=rank,
                                    payload={
                                        "provider": "brave_search",
                                        "query": query_variant,
                                        "variant_index": idx,
                                        "result_rank": rank,
                                        "url": clicked_url,
                                        "source_url": clicked_url,
                                    },
                                ),
                            )
                            trace_events.append(click_event)
                            yield click_event
                            open_event = ToolTraceEvent(
                                event_type="browser_navigate",
                                title=f"Open source page {rank}",
                                detail=_safe_snippet(clicked_url, 140),
                                data=_website_scene_payload(
                                    lane="source-navigate",
                                    primary_index=idx,
                                    secondary_index=rank,
                                    payload={
                                        "provider": "brave_search",
                                        "query": query_variant,
                                        "variant_index": idx,
                                        "result_rank": rank,
                                        "url": clicked_url,
                                        "source_url": clicked_url,
                                        "render_quality": "live",
                                    },
                                ),
                            )
                            trace_events.append(open_event)
                            yield open_event
                            source_scroll_percent = min(92.0, 24.0 + (rank * 22.0))
                            source_scroll_event = ToolTraceEvent(
                                event_type="browser_scroll",
                                title=f"Scroll source page {rank}",
                                detail=f"Scanning source evidence ({int(round(source_scroll_percent))}%)",
                                data=_website_scene_payload(
                                    lane="source-scroll",
                                    primary_index=idx,
                                    secondary_index=rank,
                                    payload={
                                        "provider": "brave_search",
                                        "query": query_variant,
                                        "variant_index": idx,
                                        "result_rank": rank,
                                        "url": clicked_url,
                                        "source_url": clicked_url,
                                        "scroll_percent": float(source_scroll_percent),
                                        "scroll_direction": "down",
                                    },
                                ),
                            )
                            trace_events.append(source_scroll_event)
                            yield source_scroll_event
                            source_preview = ""
                            if rank - 1 < len(run_rows) and isinstance(run_rows[rank - 1], dict):
                                source_preview = str(
                                    run_rows[rank - 1].get("description")
                                    or run_rows[rank - 1].get("snippet")
                                    or ""
                                ).strip()
                            extract_event = ToolTraceEvent(
                                event_type="browser_extract",
                                title=f"Extract source evidence {rank}",
                                detail=_safe_snippet(source_preview or clicked_url, 140),
                                data=_website_scene_payload(
                                    lane="source-extract",
                                    primary_index=idx,
                                    secondary_index=rank,
                                    payload={
                                        "provider": "brave_search",
                                        "query": query_variant,
                                        "variant_index": idx,
                                        "result_rank": rank,
                                        "url": clicked_url,
                                        "source_url": clicked_url,
                                        "text_excerpt": _safe_snippet(source_preview, 260),
                                    },
                                ),
                            )
                            trace_events.append(extract_event)
                            yield extract_event

                fused_results = _fuse_search_results(search_runs, top_k=fused_top_k)
                payload = {"results": fused_results, "query": query, "provider": "brave_fused"}
                used_provider = "brave_search"
                ok = True
                fused_event = ToolTraceEvent(
                    event_type="retrieval_fused",
                    title="Fuse search runs",
                    detail=f"Reduced {sum(len(run.get('results') or []) for run in search_runs)} raw rows to {len(fused_results)} fused results",
                    data={
                        "query_variants": query_variants,
                        "result_count": len(fused_results),
                        "target_source_count": min_unique_sources,
                        "fused_top_k": fused_top_k,
                        "search_budget_requested": requested_search_budget,
                        "search_budget_effective": planned_result_budget,
                    },
                )
                trace_events.append(fused_event)
                yield fused_event
                trace_events.append(
                    ToolTraceEvent(
                        event_type="api_call_completed",
                        title="Brave Search API completed",
                        detail=f"Collected {len(fused_results)} fused result(s)",
                        data={
                            "provider": "brave_search",
                            "result_count": len(fused_results),
                            "provider_requested": requested_provider,
                        },
                    )
                )
                yield trace_events[-1]
            except Exception as exc:
                failure = _classify_provider_failure(exc)
                failure["provider"] = "brave_search"
                provider_failures.append(failure)
                trace_events.append(
                    ToolTraceEvent(
                        event_type="tool_failed",
                        title="Brave provider failed",
                        detail=f"{failure['reason']}: {failure['message']}",
                        data=failure,
                    )
                )
                yield trace_events[-1]
                ok = False

        # Optional fallback to Bing when Brave fails.
        if not ok and (requested_provider == "bing_search" or allow_provider_fallback):
            try:
                provider_attempted.append("bing_search")
                trace_events.append(
                    ToolTraceEvent(
                        event_type="api_call_started",
                        title="Call Bing Search API",
                        detail="Running fallback search query",
                        data={"provider": "bing_search"},
                    )
                )
                yield trace_events[-1]
                connector = get_connector_registry().build("bing_search", settings=context.settings)
                fallback_count = max(4, min(results_per_query, planned_result_budget))
                payload = connector.search_web(query=query_variants[0], count=fallback_count)
                used_provider = "bing_search"
                trace_events.append(
                    ToolTraceEvent(
                        event_type="tool_progress",
                        title=(
                            "Using Bing provider"
                            if requested_provider == "bing_search"
                            else "Brave unavailable, falling back to Bing"
                        ),
                        detail=(
                            "Using Bing as requested provider"
                            if requested_provider == "bing_search"
                            else "Using Bing as secondary provider"
                        ),
                        data={
                            "query": query_variants[0],
                            "provider": "bing_search",
                            "result_limit": fallback_count,
                        },
                    )
                )
                yield trace_events[-1]
                rows = []
                if isinstance(payload, dict):
                    web_pages = payload.get("webPages")
                    rows = web_pages.get("value") if isinstance(web_pages, dict) else []
                bing_query = str(query_variants[0] if query_variants else query).strip() or query
                bing_search_url = _search_results_url("bing_search", bing_query)
                if bing_search_url:
                    bing_nav_event = ToolTraceEvent(
                        event_type="browser_navigate",
                        title="Open Bing results",
                        detail=_safe_snippet(bing_query, 140),
                        data=_website_scene_payload(
                            lane="bing-results-open",
                            primary_index=1,
                            payload={
                                "provider": "bing_search",
                                "query": bing_query,
                                "variant_index": 1,
                                "url": bing_search_url,
                                "source_url": bing_search_url,
                                "render_quality": "live",
                            },
                        ),
                    )
                    trace_events.append(bing_nav_event)
                    yield bing_nav_event
                if isinstance(rows, list) and rows:
                    bing_hover_event = ToolTraceEvent(
                        event_type="browser_hover",
                        title="Hover Bing result cards",
                        detail="Reviewing ranked Bing results",
                        data=_website_scene_payload(
                            lane="bing-results-hover",
                            primary_index=1,
                            payload={
                                "provider": "bing_search",
                                "query": bing_query,
                                "variant_index": 1,
                                "url": bing_search_url,
                                "source_url": bing_search_url,
                            },
                        ),
                    )
                    trace_events.append(bing_hover_event)
                    yield bing_hover_event
                    bing_scroll_event = ToolTraceEvent(
                        event_type="browser_scroll",
                        title="Scroll Bing results",
                        detail="Scanning top Bing results",
                        data=_website_scene_payload(
                            lane="bing-results-scroll",
                            primary_index=1,
                            secondary_index=1,
                            payload={
                                "provider": "bing_search",
                                "query": bing_query,
                                "variant_index": 1,
                                "url": bing_search_url,
                                "source_url": bing_search_url,
                                "scroll_percent": 34.0,
                                "scroll_direction": "down",
                            },
                        ),
                    )
                    trace_events.append(bing_scroll_event)
                    yield bing_scroll_event
                    for rank, row in enumerate(rows[:max_live_clicks_per_query], start=1):
                        if not isinstance(row, dict):
                            continue
                        clicked_url = str(row.get("url") or "").strip()
                        if not clicked_url:
                            continue
                        host_label = _hostname_label(clicked_url)
                        click_event = ToolTraceEvent(
                            event_type="browser_click",
                            title=f"Click Bing result {rank}",
                            detail=(f"Open {host_label}" if host_label else f"Open result {rank}"),
                            data=_website_scene_payload(
                                lane="bing-result-click",
                                primary_index=1,
                                secondary_index=rank,
                                payload={
                                    "provider": "bing_search",
                                    "query": bing_query,
                                    "variant_index": 1,
                                    "result_rank": rank,
                                    "selector": f"result_rank_{rank}",
                                    "url": bing_search_url,
                                    "source_url": bing_search_url,
                                    "target_url": clicked_url,
                                },
                            ),
                        )
                        trace_events.append(click_event)
                        yield click_event
                        open_event = ToolTraceEvent(
                            event_type="web_result_opened",
                            title=f"Open Bing source {rank}",
                            detail=_safe_snippet(clicked_url, 140),
                            data=_website_scene_payload(
                                lane="bing-source-opened",
                                primary_index=1,
                                secondary_index=rank,
                                payload={
                                    "provider": "bing_search",
                                    "query": bing_query,
                                    "variant_index": 1,
                                    "result_rank": rank,
                                    "url": clicked_url,
                                    "source_url": clicked_url,
                                },
                            ),
                        )
                        trace_events.append(open_event)
                        yield open_event
                trace_events.append(
                    ToolTraceEvent(
                        event_type="api_call_completed",
                        title="Bing Search API completed",
                        detail=f"Collected {len(rows) if isinstance(rows, list) else 0} result(s)",
                        data={
                            "provider": "bing_search",
                            "provider_requested": requested_provider,
                        },
                    )
                )
                yield trace_events[-1]
                ok = True
            except Exception as exc:
                failure = _classify_provider_failure(exc)
                failure["provider"] = "bing_search"
                provider_failures.append(failure)
                trace_events.append(
                    ToolTraceEvent(
                        event_type="tool_failed",
                        title="Bing provider failed",
                        detail=f"{failure['reason']}: {failure['message']}",
                        data=failure,
                    )
                )
                yield trace_events[-1]
                ok = False

        if ok:
            trace_events.append(
                ToolTraceEvent(
                    event_type="browser_extract",
                    title="Parse search response",
                    detail="Decoded JSON payload from search provider",
                    data=_website_scene_payload(
                        lane="search-response-parse",
                        primary_index=1,
                        payload={
                            "provider": used_provider,
                            "provider_requested": requested_provider,
                        },
                    ),
                )
            )
            yield trace_events[-1]
        else:
            latest_failure = provider_failures[-1] if provider_failures else {}
            trace_events.append(
                ToolTraceEvent(
                    event_type="tool_failed",
                    title="Search provider unavailable",
                    detail=(
                        f"No data returned from external provider. "
                        f"{str(latest_failure.get('reason') or '').replace('_', ' ')}"
                    ).strip(),
                    data={
                        "provider_requested": requested_provider,
                        "provider_fallback_enabled": allow_provider_fallback,
                        "provider_attempted": provider_attempted[:4],
                        "provider_failures": provider_failures[:4],
                    },
                )
            )
            yield trace_events[-1]

        if ok:
            if used_provider == "brave_search":
                rows = payload.get("results") if isinstance(payload, dict) else []
                results = rows if isinstance(rows, list) else []
                max_source_rows = max(8, min(fused_top_k, 220))
                for item in results[:max_source_rows]:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("title") or item.get("url") or "Web result").strip()
                    snippet = str(item.get("description") or item.get("snippet") or "").strip()
                    url = str(item.get("url") or "").strip()
                    excerpt = _safe_snippet(snippet or name or url, 220)
                    if len(bullets) < 24:
                        bullets.append(f"- {name}: {_safe_snippet(snippet or name)}")
                    try:
                        rrf_score = float(item.get("rrf_score") or 0.0)
                    except Exception:
                        rrf_score = 0.0
                    sources.append(
                        AgentSource(
                            source_type="web",
                            label=name,
                            url=url or None,
                            score=max(0.5, min(0.95, 0.68 + (rrf_score * 120))),
                            metadata={
                                "provider": "brave_search",
                                "excerpt": excerpt,
                                "extract": excerpt,
                                "rrf_score": rrf_score,
                            },
                        )
                    )
                quality_event = ToolTraceEvent(
                    event_type="retrieval_quality_assessed",
                    title="Assess retrieval quality",
                    detail=f"Fused retrieval produced {len(results)} result(s); {len(sources)} source(s) selected",
                    data={
                        "provider": "brave_search",
                        "result_count": len(results),
                        "source_count": len(sources),
                        "target_source_count": min_unique_sources,
                        "coverage_ok": len(sources) >= min_unique_sources,
                        "query_variants": query_variants,
                    },
                )
                trace_events.append(quality_event)
                yield quality_event
            elif used_provider == "bing_search":
                web_pages = payload.get("webPages") if isinstance(payload, dict) else None
                results = web_pages.get("value") if isinstance(web_pages, dict) else []
                max_source_rows = max(8, min(fused_top_k, 140))
                for item in (results or [])[:max_source_rows]:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name") or "Web result").strip()
                    snippet = str(item.get("snippet") or "").strip()
                    url = str(item.get("url") or "").strip()
                    excerpt = _safe_snippet(snippet or name or url, 220)
                    if len(bullets) < 24:
                        bullets.append(f"- {name}: {_safe_snippet(snippet or name)}")
                    sources.append(
                        AgentSource(
                            source_type="web",
                            label=name,
                            url=url or None,
                            score=0.74,
                            metadata={
                                "provider": "bing_search",
                                "excerpt": excerpt,
                                "extract": excerpt,
                            },
                        )
                    )
        else:
            bullets.append(
                "- No web search data available. Configure `BRAVE_SEARCH_API_KEY` (required for Brave mode)."
            )

        if bullets:
            highlight_terms = []
            for source in sources[:6]:
                label = str(source.label or "").strip()
                if label:
                    highlight_terms.extend(re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", label))
            dedup_terms = []
            for term in highlight_terms:
                lowered = term.lower()
                if lowered not in dedup_terms:
                    dedup_terms.append(lowered)
                if len(dedup_terms) >= 8:
                    break
            if dedup_terms:
                highlight_event = ToolTraceEvent(
                    event_type="browser_keyword_highlight",
                    title="Highlight search keywords",
                    detail=", ".join(dedup_terms[:6]),
                    data={"keywords": dedup_terms[:8]},
                )
                trace_events.append(highlight_event)
                yield highlight_event
            snippet_text = _safe_snippet(" | ".join(bullets), 320)
            if snippet_text:
                copy_event = ToolTraceEvent(
                    event_type="clipboard_copy",
                    title="Copy web snippets",
                    detail=snippet_text,
                    data={"clipboard_text": snippet_text},
                )
                trace_events.append(copy_event)
                yield copy_event

        unique_urls = list(
            dict.fromkeys(
                [str(source.url or "").strip() for source in sources if str(source.url or "").strip()]
            )
        )
        if len(unique_urls) < min_unique_sources:
            shortfall_event = ToolTraceEvent(
                event_type="tool_progress",
                title="Research coverage shortfall detected",
                detail=(
                    f"Collected {len(unique_urls)} unique sources; target is {min_unique_sources}. "
                    "Continue with additional targeted queries."
                ),
                data={
                    "source_count": len(unique_urls),
                    "target_source_count": min_unique_sources,
                    "coverage_ok": False,
                },
            )
            trace_events.append(shortfall_event)
            yield shortfall_event

        content = "\n".join(bullets)
        summary = (
            f"Collected {len(sources)} web sources ({len(unique_urls)} unique URLs) "
            f"using {used_provider}: {query}"
        )
        if sources:
            context.settings["__latest_web_sources"] = [
                source.to_dict()
                for source in sources[:200]
            ]
            context.settings["__latest_web_query"] = query
            context.settings["__latest_web_provider"] = used_provider
            context.settings["__latest_web_source_count"] = len(unique_urls)
            context.settings["__latest_web_source_target"] = min_unique_sources
            context.settings["__latest_research_depth_tier"] = depth_tier
        next_steps = [
            "Validate top 2 sources against internal company data.",
            "Convert findings into a competitor/market briefing.",
        ]
        if len(unique_urls) < min_unique_sources:
            next_steps.insert(
                0,
                f"Run another research pass to reach at least {min_unique_sources} unique sources.",
            )
        return ToolExecutionResult(
            summary=summary,
            content=content,
            data={
                "query": query,
                "query_variants": query_variants,
                "max_query_variants": max_query_variants,
                "results_per_query": results_per_query,
                "search_budget_requested": requested_search_budget,
                "search_budget_effective": planned_result_budget,
                "fused_top_k": fused_top_k,
                "research_depth_tier": depth_tier,
                "provider": used_provider,
                "provider_requested": requested_provider,
                "provider_fallback_enabled": allow_provider_fallback,
                "provider_attempted": provider_attempted[:4],
                "provider_failures": provider_failures[:4],
                "source_count": len(sources),
                "unique_source_count": len(unique_urls),
                "min_unique_sources": min_unique_sources,
                "coverage_ok": len(unique_urls) >= min_unique_sources,
                "items": [source.to_dict() for source in sources],
            },
            sources=sources,
            next_steps=next_steps,
            events=trace_events,
        )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        stream = self.execute_stream(context=context, prompt=prompt, params=params)
        trace_events: list[ToolTraceEvent] = []
        while True:
            try:
                trace_events.append(next(stream))
            except StopIteration as stop:
                result = stop.value
                break
        result.events = trace_events
        return result


class CompetitorProfileTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="marketing.competitor_profile",
        action_class="draft",
        risk_level="low",
        required_permissions=["analysis.write"],
        execution_policy="auto_execute",
        description="Build a concise competitor profile from provided context.",
    )

    _COMPETITOR_RE = re.compile(r"\b(versus|vs\.?|against)\s+([A-Za-z0-9 ._-]+)", re.IGNORECASE)

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        competitor = str(params.get("competitor") or "").strip()
        if not competitor:
            match = self._COMPETITOR_RE.search(prompt)
            if match:
                competitor = match.group(2).strip()
        if not competitor:
            competitor = "Competitor"

        positioning = params.get("positioning") or "Positioning is not yet validated."
        pricing = params.get("pricing") or "Pricing signals need verified source data."
        channels = params.get("channels") or "Channel mix unknown."

        content = (
            f"### Competitor Profile: {html.escape(competitor)}\n"
            f"- Positioning: {positioning}\n"
            f"- Pricing signals: {pricing}\n"
            f"- Distribution/marketing channels: {channels}\n"
            "- Key gap to exploit: emphasize measurable outcomes + faster execution."
        )
        return ToolExecutionResult(
            summary=f"Drafted competitor profile for {competitor}.",
            content=content,
            data={"competitor": competitor},
            sources=[],
            next_steps=[
                "Attach at least 3 verifiable sources for pricing and claims.",
                "Run messaging A/B draft recommendations.",
            ],
            events=[
                ToolTraceEvent(
                    event_type="tool_progress",
                    title="Assemble competitor profile",
                    detail=f"Structured profile generated for {competitor}",
                    data={"competitor": competitor},
                )
            ],
        )
