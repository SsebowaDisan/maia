from __future__ import annotations

from typing import Any, Callable

from api.services.agent.models import AgentSource
from api.services.agent.tools.base import ToolExecutionContext, ToolTraceEvent
from api.services.agent.tools.research_helpers import (
    classify_provider_failure as _classify_provider_failure,
    safe_snippet as _safe_snippet,
)
from api.services.agent.tools.research_web_helpers import (
    _apply_domain_scope,
    _hostname_label,
    _website_scene_payload,
    _search_results_url,
)


def _bing_fallback_configured(registry: Any, context: ToolExecutionContext) -> bool:
    try:
        connector = registry.build("bing_search", settings=context.settings)
        health = connector.health_check()
        return bool(getattr(health, "ok", False))
    except Exception:
        return False


def run_bing_provider_and_materialize_stage(
    *,
    context: ToolExecutionContext,
    requested_provider: str,
    allow_provider_fallback: bool,
    results_per_query: int,
    planned_result_budget: int,
    query_variants: list[str],
    query: str,
    max_live_clicks_per_query: int,
    fused_top_k: int,
    min_unique_sources: int,
    domain_scope_hosts: list[str],
    domain_scope_mode: str,
    trace_events: list[ToolTraceEvent],
    sources: list[AgentSource],
    bullets: list[str],
    state: dict[str, Any],
    get_connector_registry_fn: Callable[..., Any],
):
    get_connector_registry = get_connector_registry_fn
    payload: dict[str, Any] = state.get("payload") if isinstance(state.get("payload"), dict) else {}
    used_provider = str(state.get("used_provider") or requested_provider)
    ok = bool(state.get("ok"))
    provider_failures = state.get("provider_failures")
    if not isinstance(provider_failures, list):
        provider_failures = []
    provider_attempted = state.get("provider_attempted")
    if not isinstance(provider_attempted, list):
        provider_attempted = []
    domain_scope_filtered_out = int(state.get("domain_scope_filtered_out") or 0)
    provider_fallback_skipped = bool(state.get("provider_fallback_skipped"))
    fallback_possible = requested_provider == "bing_search" or (
        allow_provider_fallback and _bing_fallback_configured(get_connector_registry(), context)
    )
    if not ok and fallback_possible:
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
                    data=_website_scene_payload(
                        lane="bing-provider-select",
                        primary_index=1,
                        payload={
                            "query": query_variants[0],
                            "provider": "bing_search",
                            "result_limit": fallback_count,
                        },
                    ),
                )
            )
            yield trace_events[-1]
            rows = []
            if isinstance(payload, dict):
                web_pages = payload.get("webPages")
                rows = web_pages.get("value") if isinstance(web_pages, dict) else []
            scoped_rows, dropped_count = _apply_domain_scope(
                rows=[row for row in rows if isinstance(row, dict)],
                domain_scope_hosts=domain_scope_hosts,
                domain_scope_mode=domain_scope_mode,
            )
            domain_scope_filtered_out += int(dropped_count)
            rows = scoped_rows
            if isinstance(payload, dict):
                web_pages = payload.get("webPages")
                if isinstance(web_pages, dict):
                    web_pages["value"] = rows
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
        fallback_skipped = (
            allow_provider_fallback
            and requested_provider != "bing_search"
            and "bing_search" not in provider_attempted
            and not _bing_fallback_configured(get_connector_registry(), context)
        )
        provider_fallback_skipped = provider_fallback_skipped or fallback_skipped
        trace_events.append(
            ToolTraceEvent(
                event_type="tool_failed",
                title="Search provider unavailable",
                detail=(
                    f"No data returned from external provider. "
                    f"{str(latest_failure.get('reason') or '').replace('_', ' ')}"
                    + (
                        ". Bing fallback skipped because AZURE_BING_API_KEY is not configured"
                        if fallback_skipped
                        else ""
                    )
                ).strip(),
                data={
                    "provider_requested": requested_provider,
                    "provider_fallback_enabled": allow_provider_fallback,
                    "provider_attempted": provider_attempted[:4],
                    "provider_failures": provider_failures[:4],
                    "provider_fallback_skipped": fallback_skipped,
                },
            )
        )
        yield trace_events[-1]

    if ok:
        if used_provider == "brave_search":
            rows = payload.get("results") if isinstance(payload, dict) else []
            results = rows if isinstance(rows, list) else []
            max_source_rows = max(8, min(fused_top_k, 600))
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
                    "domain_scope_hosts": domain_scope_hosts[:6],
                    "domain_scope_mode": domain_scope_mode,
                    "domain_scope_filtered_out": int(domain_scope_filtered_out),
                },
            )
            trace_events.append(quality_event)
            yield quality_event
        elif used_provider == "bing_search":
            web_pages = payload.get("webPages") if isinstance(payload, dict) else None
            results = web_pages.get("value") if isinstance(web_pages, dict) else []
            max_source_rows = max(8, min(fused_top_k, 600))
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

    state["payload"] = payload
    state["used_provider"] = used_provider
    state["ok"] = ok
    state["provider_failures"] = provider_failures
    state["provider_attempted"] = provider_attempted
    state["domain_scope_filtered_out"] = int(domain_scope_filtered_out)
    state["provider_fallback_skipped"] = provider_fallback_skipped
