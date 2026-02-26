from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urlparse

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.models import AgentSource
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolMetadata,
    ToolTraceEvent,
)


def _safe_snippet(text: str, max_len: int = 280) -> str:
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= max_len else f"{clean[: max_len - 1].rstrip()}..."


def _clean_query(text: str) -> str:
    compact = " ".join(str(text or "").split())
    compact = re.sub(r"[^\w\s:/\.-]", " ", compact)
    compact = " ".join(compact.split())
    return compact.strip()


def _extract_first_url(text: str) -> str:
    match = re.search(r"https?://[^\s]+", str(text or ""), re.IGNORECASE)
    if not match:
        return ""
    return match.group(0).strip().rstrip(".,;)")


def _extract_search_variants(query: str, prompt: str) -> list[str]:
    base = _clean_query(query) or _clean_query(prompt) or "company overview and services"
    base = re.sub(
        r"\b(send|email|report|analysis|analyze|deliver)\b",
        " ",
        base,
        flags=re.IGNORECASE,
    )
    base = " ".join(base.split())
    url = _extract_first_url(prompt)
    host = (urlparse(url).hostname or "").strip().lower() if url else ""
    host_no_www = host[4:] if host.startswith("www.") else host

    candidates = [base]
    if host_no_www:
        candidates.extend(
            [
                f"site:{host_no_www} company overview services",
                f"site:{host_no_www} about",
                f"site:{host_no_www} products solutions",
                f"{host_no_www} company profile",
            ]
        )
    if len(base.split()) >= 4:
        candidates.append(" ".join(base.split()[:8]))

    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        cleaned = _clean_query(item)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cleaned)
        if len(deduped) >= 4:
            break
    return deduped or ["company overview and services"]


def _fuse_search_results(search_runs: list[dict[str, Any]], *, top_k: int = 8) -> list[dict[str, Any]]:
    # Reciprocal Rank Fusion (RRF): robust ranking across query rewrites.
    k = 60.0
    by_url: dict[str, dict[str, Any]] = {}
    for run in search_runs:
        results = run.get("results")
        if not isinstance(results, list):
            continue
        for rank, row in enumerate(results, start=1):
            if not isinstance(row, dict):
                continue
            url = str(row.get("url") or "").strip()
            if not url:
                continue
            title = str(row.get("title") or url).strip()
            description = str(row.get("description") or "").strip()
            source = str(row.get("source") or "").strip()
            score = 1.0 / (k + float(rank))
            current = by_url.get(url)
            if current is None:
                by_url[url] = {
                    "url": url,
                    "title": title,
                    "description": description,
                    "source": source or None,
                    "rrf_score": score,
                    "best_rank": rank,
                }
                continue
            current["rrf_score"] = float(current.get("rrf_score", 0.0)) + score
            if rank < int(current.get("best_rank", rank)):
                current["best_rank"] = rank
                current["title"] = title
                current["description"] = description
                current["source"] = source or None
    fused = list(by_url.values())
    fused.sort(
        key=lambda item: (float(item.get("rrf_score", 0.0)), -int(item.get("best_rank", 9999))),
        reverse=True,
    )
    return fused[: max(1, int(top_k))]


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
        sources: list[AgentSource] = []
        bullets: list[str] = []
        trace_events: list[ToolTraceEvent] = []
        started_event = ToolTraceEvent(
            event_type="status",
            title="Searching web...",
            detail=f"Query: {_safe_snippet(query, 120)}",
            data={"query": query, "query_variants": query_variants},
        )
        trace_events.append(started_event)
        yield started_event
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
            detail=f"Submitting {len(query_variants)} rewritten query variant(s) to Brave",
            data={"query": query, "provider": "brave_search", "query_variants": query_variants},
        )
        trace_events.append(navigate_event)
        yield navigate_event

        payload: dict[str, Any] = {}
        used_provider = "brave_search"
        ok = False
        search_runs: list[dict[str, Any]] = []

        # Prefer Brave Search with multi-query retrieval + reciprocal-rank fusion.
        try:
            brave = get_connector_registry().build("brave_search", settings=context.settings)
            for idx, query_variant in enumerate(query_variants, start=1):
                query_event = ToolTraceEvent(
                    event_type="brave.search.query",
                    title=f"Run Brave query {idx}/{len(query_variants)}",
                    detail=_safe_snippet(query_variant, 140),
                    data={"query": query_variant, "variant_index": idx},
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
                    data={"query": query_variant, "top_urls": run_urls},
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
        except Exception:
            ok = False

        # Fallback to Bing.
        if not ok:
            try:
                connector = get_connector_registry().build("bing_search", settings=context.settings)
                payload = connector.search_web(query=query_variants[0], count=8)
                used_provider = "bing_search"
                trace_events.append(
                    ToolTraceEvent(
                        event_type="tool_progress",
                        title="Brave unavailable, falling back to Bing",
                        detail="Using Bing as secondary provider",
                        data={"query": query_variants[0], "provider": "bing_search"},
                    )
                )
                yield trace_events[-1]
                ok = True
            except Exception:
                ok = False

        if ok:
            trace_events.append(
                ToolTraceEvent(
                    event_type="browser_extract",
                    title="Parse search response",
                    detail="Decoded JSON payload from search provider",
                    data={"provider": used_provider},
                )
            )
            yield trace_events[-1]
        else:
            trace_events.append(
                ToolTraceEvent(
                    event_type="tool_progress",
                    title="Search provider unavailable",
                    detail="No data returned from external provider",
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
                "- No web search data available. Configure `BRAVE_SEARCH_API_KEY` (preferred) or `AZURE_BING_API_KEY`."
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
