from __future__ import annotations

from collections import Counter
import re
from typing import Any, Generator
from urllib.parse import urlparse

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.models import AgentSource
from api.services.agent.tools.browser_interaction_guard import assess_browser_interactions
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionError,
    ToolExecutionResult,
    ToolTraceEvent,
    ToolMetadata,
)
from api.services.agent.tools.web_quality import (
    compute_quality_score,
    quality_band,
    quality_remediation,
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
        url = self._resolve_url(prompt=prompt, params=params)
        if not url:
            raise ToolExecutionError("Provide a valid URL for browser inspection.")
        web_provider = str(params.get("web_provider") or "playwright_browser").strip() or "playwright_browser"
        if web_provider != "playwright_browser":
            raise ToolExecutionError(
                f"Unsupported web_provider `{web_provider}`. Supported value: `playwright_browser`."
            )
        auto_accept_cookies = _truthy(params.get("auto_accept_cookies"), default=True)
        follow_same_domain_links = _truthy(params.get("follow_same_domain_links"), default=True)
        blocked_retry_attempts_raw = params.get("blocked_retry_attempts")
        try:
            blocked_retry_attempts = max(0, min(2, int(blocked_retry_attempts_raw)))
        except Exception:
            blocked_retry_attempts = 1
        blocked_root_retry_raw = params.get("blocked_root_retry_attempts")
        try:
            blocked_root_retry_attempts = max(0, min(1, int(blocked_root_retry_raw)))
        except Exception:
            blocked_root_retry_attempts = 1
        human_handoff_on_blocked = _truthy(params.get("human_handoff_on_blocked"), default=True)
        raw_actions = params.get("interaction_actions")
        interaction_actions = (
            [dict(item) for item in raw_actions[:8] if isinstance(item, dict)]
            if isinstance(raw_actions, list)
            else []
        )
        interaction_review = assess_browser_interactions(
            prompt=prompt,
            url=url,
            actions=interaction_actions,
        )
        allowed_interaction_actions = (
            [dict(item) for item in interaction_review.get("allowed_actions", []) if isinstance(item, dict)]
            if isinstance(interaction_review, dict)
            else []
        )
        blocked_interaction_actions = (
            [dict(item) for item in interaction_review.get("blocked_actions", []) if isinstance(item, dict)]
            if isinstance(interaction_review, dict)
            else []
        )
        highlight_color = _normalize_highlight_color(
            params.get("highlight_color") or context.settings.get("__highlight_color")
        )

        connector = get_connector_registry().build(web_provider, settings=context.settings)
        trace_events: list[ToolTraceEvent] = []
        provider_event = ToolTraceEvent(
            event_type="tool_progress",
            title="Select web provider",
            detail=f"Provider: {web_provider}",
            data={"web_provider": web_provider},
        )
        trace_events.append(provider_event)
        yield provider_event
        if interaction_actions:
            interaction_event = ToolTraceEvent(
                event_type="tool_progress",
                title="Prepare browser interactions",
                detail=f"Planned {len(interaction_actions)} interaction action(s)",
                data={
                    "web_provider": web_provider,
                    "interaction_actions": interaction_actions,
                },
            )
            trace_events.append(interaction_event)
            yield interaction_event
        interaction_policy_event = ToolTraceEvent(
            event_type="browser_interaction_policy",
            title="Review browser interaction safety",
            detail=str(interaction_review.get("policy_note") or "").strip()[:200],
            data={
                "web_provider": web_provider,
                "requested_actions": len(interaction_actions),
                "allowed_actions": len(allowed_interaction_actions),
                "blocked_actions": len(blocked_interaction_actions),
                "blocked_action_rows": blocked_interaction_actions[:8],
                "llm_used": bool(interaction_review.get("llm_used")),
            },
        )
        trace_events.append(interaction_policy_event)
        yield interaction_policy_event
        copied_snippets: list[str] = []
        highlighted_keywords: list[str] = []
        blocked_retry_used = 0
        blocked_retry_improved = False
        blocked_root_retry_used = 0
        blocked_root_retry_improved = False
        inspected_url = url

        def _run_capture(
            *,
            capture_url: str,
            follow_links: bool,
            actions: list[dict[str, Any]],
        ) -> dict[str, Any]:
            stream = connector.browse_live_stream(
                url=capture_url,
                auto_accept_cookies=auto_accept_cookies,
                highlight_color=highlight_color,
                follow_same_domain_links=follow_links,
                interaction_actions=actions,
            )
            while True:
                try:
                    payload = next(stream)
                except StopIteration as stop:
                    return stop.value
                event = ToolTraceEvent(
                    event_type=str(payload.get("event_type") or "browser_progress"),
                    title=str(payload.get("title") or "Browser activity"),
                    detail=str(payload.get("detail") or ""),
                    data={**dict(payload.get("data") or {}), "web_provider": web_provider},
                    snapshot_ref=str(payload.get("snapshot_ref") or "") or None,
                )
                trace_events.append(event)
                yield_event = event
                # yield from nested function by mutating outer list
                pending_events.append(yield_event)
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

        pending_events: list[ToolTraceEvent] = []
        capture = _run_capture(
            capture_url=inspected_url,
            follow_links=follow_same_domain_links,
            actions=allowed_interaction_actions,
        )
        while pending_events:
            yield pending_events.pop(0)

        for _retry_idx in range(blocked_retry_attempts):
            if not bool(capture.get("blocked_signal")):
                break
            blocked_retry_used += 1
            retry_event = ToolTraceEvent(
                event_type="tool_progress",
                title=f"Blocked-page recovery attempt {blocked_retry_used}",
                detail="Retrying capture in read-only mode",
                data={
                    "web_provider": web_provider,
                    "blocked_retry_attempt": blocked_retry_used,
                },
            )
            trace_events.append(retry_event)
            yield retry_event
            retry_capture = _run_capture(
                capture_url=inspected_url,
                follow_links=False,
                actions=[],
            )
            while pending_events:
                yield pending_events.pop(0)
            previous_chars = len(str(capture.get("text_excerpt") or ""))
            retry_chars = len(str(retry_capture.get("text_excerpt") or ""))
            retry_blocked = bool(retry_capture.get("blocked_signal"))
            if (not retry_blocked and bool(capture.get("blocked_signal"))) or (retry_chars >= (previous_chars + 200)):
                capture = retry_capture
                blocked_retry_improved = True

        if bool(capture.get("blocked_signal")) and blocked_root_retry_attempts > 0:
            root_candidate = _root_url(inspected_url)
            if root_candidate and root_candidate.rstrip("/") != inspected_url.rstrip("/"):
                for _attempt in range(blocked_root_retry_attempts):
                    blocked_root_retry_used += 1
                    root_retry_event = ToolTraceEvent(
                        event_type="tool_progress",
                        title=f"Blocked-page recovery attempt {blocked_retry_used + blocked_root_retry_used}",
                        detail="Retrying capture from site root URL",
                        data={
                            "web_provider": web_provider,
                            "blocked_root_retry_attempt": blocked_root_retry_used,
                            "target_url": root_candidate,
                        },
                    )
                    trace_events.append(root_retry_event)
                    yield root_retry_event
                    retry_capture = _run_capture(
                        capture_url=root_candidate,
                        follow_links=False,
                        actions=[],
                    )
                    while pending_events:
                        yield pending_events.pop(0)
                    previous_chars = len(str(capture.get("text_excerpt") or ""))
                    retry_chars = len(str(retry_capture.get("text_excerpt") or ""))
                    retry_blocked = bool(retry_capture.get("blocked_signal"))
                    if (not retry_blocked and bool(capture.get("blocked_signal"))) or (
                        retry_chars >= (previous_chars + 200)
                    ):
                        capture = retry_capture
                        inspected_url = root_candidate
                        blocked_root_retry_improved = True
                        if not retry_blocked:
                            break

        title = str(capture.get("title") or url)
        final_url = str(capture.get("url") or url)
        text_excerpt = str(capture.get("text_excerpt") or "").strip()
        screenshot_path = str(capture.get("screenshot_path") or "").strip()
        render_quality = str(capture.get("render_quality") or "").strip().lower() or "unknown"
        blocked_signal = bool(capture.get("blocked_signal"))
        blocked_reason = str(capture.get("blocked_reason") or "").strip()
        try:
            content_density = float(capture.get("content_density") or 0.0)
        except Exception:
            content_density = 0.0
        stages = capture.get("stages") if isinstance(capture.get("stages"), dict) else {}
        keywords = _extract_keywords(text_excerpt, limit=14)
        compact_excerpt = _excerpt(text_excerpt, limit=320)
        inspection_quality_score = compute_quality_score(
            render_quality=render_quality,
            content_density=content_density,
            extraction_confidence=0.7 if text_excerpt else 0.1,
            schema_coverage=1.0,
            evidence_count=len(copied_snippets),
            blocked_signal=blocked_signal,
        )
        inspection_quality_band = quality_band(inspection_quality_score)
        context.settings["__latest_browser_findings"] = {
            "title": title,
            "url": final_url,
            "keywords": keywords[:14],
            "excerpt": compact_excerpt,
            "render_quality": render_quality,
            "content_density": content_density,
            "blocked_signal": blocked_signal,
            "quality_score": inspection_quality_score,
            "quality_band": inspection_quality_band,
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
            f"- Render quality: {render_quality}",
            f"- Quality score: {inspection_quality_score:.3f} ({inspection_quality_band})",
            f"- Content density: {content_density:.3f}",
        ]
        if blocked_signal:
            content_lines.append(
                f"- Blocked signal: yes ({blocked_reason or 'site challenge detected'})"
            )
        else:
            content_lines.append("- Blocked signal: no")
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
                    "render_quality": render_quality,
                    "content_density": content_density,
                    "blocked_signal": blocked_signal,
                    "blocked_reason": blocked_reason,
                },
            )
        ]
        human_handoff_required = bool(
            blocked_signal and human_handoff_on_blocked and _is_challenge_block_reason(blocked_reason)
        )
        human_handoff_note = (
            _human_handoff_message(url=final_url or inspected_url or url, blocked_reason=blocked_reason)
            if human_handoff_required
            else ""
        )
        if human_handoff_required:
            context.settings["__barrier_handoff_required"] = True
            context.settings["__barrier_handoff_note"] = human_handoff_note
            context.settings["__barrier_handoff_url"] = final_url or inspected_url or url
            context.settings["__barrier_handoff_reason"] = blocked_reason
            handoff_event = ToolTraceEvent(
                event_type="browser_human_verification_required",
                title="Human verification required",
                detail=human_handoff_note,
                data={
                    "url": final_url or inspected_url or url,
                    "blocked_reason": blocked_reason,
                    "human_handoff_required": True,
                    "scene_surface": "website",
                },
                snapshot_ref=screenshot_path or None,
            )
            trace_events.append(handoff_event)
            yield handoff_event
        next_steps: list[str] = []
        next_steps.extend(
            quality_remediation(
                score=inspection_quality_score,
                blocked_signal=blocked_signal,
            )
        )
        if human_handoff_note and human_handoff_note not in next_steps:
            next_steps.insert(0, human_handoff_note)
        if blocked_interaction_actions:
            next_steps.append(
                "Some interaction actions were blocked by policy review; adjust the requested actions and retry."
            )
        if not next_steps:
            next_steps = []

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
                "web_provider": web_provider,
                "follow_same_domain_links": follow_same_domain_links,
                "interaction_actions": allowed_interaction_actions,
                "interaction_actions_blocked": blocked_interaction_actions[:8],
                "render_quality": render_quality,
                "quality_score": inspection_quality_score,
                "quality_band": inspection_quality_band,
                "content_density": round(content_density, 4),
                "blocked_signal": blocked_signal,
                "blocked_reason": blocked_reason,
                "blocked_retry_attempts": blocked_retry_attempts,
                "blocked_retry_used": blocked_retry_used,
                "blocked_retry_improved": blocked_retry_improved,
                "blocked_root_retry_attempts": blocked_root_retry_attempts,
                "blocked_root_retry_used": blocked_root_retry_used,
                "blocked_root_retry_improved": blocked_root_retry_improved,
                "human_handoff_required": human_handoff_required,
                "human_handoff_note": human_handoff_note,
                "stages": stages,
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
