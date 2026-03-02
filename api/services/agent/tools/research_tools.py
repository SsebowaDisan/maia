from __future__ import annotations

import html
import re
from typing import Any

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
        query_variants = _extract_search_variants(query=query, prompt=prompt)
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
            data={"query": query, "provider": requested_provider, "query_variants": query_variants},
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
                        detail=f"Running {len(query_variants)} query variant(s)",
                        data={"provider": "brave_search"},
                    )
                )
                yield trace_events[-1]
                brave = get_connector_registry().build("brave_search", settings=context.settings)
                for idx, query_variant in enumerate(query_variants, start=1):
                    query_event = ToolTraceEvent(
                        event_type="brave.search.query",
                        title=f"Run Brave query {idx}/{len(query_variants)}",
                        detail=_safe_snippet(query_variant, 140),
                        data={"query": query_variant, "variant_index": idx, "provider": "brave_search"},
                    )
                    trace_events.append(query_event)
                    yield query_event
                    run_payload = brave.web_search(query=query_variant, count=6)
                    if not isinstance(run_payload, dict):
                        continue
                    run_payload["query_variant"] = query_variant
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
                        detail=f"Captured {len(run_urls)} URL(s)",
                        data={"query": query_variant, "top_urls": run_urls, "provider": "brave_search"},
                    )
                    trace_events.append(result_event)
                    yield result_event

                fused_results = _fuse_search_results(search_runs, top_k=8)
                payload = {"results": fused_results, "query": query, "provider": "brave_fused"}
                used_provider = "brave_search"
                ok = True
                fused_event = ToolTraceEvent(
                    event_type="retrieval_fused",
                    title="Fuse search runs",
                    detail=f"Reduced {sum(len(run.get('results') or []) for run in search_runs)} raw rows to {len(fused_results)} fused results",
                    data={"query_variants": query_variants, "result_count": len(fused_results)},
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
                payload = connector.search_web(query=query_variants[0], count=8)
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
                        data={"query": query_variants[0], "provider": "bing_search"},
                    )
                )
                yield trace_events[-1]
                rows = []
                if isinstance(payload, dict):
                    web_pages = payload.get("webPages")
                    rows = web_pages.get("value") if isinstance(web_pages, dict) else []
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
                    data={"provider": used_provider, "provider_requested": requested_provider},
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
                for item in results[:6]:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("title") or item.get("url") or "Web result").strip()
                    snippet = str(item.get("description") or "").strip()
                    url = str(item.get("url") or "").strip()
                    bullets.append(f"- {name}: {_safe_snippet(snippet)}")
                    sources.append(
                        AgentSource(
                            source_type="web",
                            label=name,
                            url=url or None,
                            score=0.79,
                            metadata={
                                "provider": "brave_search",
                                "excerpt": _safe_snippet(snippet, 220),
                            },
                        )
                    )
                quality_event = ToolTraceEvent(
                    event_type="retrieval_quality_assessed",
                    title="Assess retrieval quality",
                    detail=f"Fused retrieval produced {len(results)} high-confidence result(s)",
                    data={
                        "provider": "brave_search",
                        "result_count": len(results),
                        "query_variants": query_variants,
                    },
                )
                trace_events.append(quality_event)
                yield quality_event
            elif used_provider == "bing_search":
                web_pages = payload.get("webPages") if isinstance(payload, dict) else None
                results = web_pages.get("value") if isinstance(web_pages, dict) else []
                for item in (results or [])[:6]:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name") or "Web result").strip()
                    snippet = str(item.get("snippet") or "").strip()
                    url = str(item.get("url") or "").strip()
                    bullets.append(f"- {name}: {_safe_snippet(snippet)}")
                    sources.append(
                        AgentSource(
                            source_type="web",
                            label=name,
                            url=url or None,
                            score=0.74,
                            metadata={
                                "provider": "bing_search",
                                "excerpt": _safe_snippet(snippet, 220),
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

        content = "\n".join(bullets)
        summary = f"Collected {len(sources)} web sources for query using {used_provider}: {query}"
        next_steps = [
            "Validate top 2 sources against internal company data.",
            "Convert findings into a competitor/market briefing.",
        ]
        return ToolExecutionResult(
            summary=summary,
            content=content,
            data={
                "query": query,
                "query_variants": query_variants,
                "provider": used_provider,
                "provider_requested": requested_provider,
                "provider_fallback_enabled": allow_provider_fallback,
                "provider_attempted": provider_attempted[:4],
                "provider_failures": provider_failures[:4],
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
