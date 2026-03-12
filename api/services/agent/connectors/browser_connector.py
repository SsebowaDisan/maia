from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import random
import time
from typing import Any, Generator

from api.services.agent.execution.browser_runtime import BrowserRuntime

from .browser_page_state import (
    capture_page_state,
    move_cursor,
    page_metrics,
    playwright_available,
)
from .browser_live_utils import (
    excerpt,
    extract_keywords,
    keyword_regions,
    safe_focus_point,
    smart_scroll_delta,
    to_number,
)
from .browser_navigation_utils import accept_cookie_banner, extract_same_origin_links
from .browser_stealth_script import STEALTH_INIT_SCRIPT
from .browser_stream_stage_initial import run_initial_browser_stage
from .browser_stream_stage_pages import run_browser_pages_stage
from .trusted_site_policy import build_trusted_site_overrides
from .base import BaseConnector, ConnectorError, ConnectorHealth


class BrowserConnector(BaseConnector):
    connector_id = "playwright_browser"

    def health_check(self) -> ConnectorHealth:
        if not playwright_available():
            return ConnectorHealth(
                self.connector_id,
                False,
                "Playwright is not installed. Run `pip install playwright` and `playwright install`.",
            )
        return ConnectorHealth(self.connector_id, True, "configured")

    def browse_and_capture(
        self,
        *,
        url: str,
        timeout_ms: int = 20000,
        wait_ms: int = 1200,
        auto_accept_cookies: bool = True,
        highlight_color: str = "yellow",
        follow_same_domain_links: bool = True,
        interaction_actions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        stream = self.browse_live_stream(
            url=url,
            timeout_ms=timeout_ms,
            wait_ms=wait_ms,
            max_pages=1,
            max_scroll_steps=1,
            auto_accept_cookies=auto_accept_cookies,
            highlight_color=highlight_color,
            follow_same_domain_links=follow_same_domain_links,
            interaction_actions=interaction_actions,
        )
        while True:
            try:
                next(stream)
            except StopIteration as stop:
                return stop.value

    def browse_live_stream(
        self,
        *,
        url: str,
        timeout_ms: int = 20000,
        wait_ms: int = 1200,
        max_pages: int = 3,
        max_scroll_steps: int = 3,
        auto_accept_cookies: bool = True,
        highlight_color: str = "yellow",
        follow_same_domain_links: bool = True,
        interaction_actions: list[dict[str, Any]] | None = None,
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        if not playwright_available():
            raise ConnectorError(
                "Playwright is not installed. Run `pip install playwright` and `playwright install`."
            )

        from playwright.sync_api import sync_playwright

        output_dir = Path(".maia_agent") / "browser_captures"
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp_prefix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        visited_pages: list[dict[str, Any]] = []
        stream_started = time.perf_counter()

        effective_highlight_color = "green" if str(highlight_color).strip().lower() == "green" else "yellow"
        movement_rng = random.Random(datetime.now(timezone.utc).timestamp())
        runtime = BrowserRuntime(scene_surface="website")

        def _elapsed_ms() -> int:
            return int((time.perf_counter() - stream_started) * 1000.0)

        def _quality_profile(*, text_excerpt: str) -> dict[str, Any]:
            compact = " ".join(str(text_excerpt or "").split())
            characters = len(compact)
            words = len(re.findall(r"[A-Za-z0-9]+", compact))
            density = round(min(1.0, float(words) / 420.0), 4)
            blocked_patterns = (
                ("captcha", "captcha"),
                ("cloudflare", "bot_challenge"),
                ("security verification", "bot_challenge"),
                ("performing security verification", "bot_challenge"),
                ("checking your browser", "bot_challenge"),
                ("attention required", "bot_challenge"),
                ("i'm not a robot", "captcha"),
                ("recaptcha", "captcha"),
                ("turnstile", "captcha"),
                ("access denied", "access_denied"),
                ("verify you are human", "bot_challenge"),
                ("unusual traffic", "bot_challenge"),
                ("temporarily unavailable", "temporarily_unavailable"),
                ("enable javascript", "javascript_required"),
                ("request blocked", "request_blocked"),
                ("forbidden", "forbidden"),
            )
            lowered = compact.lower()
            blocked_reason = ""
            for pattern, reason in blocked_patterns:
                if pattern in lowered:
                    blocked_reason = reason
                    break
            blocked_signal = bool(blocked_reason)
            if blocked_signal:
                render_quality = "blocked"
            elif characters < 120:
                render_quality = "low"
            elif characters < 900:
                render_quality = "medium"
            else:
                render_quality = "high"
            return {
                "render_quality": render_quality,
                "content_density": density,
                "blocked_signal": blocked_signal,
                "blocked_reason": blocked_reason,
                "characters": characters,
            }

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-accelerated-2d-canvas",
                    "--no-first-run",
                    "--no-zygote",
                    "--disable-gpu",
                    "--window-size=1366,768",
                ],
            )
            trusted_site = build_trusted_site_overrides(settings=self.settings, url=url)
            trusted_headers = (
                dict(trusted_site.get("headers") or {})
                if isinstance(trusted_site.get("headers"), dict)
                else {}
            )
            # Use a current, realistic Chrome UA with matching sec-ch-ua client hints.
            # Anti-bot systems (Akamai, Cloudflare) cross-check the UA string against
            # these headers — a mismatch is an instant bot signal.
            _chrome_ua = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/134.0.0.0 Safari/537.36"
            )
            _stealth_headers = {
                "sec-ch-ua": '"Chromium";v="134", "Google Chrome";v="134", "Not-A.Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "none",
                "sec-fetch-user": "?1",
                "upgrade-insecure-requests": "1",
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "accept-language": "en-US,en;q=0.9",
            }
            # Trusted site headers take priority over stealth defaults
            _merged_headers = {**_stealth_headers, **trusted_headers} if trusted_headers else _stealth_headers
            browser_context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=_chrome_ua,
                locale="en-US",
                timezone_id="America/New_York",
                extra_http_headers=_merged_headers,
            )
            # Inject stealth script before every navigation
            browser_context.add_init_script(STEALTH_INIT_SCRIPT)
            trusted_cookies = (
                list(trusted_site.get("cookies") or [])
                if isinstance(trusted_site.get("cookies"), list)
                else []
            )
            if trusted_cookies:
                try:
                    browser_context.add_cookies(trusted_cookies)
                except Exception:
                    pass
            page = browser_context.new_page()
            actions = interaction_actions if isinstance(interaction_actions, list) else []

            def _safe_selector(value: Any) -> str:
                text = str(value or "").strip()
                if not text or len(text) > 160:
                    return ""
                lowered = text.lower()
                if "javascript:" in lowered:
                    return ""
                return text

            def _jitter_target(
                base_x: float,
                base_y: float,
                *,
                spread: float = 22.0,
            ) -> tuple[float, float]:
                metrics = page_metrics(page=page)
                viewport_width = max(1.0, to_number(metrics.get("viewport_width"), 1366.0))
                viewport_height = max(1.0, to_number(metrics.get("viewport_height"), 768.0))
                x = float(base_x) + movement_rng.uniform(-spread, spread)
                y = float(base_y) + movement_rng.uniform(-spread * 0.52, spread * 0.52)
                return (
                    max(8.0, min(viewport_width - 8.0, x)),
                    max(8.0, min(viewport_height - 8.0, y)),
                )

            def _website_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
                base = dict(payload or {})
                base.setdefault("scene_surface", "website")
                return base

            def _emit_extract_side_events(
                *,
                capture: dict[str, str],
                page_index: int,
                cursor_payload: dict[str, float],
            ) -> Generator[dict[str, Any], None, None]:
                text_excerpt = str(capture.get("text_excerpt") or "").strip()
                keywords = extract_keywords(text_excerpt, limit=8)
                if keywords:
                    regions = keyword_regions(page=page, keywords=keywords, limit=8)
                    if regions:
                        regions = [{**dict(row), "color": effective_highlight_color} for row in regions]
                    metrics = page_metrics(page=page)
                    viewport_width = max(1.0, to_number(metrics.get("viewport_width"), 1366.0))
                    viewport_height = max(1.0, to_number(metrics.get("viewport_height"), 768.0))
                    highlight_cursor = dict(cursor_payload)
                    if regions:
                        region = regions[0]
                        rx = float(region.get("x", 0.0))
                        ry = float(region.get("y", 0.0))
                        rw = float(region.get("width", 0.0))
                        rh = float(region.get("height", 0.0))
                        cursor_x = (rx + max(0.5, rw / 2.0)) / 100.0 * viewport_width
                        cursor_y = (ry + max(0.5, rh / 2.0)) / 100.0 * viewport_height
                        cursor_x, cursor_y = _jitter_target(cursor_x, cursor_y, spread=18.0)
                        highlight_cursor = move_cursor(page=page, x=cursor_x, y=cursor_y)
                    find_query = " ".join(keywords[:2]).strip() or keywords[0]
                    if find_query:
                        find_capture = capture_page_state(
                            page=page,
                            output_dir=output_dir,
                            stamp_prefix=stamp_prefix,
                            label=f"find-{page_index}",
                        )
                        yield {
                            "event_type": "browser_find_in_page",
                            "title": "Search terms on page",
                            "detail": find_query,
                            "data": _website_payload(
                                {
                                    "url": find_capture["url"],
                                    "title": find_capture["title"],
                                    "page_index": page_index,
                                    "find_query": find_query,
                                    "keywords": keywords[:8],
                                    "match_count": len(regions),
                                    "highlight_regions": regions,
                                    "highlight_color": effective_highlight_color,
                                    **highlight_cursor,
                                    **page_metrics(page=page),
                                }
                            ),
                            "snapshot_ref": find_capture["screenshot_path"],
                        }
                    highlight_capture = capture_page_state(
                        page=page,
                        output_dir=output_dir,
                        stamp_prefix=stamp_prefix,
                        label=f"highlight-{page_index}",
                    )
                    yield {
                        "event_type": "browser_keyword_highlight",
                        "title": "Highlight relevant keywords",
                        "detail": ", ".join(keywords[:5]),
                        "data": _website_payload(
                            {
                                "url": highlight_capture["url"],
                                "title": highlight_capture["title"],
                                "page_index": page_index,
                                "keywords": keywords[:8],
                                "highlight_regions": regions,
                                "find_query": find_query,
                                "match_count": len(regions),
                                "highlight_color": effective_highlight_color,
                                **highlight_cursor,
                                **page_metrics(page=page),
                            }
                        ),
                        "snapshot_ref": highlight_capture["screenshot_path"],
                    }
                copied = excerpt(text_excerpt, limit=420)
                if copied:
                    copied_words = [
                        token
                        for token in (part.strip() for part in re.split(r"\s+", copied))
                        if token
                    ][:8]
                    yield {
                        "event_type": "browser_copy_selection",
                        "title": "Copy evidence snippet",
                        "detail": excerpt(copied, limit=150),
                        "data": _website_payload(
                            {
                                "url": str(capture.get("url") or ""),
                                "title": str(capture.get("title") or ""),
                                "page_index": page_index,
                                "clipboard_text": copied,
                                "copied_words": copied_words,
                                "highlight_color": effective_highlight_color,
                                **cursor_payload,
                                **page_metrics(page=page),
                            }
                        ),
                        "snapshot_ref": str(capture.get("screenshot_path") or ""),
                    }

            # Safe defaults so run_initial_browser_stage can accept them as parameters.
            # The function reassigns both internally and returns the live captures in
            # stage_one["open_capture"] / stage_one["open_cursor"].
            open_capture: dict[str, Any] = {}
            open_cursor: dict[str, float] = {}

            stage_one = yield from run_initial_browser_stage(
                page=page,
                url=url,
                timeout_ms=timeout_ms,
                wait_ms=wait_ms,
                auto_accept_cookies=auto_accept_cookies,
                actions=actions,
                trusted_site=trusted_site,
                trusted_headers=trusted_headers,
                trusted_cookies=trusted_cookies,
                output_dir=output_dir,
                stamp_prefix=stamp_prefix,
                visited_pages=visited_pages,
                open_capture=open_capture,
                open_cursor=open_cursor,
                movement_rng=movement_rng,
                _quality_profile=_quality_profile,
                _safe_selector=_safe_selector,
                _jitter_target=_jitter_target,
                _website_payload=_website_payload,
                _emit_extract_side_events=_emit_extract_side_events,
                _elapsed_ms=_elapsed_ms,
                runtime=runtime,
                accept_cookie_banner=accept_cookie_banner,
                move_cursor=move_cursor,
                capture_page_state=capture_page_state,
                page_metrics=page_metrics,
                excerpt=excerpt,
            )
            # Retrieve the captures the stage function created internally.
            if isinstance(stage_one.get("open_capture"), dict):
                open_capture = stage_one["open_capture"]
            if isinstance(stage_one.get("open_cursor"), dict):
                open_cursor = stage_one["open_cursor"]

            current_url = str(stage_one.get("current_url") or str(open_capture.get("url") or url))
            final_cursor = (
                dict(stage_one.get("final_cursor"))
                if isinstance(stage_one.get("final_cursor"), dict)
                else dict(open_cursor)
            )

            stage_two = yield from run_browser_pages_stage(
                page=page,
                browser_context=browser_context,
                browser=browser,
                current_url=current_url,
                final_cursor=final_cursor,
                open_cursor=open_cursor,
                follow_same_domain_links=follow_same_domain_links,
                max_pages=max_pages,
                max_scroll_steps=max_scroll_steps,
                timeout_ms=timeout_ms,
                wait_ms=wait_ms,
                auto_accept_cookies=auto_accept_cookies,
                output_dir=output_dir,
                stamp_prefix=stamp_prefix,
                movement_rng=movement_rng,
                visited_pages=visited_pages,
                _quality_profile=_quality_profile,
                _safe_selector=_safe_selector,
                _jitter_target=_jitter_target,
                _website_payload=_website_payload,
                _emit_extract_side_events=_emit_extract_side_events,
                _elapsed_ms=_elapsed_ms,
                extract_same_origin_links=extract_same_origin_links,
                accept_cookie_banner=accept_cookie_banner,
                safe_focus_point=safe_focus_point,
                smart_scroll_delta=smart_scroll_delta,
                move_cursor=move_cursor,
                capture_page_state=capture_page_state,
                page_metrics=page_metrics,
                runtime=runtime,
            )
            if isinstance(stage_two.get("final_cursor"), dict):
                final_cursor = dict(stage_two.get("final_cursor") or final_cursor)
            targets = (
                list(stage_two.get("targets"))
                if isinstance(stage_two.get("targets"), list)
                else [current_url]
            )
        if not visited_pages:
            return {
                "url": current_url,
                "title": str(open_capture.get("title") or ""),
                "text_excerpt": str(open_capture.get("text_excerpt") or ""),
                "screenshot_path": str(open_capture.get("screenshot_path") or ""),
                "cursor_x": float(final_cursor.get("cursor_x") or 0.0),
                "cursor_y": float(final_cursor.get("cursor_y") or 0.0),
                "pages": [],
            }

        combined_excerpt = "\n\n".join(
            str(row.get("text_excerpt") or "").strip() for row in visited_pages if isinstance(row, dict)
        )
        combined_excerpt = combined_excerpt[:12000]
        page_profiles = [dict(row) for row in visited_pages if isinstance(row, dict)]
        blocked_profiles = [row for row in page_profiles if bool(row.get("blocked_signal"))]
        average_density = 0.0
        if page_profiles:
            total_density = 0.0
            for row in page_profiles:
                try:
                    total_density += float(row.get("content_density") or 0.0)
                except Exception:
                    total_density += 0.0
            average_density = round(total_density / float(len(page_profiles)), 4)
        if blocked_profiles:
            final_quality = "blocked"
        elif average_density < 0.15:
            final_quality = "low"
        elif average_density < 0.45:
            final_quality = "medium"
        else:
            final_quality = "high"
        primary = visited_pages[0]
        final_page = visited_pages[-1]
        return {
            "url": str(final_page.get("url") or current_url),
            "title": str(primary.get("title") or final_page.get("title") or current_url),
            "text_excerpt": combined_excerpt,
            "screenshot_path": str(final_page.get("screenshot_path") or ""),
            "cursor_x": float(final_cursor.get("cursor_x") or 0.0),
            "cursor_y": float(final_cursor.get("cursor_y") or 0.0),
            "pages": visited_pages,
            "render_quality": final_quality,
            "content_density": average_density,
            "blocked_signal": bool(blocked_profiles),
            "blocked_reason": str(blocked_profiles[0].get("blocked_reason") or "") if blocked_profiles else "",
            "stages": {
                "initial_render": True,
                "lazy_load_scroll": max(1, int(max_scroll_steps)),
                "same_domain_followup": max(0, len(targets) - 1),
            },
        }
