from __future__ import annotations

from collections import Counter
import re
from typing import Any, Generator
from urllib.parse import urlparse

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.tools.browser_inspect_stream import execute_playwright_inspect_stream
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
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

CHALLENGE_BLOCK_REASONS = {
    "captcha",
    "bot_challenge",
    "access_denied",
    "request_blocked",
    "forbidden",
    "javascript_required",
    "temporarily_unavailable",
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


def _root_url(raw_url: str) -> str:
    text = " ".join(str(raw_url or "").split()).strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}/"


def _is_challenge_block_reason(reason: str) -> bool:
    normalized = str(reason or "").strip().lower()
    if not normalized:
        return False
    return normalized in CHALLENGE_BLOCK_REASONS


def _human_handoff_message(*, url: str, blocked_reason: str) -> str:
    reason_text = str(blocked_reason or "").strip().replace("_", " ") or "site challenge detected"
    return (
        "Automated access is blocked by website verification. "
        f"Open {url}, complete the human verification step ({reason_text}), then retry the task."
    )


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
        return (
            yield from execute_playwright_inspect_stream(
                context=context,
                prompt=prompt,
                params=params,
                resolve_url_fn=self._resolve_url,
                truthy_fn=_truthy,
                normalize_highlight_color_fn=_normalize_highlight_color,
                extract_keywords_fn=_extract_keywords,
                excerpt_fn=_excerpt,
                root_url_fn=_root_url,
                is_challenge_block_reason_fn=_is_challenge_block_reason,
                human_handoff_message_fn=_human_handoff_message,
                get_connector_registry_fn=get_connector_registry,
            )
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
