from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import quote_plus, urlencode
from urllib.request import urlopen

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
        sources: list[AgentSource] = []
        bullets: list[str] = []
        trace_events: list[ToolTraceEvent] = []
        started_event = ToolTraceEvent(
            event_type="status",
            title="Searching web...",
            detail=f"Query: {_safe_snippet(query, 120)}",
            data={"query": query},
        )
        trace_events.append(started_event)
        yield started_event
        navigate_event = ToolTraceEvent(
            event_type="browser_navigate",
            title="Open search provider",
            detail=f"Submitting query: {_safe_snippet(query, 96)}",
            data={"query": query},
        )
        trace_events.append(navigate_event)
        yield navigate_event

        payload: dict[str, Any] = {}
        used_provider = "duckduckgo"
        ok = False

        # Prefer Brave Search.
        try:
            brave = get_connector_registry().build("brave_search", settings=context.settings)
            payload = brave.web_search(query=query, count=8)
            used_provider = "brave_search"
            ok = True
            brave_rows = payload.get("results") if isinstance(payload, dict) else []
            brave_results = brave_rows if isinstance(brave_rows, list) else []
            top_urls = [
                str(item.get("url") or "")
                for item in brave_results
                if isinstance(item, dict)
            ][:5]
            trace_events.append(
                ToolTraceEvent(
                    event_type="brave.search.query",
                    title="Run Brave web search",
                    detail=_safe_snippet(query, 120),
                    data={"query": query},
                )
            )
            yield trace_events[-1]
            trace_events.append(
                ToolTraceEvent(
                    event_type="brave.search.results",
                    title="Brave returned search results",
                    detail=f"Top {len(top_urls)} URL(s) captured",
                    data={"top_urls": top_urls},
                )
            )
            yield trace_events[-1]
        except Exception:
            ok = False

        # Fallback to Bing.
        if not ok:
            try:
                connector = get_connector_registry().build("bing_search", settings=context.settings)
                payload = connector.search_web(query=query, count=8)
                used_provider = "bing_search"
                ok = True
            except Exception:
                ok = False

        # Fallback to DuckDuckGo.
        if not ok:
            ddg_url = "https://api.duckduckgo.com/"
            ddg_params = {
                "q": query,
                "format": "json",
                "no_html": "1",
                "no_redirect": "1",
            }
            query_url = f"{ddg_url}?{urlencode(ddg_params)}"
            try:
                with urlopen(query_url, timeout=20) as response:
                    body = response.read()
                payload = json.loads(body.decode("utf-8"))
                used_provider = "duckduckgo"
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
                            score=0.77,
                            metadata={"provider": "brave_search"},
                        )
                    )
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
                            metadata={"provider": "bing_search"},
                        )
                    )
            else:
                abstract = str(payload.get("AbstractText") or "").strip()
                abstract_url = str(payload.get("AbstractURL") or "").strip()
                heading = str(payload.get("Heading") or query)
                if abstract:
                    bullets.append(f"- {heading}: {_safe_snippet(abstract)}")
                    sources.append(
                        AgentSource(
                            source_type="web",
                            label=heading,
                            url=abstract_url or None,
                            score=0.72,
                            metadata={"provider": "duckduckgo"},
                        )
                    )
                related = payload.get("RelatedTopics") or []
                for topic in related[:4]:
                    if not isinstance(topic, dict):
                        continue
                    text = str(topic.get("Text") or "").strip()
                    topic_url = str(topic.get("FirstURL") or "").strip()
                    if not text:
                        continue
                    bullets.append(f"- {_safe_snippet(text)}")
                    sources.append(
                        AgentSource(
                            source_type="web",
                            label=_safe_snippet(text, 80),
                            url=topic_url or None,
                            score=0.6,
                            metadata={"provider": "duckduckgo_related"},
                        )
                    )
        else:
            bullets.append("- Search provider returned no data. Check network or query phrasing.")

        if not bullets:
            encoded = quote_plus(query)
            bullets.append(f"- No direct snippet found. Run manual search: https://duckduckgo.com/?q={encoded}")
        else:
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
        summary = f"Collected {len(sources)} web sources for query: {query}"
        next_steps = [
            "Validate top 2 sources against internal company data.",
            "Convert findings into a competitor/market briefing.",
        ]
        return ToolExecutionResult(
            summary=summary,
            content=content,
            data={"query": query, "items": [source.to_dict() for source in sources]},
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
