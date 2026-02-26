from __future__ import annotations

from collections import Counter
import re
from typing import Any, Generator

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.models import AgentSource
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionError,
    ToolExecutionResult,
    ToolTraceEvent,
    ToolMetadata,
)

URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
STOPWORDS = {
    "about",
    "after",
    "also",
    "because",
    "before",
    "being",
    "between",
    "company",
    "could",
    "from",
    "have",
    "into",
    "more",
    "most",
    "other",
    "page",
    "that",
    "their",
    "there",
    "these",
    "this",
    "those",
    "using",
    "with",
    "your",
    "http",
    "https",
    "www",
}


def _truthy(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _extract_keywords(text: str, *, limit: int = 12) -> list[str]:
    words = [match.group(0).lower() for match in WORD_RE.finditer(str(text or ""))]
    filtered = [word for word in words if word not in STOPWORDS and len(word) >= 4]
    counts = Counter(filtered)
    ranked = [word for word, _ in counts.most_common(max(1, int(limit)))]
    return ranked


def _excerpt(text: str, *, limit: int = 360) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: max(1, limit - 1)].rstrip()}..."


def _normalize_highlight_color(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text == "green":
        return "green"
    return "yellow"


class PlaywrightInspectTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="browser.playwright.inspect",
        action_class="read",
        risk_level="medium",
        required_permissions=["browser.read"],
        execution_policy="auto_execute",
        description="Open a website using Playwright and capture visible evidence.",
    )

    def _resolve_url(
        self,
        *,
        prompt: str,
        params: dict[str, Any],
    ) -> str:
        url = str(params.get("url") or "").strip()
        if not url:
            match = URL_RE.search(prompt)
            url = match.group(0) if match else ""
        return url.strip()

    def execute_stream(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> Generator[ToolTraceEvent, None, ToolExecutionResult]:
        url = self._resolve_url(prompt=prompt, params=params)
        if not url:
            raise ToolExecutionError("Provide a valid URL for browser inspection.")
        auto_accept_cookies = _truthy(params.get("auto_accept_cookies"), default=True)
        highlight_color = _normalize_highlight_color(
            params.get("highlight_color") or context.settings.get("__highlight_color")
        )

        connector = get_connector_registry().build("playwright_browser", settings=context.settings)
        trace_events: list[ToolTraceEvent] = []
        copied_snippets: list[str] = []
        highlighted_keywords: list[str] = []
        stream = connector.browse_live_stream(
            url=url,
            auto_accept_cookies=auto_accept_cookies,
            highlight_color=highlight_color,
        )
        while True:
            try:
                payload = next(stream)
            except StopIteration as stop:
                capture = stop.value
                break
            event = ToolTraceEvent(
                event_type=str(payload.get("event_type") or "browser_progress"),
                title=str(payload.get("title") or "Browser activity"),
                detail=str(payload.get("detail") or ""),
                data=dict(payload.get("data") or {}),
                snapshot_ref=str(payload.get("snapshot_ref") or "") or None,
            )
            trace_events.append(event)
            yield event
            if event.event_type == "browser_keyword_highlight":
                keyword_rows = event.data.get("keywords")
                if isinstance(keyword_rows, list):
                    highlighted_keywords.extend(
                        str(item).strip() for item in keyword_rows if str(item).strip()
                    )
            if event.event_type == "browser_copy_selection":
                copied = str(event.data.get("clipboard_text") or "").strip()
                if copied:
                    copied_snippets.append(copied)

        title = str(capture.get("title") or url)
        final_url = str(capture.get("url") or url)
        text_excerpt = str(capture.get("text_excerpt") or "").strip()
        screenshot_path = str(capture.get("screenshot_path") or "").strip()
        keywords = _extract_keywords(text_excerpt, limit=14)
        compact_excerpt = _excerpt(text_excerpt, limit=320)
        context.settings["__latest_browser_findings"] = {
            "title": title,
            "url": final_url,
            "keywords": keywords[:14],
            "excerpt": compact_excerpt,
        }
        context.settings["__highlight_color"] = highlight_color
        copied_highlights = context.settings.get("__copied_highlights")
        if not isinstance(copied_highlights, list):
            copied_highlights = []
        for snippet in copied_snippets[:12]:
            copied_highlights.append(
                {
                    "source": "website",
                    "color": highlight_color,
                    "word": "",
                    "text": snippet,
                    "reference": final_url,
                    "title": title,
                }
            )
        context.settings["__copied_highlights"] = copied_highlights[-64:]

        pages = capture.get("pages") if isinstance(capture, dict) else []
        visited_count = len(pages) if isinstance(pages, list) else 0

        content_lines = [
            "## Website Inspection",
            f"- Page title: {title}",
            f"- URL: {final_url}",
            f"- Pages reviewed: {visited_count}",
        ]
        if keywords:
            content_lines.append(f"- Observed keywords: {', '.join(keywords[:12])}")
        if compact_excerpt:
            content_lines.extend(
                [
                    "",
                    "## Evidence Excerpt",
                    compact_excerpt,
                ]
            )
        else:
            content_lines.extend(
                [
                    "",
                    "## Evidence Excerpt",
                    "No readable text was extracted from the rendered page.",
                ]
            )

        sources = [
            AgentSource(
                source_type="web",
                label=title,
                url=final_url,
                score=0.8,
                metadata={
                    "snapshot_path": screenshot_path,
                    "excerpt": compact_excerpt,
                    "keywords": keywords[:14],
                    "pages_reviewed": visited_count,
                },
            )
        ]

        return ToolExecutionResult(
            summary=f"Website inspection completed for {title}.",
            content="\n".join(content_lines),
            data={
                "url": final_url,
                "title": title,
                "screenshot_path": screenshot_path,
                "keywords": keywords,
                "pages": pages if isinstance(pages, list) else [],
                "auto_accept_cookies": auto_accept_cookies,
                "highlight_color": highlight_color,
                "highlighted_keywords": list(dict.fromkeys(highlighted_keywords))[:24],
                "copied_snippets": copied_snippets[:8],
            },
            sources=sources,
            next_steps=[
                "Extract contacts or CTA details from the captured page.",
                "Use findings to personalize outreach messaging.",
            ],
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
