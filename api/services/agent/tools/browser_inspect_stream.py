from __future__ import annotations

import re as _re
from typing import Any, Callable, Generator
from urllib.parse import urlparse as _urlparse

from api.services.agent.connectors.trusted_site_policy import build_trusted_site_overrides
from api.services.agent.execution.browser_event_contract import normalize_browser_event
from api.services.agent.models import AgentSource
from api.services.agent.orchestration.handoff_state import pause_for_handoff
from api.services.agent.tools.browser_interaction_guard import assess_browser_interactions
from api.services.agent.tools.base import (
    ToolExecutionContext,
    ToolExecutionError,
    ToolExecutionResult,
    ToolTraceEvent,
)
from api.services.agent.tools.web_quality import (
    compute_quality_score,
    quality_band,
    quality_remediation,
)

_SEARCH_FALLBACK_STOPWORDS = {
    "about", "after", "also", "because", "before", "being", "between",
    "could", "from", "have", "into", "more", "most", "other", "page",
    "that", "their", "there", "these", "this", "those", "using", "with",
    "your", "http", "https", "www",
}


def _build_search_fallback_query(*, url: str, prompt: str) -> str:
    """Build a search query to find cached/alternative content for a blocked URL."""
    parsed = _urlparse(url)
    hostname = _re.sub(r"^www\.", "", parsed.netloc or "") or url[:80]
    path_parts = [p for p in (parsed.path or "").split("/") if len(p) > 3]
    prompt_words = [
        w.lower()
        for w in _re.findall(r"[A-Za-z][A-Za-z0-9]{3,}", str(prompt or ""))
        if w.lower() not in _SEARCH_FALLBACK_STOPWORDS
    ]
    unique_prompt_words = list(dict.fromkeys(prompt_words))
    parts = [hostname] + path_parts[:2] + unique_prompt_words[:4]
    return " ".join(parts)[:200].strip()


def execute_playwright_inspect_stream(
    *,
    context: ToolExecutionContext,
    prompt: str,
    params: dict[str, Any],
    resolve_url_fn: Callable[..., str],
    truthy_fn: Callable[..., bool],
    normalize_highlight_color_fn: Callable[[Any], str],
    extract_keywords_fn: Callable[..., list[str]],
    excerpt_fn: Callable[..., str],
    root_url_fn: Callable[[str], str],
    is_challenge_block_reason_fn: Callable[[str], bool],
    human_handoff_message_fn: Callable[..., str],
    get_connector_registry_fn: Callable[..., Any],
) -> Generator[ToolTraceEvent, None, ToolExecutionResult]:
    url = resolve_url_fn(prompt=prompt, params=params)
    if not url:
        raise ToolExecutionError("Provide a valid URL for browser inspection.")
    _SUPPORTED_BROWSER_PROVIDERS = {"playwright_browser", "computer_use_browser"}
    web_provider = str(params.get("web_provider") or "computer_use_browser").strip() or "computer_use_browser"
    # Redirect deprecated provider to new default
    if web_provider == "playwright_browser":
        web_provider = "computer_use_browser"
    if web_provider not in _SUPPORTED_BROWSER_PROVIDERS:
        raise ToolExecutionError(
            f"Unsupported web_provider `{web_provider}`. Supported: {', '.join(sorted(_SUPPORTED_BROWSER_PROVIDERS))}."
        )
    auto_accept_cookies = truthy_fn(params.get("auto_accept_cookies"), default=True)
    follow_same_domain_links = truthy_fn(params.get("follow_same_domain_links"), default=True)
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
    human_handoff_on_blocked = truthy_fn(params.get("human_handoff_on_blocked"), default=True)
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
    highlight_color = normalize_highlight_color_fn(
        params.get("highlight_color") or context.settings.get("__highlight_color")
    )

    connector = get_connector_registry_fn().build(web_provider, settings=context.settings)
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
            "scene_surface": "website",
            "url": url,
            "source_url": url,
            "target_url": url,
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
            highlight_query=prompt,
            follow_same_domain_links=follow_links,
            interaction_actions=actions,
        )
        while True:
            try:
                payload = next(stream)
            except StopIteration as stop:
                return stop.value
            normalized_payload = normalize_browser_event(
                dict(payload or {}),
                default_scene_surface="website",
            )
            event = ToolTraceEvent(
                event_type=str(normalized_payload.get("event_type") or "browser_progress"),
                title=str(normalized_payload.get("title") or "Browser activity"),
                detail=str(normalized_payload.get("detail") or ""),
                data={**dict(normalized_payload.get("data") or {}), "web_provider": web_provider},
                snapshot_ref=str(normalized_payload.get("snapshot_ref") or "") or None,
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
        root_candidate = root_url_fn(inspected_url)
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

    # --- Search-based fallback for persistently blocked pages ---
    # When every browser retry is exhausted and the page is still blocked, query
    # Brave (or Bing as backup) to surface cached/alternative content.  The
    # search snippets are injected as supplementary text so the answer builder has
    # real evidence to synthesise instead of returning an empty response.
    _search_fallback_sources: list[dict] = []
    if bool(capture.get("blocked_signal")):
        _fallback_query = _build_search_fallback_query(url=inspected_url, prompt=prompt)
        if _fallback_query:
            fb_start_event = ToolTraceEvent(
                event_type="tool_progress",
                title="Browser blocked — switching to web search fallback",
                detail=f"Searching for alternative content: {_fallback_query[:120]}",
                data={
                    "web_provider": web_provider,
                    "search_fallback_query": _fallback_query[:200],
                    "blocked_reason": str(capture.get("blocked_reason") or ""),
                },
            )
            trace_events.append(fb_start_event)
            yield fb_start_event
            _fallback_results: list[dict] = []
            try:
                _brave = get_connector_registry_fn().build("brave_search", settings=context.settings)
                _brave_payload = _brave.web_search(query=_fallback_query, count=8)
                _fallback_results = [
                    r for r in (_brave_payload.get("results") or []) if isinstance(r, dict)
                ]
            except Exception:
                try:
                    _bing = get_connector_registry_fn().build("bing_search", settings=context.settings)
                    _bing_raw = _bing.search_web(query=_fallback_query, count=8)
                    _bing_values = (_bing_raw.get("webPages") or {}).get("value") or []
                    _fallback_results = [
                        {
                            "title": str(r.get("name") or "").strip(),
                            "url": str(r.get("url") or "").strip(),
                            "description": str(r.get("snippet") or "").strip(),
                        }
                        for r in _bing_values
                        if isinstance(r, dict)
                    ]
                except Exception:
                    _fallback_results = []
            if _fallback_results:
                _search_fallback_sources = _fallback_results
                # Build supplementary text from search snippets
                _snippet_lines = []
                for _r in _fallback_results[:6]:
                    _t = str(_r.get("title") or "").strip()
                    _d = str(_r.get("description") or "").strip()
                    if _d:
                        _snippet_lines.append(f"{_t}: {_d}" if _t else _d)
                _fallback_text = "\n\n".join(_snippet_lines)
                _existing_excerpt = str(capture.get("text_excerpt") or "").strip()
                _combined = f"{_fallback_text}\n\n{_existing_excerpt}".strip() if _existing_excerpt else _fallback_text
                capture = {
                    **capture,
                    "text_excerpt": _combined[:12000],
                    "render_quality": "medium",
                    "content_density": 0.35,
                    "search_fallback": True,
                }
                fb_done_event = ToolTraceEvent(
                    event_type="tool_progress",
                    title=f"Search fallback: {len(_fallback_results)} alternative result(s) found",
                    detail="Web search results will supplement the blocked page content",
                    data={
                        "web_provider": "search_fallback",
                        "results_count": len(_fallback_results),
                        "search_fallback_query": _fallback_query[:200],
                    },
                )
                trace_events.append(fb_done_event)
                yield fb_done_event

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
    keywords = extract_keywords_fn(text_excerpt, limit=14)
    compact_excerpt = excerpt_fn(text_excerpt, limit=320)
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
    # Inject search-fallback snippets into copied_highlights so the answer
    # builder has real evidence even when the browser was blocked.
    for _fb_row in _search_fallback_sources[:8]:
        _fb_desc = str(_fb_row.get("description") or "").strip()
        _fb_title = str(_fb_row.get("title") or "").strip()
        _fb_url = str(_fb_row.get("url") or "").strip()
        if _fb_desc:
            copied_highlights.append(
                {
                    "source": "search_fallback",
                    "color": highlight_color,
                    "word": "",
                    "text": f"{_fb_title}: {_fb_desc}" if _fb_title else _fb_desc,
                    "reference": _fb_url or final_url,
                    "title": _fb_title or title,
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
    for _fb_src in _search_fallback_sources[:6]:
        _fb_url = str(_fb_src.get("url") or "").strip()
        _fb_title = str(_fb_src.get("title") or _fb_url or "").strip()
        _fb_desc = str(_fb_src.get("description") or "").strip()
        if _fb_url and _fb_title:
            sources.append(
                AgentSource(
                    source_type="web",
                    label=_fb_title,
                    url=_fb_url,
                    score=0.6,
                    metadata={
                        "excerpt": _fb_desc[:400],
                        "via": "search_fallback",
                        "blocked_original_url": final_url,
                    },
                )
            )
    trusted_site = build_trusted_site_overrides(
        settings=context.settings,
        url=final_url or inspected_url or url,
    )
    trusted_site_mode = bool(trusted_site.get("trusted"))
    human_handoff_required = bool(
        blocked_signal and human_handoff_on_blocked and is_challenge_block_reason_fn(blocked_reason)
    )
    human_handoff_note = (
        human_handoff_message_fn(url=final_url or inspected_url or url, blocked_reason=blocked_reason)
        if human_handoff_required
        else ""
    )
    if _search_fallback_sources and human_handoff_required:
        # We recovered content via web search — no need to pause for human verification.
        human_handoff_required = False
        human_handoff_note = ""
    if trusted_site_mode and human_handoff_required:
        human_handoff_required = False
        human_handoff_note = (
            "Trusted-site mode is enabled for this host, but a verification challenge is still present. "
            "Check trusted header/cookie configuration on the target site."
        )
    if human_handoff_required:
        handoff_cursor = {
            key: float(capture.get(key))
            for key in ("cursor_x", "cursor_y")
            if isinstance(capture.get(key), (int, float))
        }
        handoff_state = pause_for_handoff(
            settings=context.settings,
            pause_reason=blocked_reason or "human_verification_required",
            handoff_url=final_url or inspected_url or url,
            note=human_handoff_note,
            barrier_type="human_verification",
            barrier_scope="website_navigation",
            verification_context={
                "tool_id": "browser.inspect",
                "url": final_url or inspected_url or url,
                "blocked_reason": blocked_reason or "",
            },
        )
        handoff_event = ToolTraceEvent(
            event_type="browser_human_verification_required",
            title="Human verification required",
            detail=human_handoff_note,
            data={
                "url": final_url or inspected_url or url,
                "blocked_reason": blocked_reason,
                "human_handoff_required": True,
                "handoff_resume_token": str(handoff_state.get("resume_token") or ""),
                "handoff_state": str(handoff_state.get("state") or ""),
                "scene_surface": "website",
                **handoff_cursor,
            },
            snapshot_ref=screenshot_path or None,
        )
        trace_events.append(handoff_event)
        yield handoff_event
    else:
        context.settings["__barrier_handoff_required"] = False
        existing_handoff = context.settings.get("__handoff_state")
        if isinstance(existing_handoff, dict):
            normalized_state = " ".join(str(existing_handoff.get("state") or "").split()).strip().lower()
            if normalized_state == "paused_for_human":
                context.settings["__handoff_state"] = {
                    **existing_handoff,
                    "state": "running",
                    "resume_status": "not_required",
                }
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
            "highlight_regions": (
                [dict(row) for row in capture.get("highlight_regions", []) if isinstance(row, dict)]
                if isinstance(capture, dict)
                else []
            )[:12],
            "highlight_sentences": (
                [str(row).strip() for row in capture.get("highlight_sentences", []) if str(row).strip()]
                if isinstance(capture, dict)
                else []
            )[:12],
            "highlight_color": (
                str(capture.get("highlight_color") or highlight_color)
                if isinstance(capture, dict)
                else highlight_color
            ),
            "pages": pages if isinstance(pages, list) else [],
            "auto_accept_cookies": auto_accept_cookies,
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
            "search_fallback_used": bool(_search_fallback_sources),
            "search_fallback_results_count": len(_search_fallback_sources),
            "human_handoff_required": human_handoff_required,
            "human_handoff_note": human_handoff_note,
            "trusted_site_mode": trusted_site_mode,
            "trusted_host": str(trusted_site.get("host") or ""),
            "trusted_header_count": len(trusted_site.get("headers") or {}),
            "trusted_cookie_count": len(trusted_site.get("cookies") or []),
            "stages": stages,
        },
        sources=sources,
        next_steps=next_steps,
        events=trace_events,
    )
