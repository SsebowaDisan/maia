from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from api.services.agent.tools.base import ToolExecutionContext, ToolTraceEvent
from api.services.agent.tools.research_helpers import (
    classify_provider_failure as _classify_provider_failure,
    fuse_search_results as _fuse_search_results,
    safe_snippet as _safe_snippet,
)
from api.services.agent.tools.research_web_helpers import (
    _apply_domain_scope,
    _hostname_label,
    _search_results_url,
    _website_scene_payload,
)


def _stream_source_page_via_computer_use(
    *,
    context: ToolExecutionContext,
    clicked_url: str,
    query_variant: str,
    query: str,
    idx: int,
    rank: int,
    trace_events: list[ToolTraceEvent],
    get_connector_registry_fn: Callable[..., Any],
):
    try:
        connector = get_connector_registry_fn().build("computer_use_browser", settings=context.settings)
        health = connector.health_check()
        if not bool(getattr(health, "ok", False)):
            return None
        stream = connector.browse_live_stream(
            url=clicked_url,
            max_pages=1,
            max_scroll_steps=1,
            follow_same_domain_links=False,
            highlight_query=query,
            prefer_direct_capture=True,
        )
        while True:
            try:
                raw_event = next(stream)
            except StopIteration as stop:
                return stop.value if isinstance(stop.value, dict) else {}
            if not isinstance(raw_event, dict):
                continue
            event_type = str(raw_event.get("event_type") or "").strip() or "browser_event"
            title = str(raw_event.get("title") or event_type.replace("_", " ")).strip()
            detail = str(raw_event.get("detail") or "").strip()
            raw_data = raw_event.get("data") if isinstance(raw_event.get("data"), dict) else {}
            data = {
                **raw_data,
                "provider": "computer_use_browser",
                "query": query_variant,
                "query_variant": query_variant,
                "variant_index": idx,
                "result_rank": rank,
                "url": str(raw_data.get("url") or clicked_url).strip() or clicked_url,
                "source_url": str(raw_data.get("source_url") or raw_data.get("url") or clicked_url).strip() or clicked_url,
            }
            event = ToolTraceEvent(
                event_type=event_type,
                title=title,
                detail=detail,
                data=data,
                snapshot_ref=str(raw_event.get("snapshot_ref") or "").strip() or None,
            )
            trace_events.append(event)
            yield event
    except Exception:
        return None


def run_brave_provider_stage(
    *,
    context: ToolExecutionContext,
    requested_provider: str,
    search_plan: list[tuple[str, int]],
    planned_result_budget: int,
    requested_search_budget: int,
    query_variants: list[str],
    max_live_queries: int,
    max_live_clicks_per_query: int,
    domain_scope_hosts: list[str],
    domain_scope_mode: str,
    min_unique_sources: int,
    fused_top_k: int,
    query: str,
    trace_events: list[ToolTraceEvent],
    state: dict[str, Any],
    get_connector_registry_fn: Callable[..., Any],
):
    get_connector_registry = get_connector_registry_fn
    payload: dict[str, Any] = state.get("payload") if isinstance(state.get("payload"), dict) else {}
    used_provider = str(state.get("used_provider") or requested_provider)
    ok = bool(state.get("ok"))
    search_runs = state.get("search_runs")
    if not isinstance(search_runs, list):
        search_runs = []
    provider_failures = state.get("provider_failures")
    if not isinstance(provider_failures, list):
        provider_failures = []
    provider_attempted = state.get("provider_attempted")
    if not isinstance(provider_attempted, list):
        provider_attempted = []
    domain_scope_filtered_out = int(state.get("domain_scope_filtered_out") or 0)
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
            brave_settings = context.settings
            scheduled_queries: list[tuple[int, str, int, str]] = []
            for idx, (query_variant, per_query_limit) in enumerate(search_plan, start=1):
                search_url = _search_results_url("brave_search", query_variant)
                scheduled_queries.append((idx, query_variant, per_query_limit, search_url))
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
            def _run_search_variant(
                variant_query: str,
                variant_limit: int,
            ) -> dict[str, Any]:
                brave = get_connector_registry().build("brave_search", settings=brave_settings)
                return brave.web_search(query=variant_query, count=variant_limit)

            max_workers = max(1, min(len(scheduled_queries), 4))
            future_map = {}
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for idx, query_variant, per_query_limit, search_url in scheduled_queries:
                    future = executor.submit(_run_search_variant, query_variant, per_query_limit)
                    future_map[future] = (idx, query_variant, per_query_limit, search_url)

                for future in as_completed(future_map):
                    idx, query_variant, per_query_limit, search_url = future_map[future]
                    run_payload = future.result()
                    if not isinstance(run_payload, dict):
                        continue
                    run_payload["query_variant"] = query_variant
                    run_payload["result_limit"] = per_query_limit
                    run_rows = run_payload.get("results") if isinstance(run_payload.get("results"), list) else []
                    scoped_rows, dropped_count = _apply_domain_scope(
                        rows=[row for row in run_rows if isinstance(row, dict)],
                        domain_scope_hosts=domain_scope_hosts,
                        domain_scope_mode=domain_scope_mode,
                    )
                    domain_scope_filtered_out += int(dropped_count)
                    scoped_payload = dict(run_payload)
                    scoped_payload["results"] = scoped_rows
                    search_runs.append(scoped_payload)
                    run_urls = [
                        str(item.get("url") or "")
                        for item in scoped_rows
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
                            "domain_scope_filtered_out": int(dropped_count),
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
                        if len(scoped_rows) >= 8:
                            scroll_count = 3
                        elif len(scoped_rows) >= 4:
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
                            computer_use_result = yield from _stream_source_page_via_computer_use(
                                context=context,
                                clicked_url=clicked_url,
                                query_variant=query_variant,
                                query=query,
                                idx=idx,
                                rank=rank,
                                trace_events=trace_events,
                                get_connector_registry_fn=get_connector_registry,
                            )
                            if isinstance(computer_use_result, dict) and (
                                str(computer_use_result.get("text_excerpt") or "").strip()
                                or str(computer_use_result.get("screenshot_path") or "").strip()
                            ):
                                continue

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
                            if rank - 1 < len(scoped_rows) and isinstance(scoped_rows[rank - 1], dict):
                                source_preview = str(
                                    scoped_rows[rank - 1].get("description")
                                    or scoped_rows[rank - 1].get("snippet")
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
                    "domain_scope_hosts": domain_scope_hosts[:6],
                    "domain_scope_mode": domain_scope_mode,
                    "domain_scope_filtered_out": int(domain_scope_filtered_out),
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

    state["payload"] = payload
    state["used_provider"] = used_provider
    state["ok"] = ok
    state["search_runs"] = search_runs
    state["provider_failures"] = provider_failures
    state["provider_attempted"] = provider_attempted
    state["domain_scope_filtered_out"] = int(domain_scope_filtered_out)
