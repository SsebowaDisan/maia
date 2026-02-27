from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import random
from typing import Any, Generator

from .browser_live_utils import (
    excerpt,
    extract_keywords,
    keyword_regions,
    safe_focus_point,
    smart_scroll_delta,
    to_number,
)
from .browser_navigation_utils import accept_cookie_banner, extract_same_origin_links
from .base import BaseConnector, ConnectorError, ConnectorHealth


class BrowserConnector(BaseConnector):
    connector_id = "playwright_browser"

    def _playwright_available(self) -> bool:
        try:
            import playwright.sync_api  # noqa: F401
            return True
        except Exception:
            return False

    def health_check(self) -> ConnectorHealth:
        if not self._playwright_available():
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
    ) -> dict[str, Any]:
        stream = self.browse_live_stream(
            url=url,
            timeout_ms=timeout_ms,
            wait_ms=wait_ms,
            max_pages=1,
            max_scroll_steps=1,
            auto_accept_cookies=auto_accept_cookies,
            highlight_color=highlight_color,
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
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        if not self._playwright_available():
            raise ConnectorError(
                "Playwright is not installed. Run `pip install playwright` and `playwright install`."
            )

        from playwright.sync_api import sync_playwright

        output_dir = Path(".maia_agent") / "browser_captures"
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp_prefix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        visited_pages: list[dict[str, Any]] = []

        effective_highlight_color = "green" if str(highlight_color).strip().lower() == "green" else "yellow"
        movement_rng = random.Random(datetime.now(timezone.utc).timestamp())

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 768})

            def _jitter_target(
                base_x: float,
                base_y: float,
                *,
                spread: float = 22.0,
            ) -> tuple[float, float]:
                metrics = self._page_metrics(page=page)
                viewport_width = max(1.0, to_number(metrics.get("viewport_width"), 1366.0))
                viewport_height = max(1.0, to_number(metrics.get("viewport_height"), 768.0))
                x = float(base_x) + movement_rng.uniform(-spread, spread)
                y = float(base_y) + movement_rng.uniform(-spread * 0.52, spread * 0.52)
                return (
                    max(8.0, min(viewport_width - 8.0, x)),
                    max(8.0, min(viewport_height - 8.0, y)),
                )

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
                    metrics = self._page_metrics(page=page)
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
                        highlight_cursor = self._move_cursor(page=page, x=cursor_x, y=cursor_y)
                    find_query = " ".join(keywords[:2]).strip() or keywords[0]
                    if find_query:
                        find_capture = self._capture_page_state(
                            page=page,
                            output_dir=output_dir,
                            stamp_prefix=stamp_prefix,
                            label=f"find-{page_index}",
                        )
                        yield {
                            "event_type": "browser_find_in_page",
                            "title": "Search terms on page",
                            "detail": find_query,
                            "data": {
                                "url": find_capture["url"],
                                "title": find_capture["title"],
                                "page_index": page_index,
                                "find_query": find_query,
                                "keywords": keywords[:8],
                                "match_count": len(regions),
                                "highlight_regions": regions,
                                "highlight_color": effective_highlight_color,
                                **highlight_cursor,
                                **self._page_metrics(page=page),
                            },
                            "snapshot_ref": find_capture["screenshot_path"],
                        }
                    highlight_capture = self._capture_page_state(
                        page=page,
                        output_dir=output_dir,
                        stamp_prefix=stamp_prefix,
                        label=f"highlight-{page_index}",
                    )
                    yield {
                        "event_type": "browser_keyword_highlight",
                        "title": "Highlight relevant keywords",
                        "detail": ", ".join(keywords[:5]),
                        "data": {
                            "url": highlight_capture["url"],
                            "title": highlight_capture["title"],
                            "page_index": page_index,
                            "keywords": keywords[:8],
                            "highlight_regions": regions,
                            "find_query": find_query,
                            "match_count": len(regions),
                            "highlight_color": effective_highlight_color,
                            **highlight_cursor,
                            **self._page_metrics(page=page),
                        },
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
                        "data": {
                            "url": str(capture.get("url") or ""),
                            "title": str(capture.get("title") or ""),
                            "page_index": page_index,
                            "clipboard_text": copied,
                            "copied_words": copied_words,
                            "highlight_color": effective_highlight_color,
                            **cursor_payload,
                            **self._page_metrics(page=page),
                        },
                        "snapshot_ref": str(capture.get("screenshot_path") or ""),
                    }

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(max(200, wait_ms))
            except Exception as exc:
                browser.close()
                raise ConnectorError(f"Failed to open URL: {url}. {exc}") from exc

            open_x, open_y = _jitter_target(124, 88, spread=14.0)
            open_cursor = self._move_cursor(page=page, x=open_x, y=open_y)
            open_capture = self._capture_page_state(
                page=page,
                output_dir=output_dir,
                stamp_prefix=stamp_prefix,
                label="open",
            )
            open_metrics = self._page_metrics(page=page)
            yield {
                "event_type": "browser_open",
                "title": "Start Playwright browser session",
                "detail": open_capture["url"],
                "data": {
                    "url": open_capture["url"],
                    "title": open_capture["title"],
                    "page_index": 1,
                    **open_cursor,
                    **open_metrics,
                },
                "snapshot_ref": open_capture["screenshot_path"],
            }

            if auto_accept_cookies:
                consent = accept_cookie_banner(page=page, wait_ms=wait_ms)
                consent_capture = self._capture_page_state(
                    page=page,
                    output_dir=output_dir,
                    stamp_prefix=stamp_prefix,
                    label="cookie-accept-1",
                )
                if consent.get("accepted"):
                    yield {
                        "event_type": "browser_cookie_accept",
                        "title": "Accept website cookies",
                        "detail": str(consent.get("label") or "Accepted cookie consent banner"),
                        "data": {
                            "url": consent_capture["url"],
                            "title": consent_capture["title"],
                            "page_index": 1,
                        },
                        "snapshot_ref": consent_capture["screenshot_path"],
                    }
                else:
                    yield {
                        "event_type": "browser_cookie_check",
                        "title": "Check website cookies",
                        "detail": "No cookie banner detected or consent already stored.",
                        "data": {
                            "url": consent_capture["url"],
                            "title": consent_capture["title"],
                            "page_index": 1,
                        },
                        "snapshot_ref": consent_capture["screenshot_path"],
                    }

            # Always capture a fast first-pass extract before any scrolling/navigation so
            # the agent can ground an initial answer from the landing page immediately.
            quick_x, quick_y = _jitter_target(220, 192, spread=20.0)
            quick_cursor = self._move_cursor(page=page, x=quick_x, y=quick_y)
            quick_capture = self._capture_page_state(
                page=page,
                output_dir=output_dir,
                stamp_prefix=stamp_prefix,
                label="extract-initial-1",
            )
            visited_pages.append(
                {
                    "url": quick_capture["url"],
                    "title": quick_capture["title"],
                    "text_excerpt": quick_capture["text_excerpt"],
                    "screenshot_path": quick_capture["screenshot_path"],
                }
            )
            yield {
                "event_type": "browser_extract",
                "title": "Fast landing-page analysis",
                "detail": quick_capture["title"] or quick_capture["url"],
                "data": {
                    "url": quick_capture["url"],
                    "title": quick_capture["title"],
                    "page_index": 1,
                    "extract_pass": "initial",
                    "characters": len(str(quick_capture["text_excerpt"] or "")),
                    "text_excerpt": str(quick_capture["text_excerpt"] or "")[:1200],
                    **quick_cursor,
                    **self._page_metrics(page=page),
                },
                "snapshot_ref": quick_capture["screenshot_path"],
            }
            for side_event in _emit_extract_side_events(
                capture=quick_capture,
                page_index=1,
                cursor_payload=quick_cursor,
            ):
                yield side_event

            current_url = str(open_capture["url"] or url)
            targets = [current_url]
            targets.extend(
                extract_same_origin_links(
                    page=page,
                    origin_url=current_url,
                    limit=max(0, int(max_pages) - 1),
                )
            )

            for page_index, target_url in enumerate(targets, start=1):
                last_cursor = dict(open_cursor)
                if page_index > 1:
                    try:
                        page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
                        page.wait_for_timeout(max(200, wait_ms))
                    except Exception:
                        continue
                    nav_x, nav_y = _jitter_target(138, 106, spread=16.0)
                    last_cursor = self._move_cursor(page=page, x=nav_x, y=nav_y)
                    nav_capture = self._capture_page_state(
                        page=page,
                        output_dir=output_dir,
                        stamp_prefix=stamp_prefix,
                        label=f"nav-{page_index}",
                    )
                    nav_metrics = self._page_metrics(page=page)
                    yield {
                        "event_type": "browser_navigate",
                        "title": f"Navigate to page {page_index}",
                        "detail": nav_capture["url"],
                        "data": {
                            "url": nav_capture["url"],
                            "title": nav_capture["title"],
                            "page_index": page_index,
                            **last_cursor,
                            **nav_metrics,
                        },
                        "snapshot_ref": nav_capture["screenshot_path"],
                    }
                    if auto_accept_cookies:
                        consent = accept_cookie_banner(page=page, wait_ms=wait_ms)
                        consent_capture = self._capture_page_state(
                            page=page,
                            output_dir=output_dir,
                            stamp_prefix=stamp_prefix,
                            label=f"cookie-accept-{page_index}",
                        )
                        if consent.get("accepted"):
                            yield {
                                "event_type": "browser_cookie_accept",
                                "title": f"Accept website cookies (page {page_index})",
                                "detail": str(consent.get("label") or "Accepted cookie consent banner"),
                                "data": {
                                    "url": consent_capture["url"],
                                    "title": consent_capture["title"],
                                    "page_index": page_index,
                                    **last_cursor,
                                },
                                "snapshot_ref": consent_capture["screenshot_path"],
                            }
                        else:
                            yield {
                                "event_type": "browser_cookie_check",
                                "title": f"Check website cookies (page {page_index})",
                                "detail": "No cookie banner detected or consent already stored.",
                                "data": {
                                    "url": consent_capture["url"],
                                    "title": consent_capture["title"],
                                    "page_index": page_index,
                                    **last_cursor,
                                },
                                "snapshot_ref": consent_capture["screenshot_path"],
                            }

                for scroll_index in range(max(1, int(max_scroll_steps))):
                    metrics_before = self._page_metrics(page=page)
                    viewport_width = int(metrics_before.get("viewport_width") or 1366)
                    viewport_height = int(metrics_before.get("viewport_height") or 768)
                    cursor_x_px, cursor_y_px = safe_focus_point(
                        page=page,
                        pass_index=scroll_index + page_index,
                        viewport_width=float(viewport_width),
                        viewport_height=float(viewport_height),
                    )
                    cursor_x_px, cursor_y_px = _jitter_target(cursor_x_px, cursor_y_px, spread=24.0)
                    last_cursor = self._move_cursor(page=page, x=cursor_x_px, y=cursor_y_px)
                    scroll_delta = smart_scroll_delta(
                        metrics_before=metrics_before,
                        pass_index=scroll_index,
                        total_passes=max(1, int(max_scroll_steps)),
                    )
                    if abs(scroll_delta) >= 1:
                        scroll_delta *= movement_rng.uniform(0.83, 1.19)
                        max_delta = max(320.0, float(viewport_height) * 1.14)
                        scroll_delta = max(-max_delta, min(max_delta, scroll_delta))
                    if abs(scroll_delta) < 1:
                        continue
                    page.mouse.wheel(0, scroll_delta)
                    pause_ms = max(180, wait_ms // 2) + movement_rng.randint(0, 220)
                    page.wait_for_timeout(pause_ms)
                    metrics_after = self._page_metrics(page=page)
                    scroll_capture = self._capture_page_state(
                        page=page,
                        output_dir=output_dir,
                        stamp_prefix=stamp_prefix,
                        label=f"scroll-{page_index}-{scroll_index + 1}",
                    )
                    yield {
                        "event_type": "browser_scroll",
                        "title": f"Scroll page {page_index}",
                        "detail": f"Viewport pass {scroll_index + 1} ({'down' if scroll_delta >= 0 else 'up'})",
                        "data": {
                            "url": scroll_capture["url"],
                            "title": scroll_capture["title"],
                            "page_index": page_index,
                            "scroll_pass": scroll_index + 1,
                            "scroll_delta": round(float(scroll_delta), 2),
                            "scroll_direction": "down" if scroll_delta >= 0 else "up",
                            **last_cursor,
                            **metrics_after,
                        },
                        "snapshot_ref": scroll_capture["screenshot_path"],
                    }

                extract_capture = self._capture_page_state(
                    page=page,
                    output_dir=output_dir,
                    stamp_prefix=stamp_prefix,
                    label=f"extract-{page_index}",
                )
                visited_pages.append(
                    {
                        "url": extract_capture["url"],
                        "title": extract_capture["title"],
                        "text_excerpt": extract_capture["text_excerpt"],
                        "screenshot_path": extract_capture["screenshot_path"],
                    }
                )
                yield {
                    "event_type": "browser_extract",
                    "title": f"Extract web evidence (page {page_index})",
                    "detail": extract_capture["title"] or extract_capture["url"],
                    "data": {
                        "url": extract_capture["url"],
                        "title": extract_capture["title"],
                        "page_index": page_index,
                        "characters": len(str(extract_capture["text_excerpt"] or "")),
                        "text_excerpt": str(extract_capture["text_excerpt"] or "")[:1200],
                        **last_cursor,
                        **self._page_metrics(page=page),
                    },
                    "snapshot_ref": extract_capture["screenshot_path"],
                }
                for side_event in _emit_extract_side_events(
                    capture=extract_capture,
                    page_index=page_index,
                    cursor_payload=last_cursor,
                ):
                    yield side_event

            browser.close()

        if not visited_pages:
            return {
                "url": current_url,
                "title": str(open_capture.get("title") or ""),
                "text_excerpt": str(open_capture.get("text_excerpt") or ""),
                "screenshot_path": str(open_capture.get("screenshot_path") or ""),
                "pages": [],
            }

        combined_excerpt = "\n\n".join(
            str(row.get("text_excerpt") or "").strip() for row in visited_pages if isinstance(row, dict)
        )
        combined_excerpt = combined_excerpt[:12000]
        primary = visited_pages[0]
        final_page = visited_pages[-1]
        return {
            "url": str(final_page.get("url") or current_url),
            "title": str(primary.get("title") or final_page.get("title") or current_url),
            "text_excerpt": combined_excerpt,
            "screenshot_path": str(final_page.get("screenshot_path") or ""),
            "pages": visited_pages,
        }

    def _capture_page_state(
        self,
        *,
        page: Any,
        output_dir: Path,
        stamp_prefix: str,
        label: str,
    ) -> dict[str, str]:
        safe_label = "".join(char if char.isalnum() or char in ("-", "_") else "-" for char in label)[:40]
        suffix = datetime.now(timezone.utc).strftime("%H%M%S%f")
        screenshot_path = output_dir / f"{stamp_prefix}-{safe_label}-{suffix}.png"
        page.screenshot(path=str(screenshot_path), full_page=False)
        raw_text = page.evaluate("() => document.body ? document.body.innerText : ''")
        text_excerpt = " ".join(str(raw_text or "").split())[:4000]
        return {
            "url": str(page.url or ""),
            "title": str(page.title() or ""),
            "text_excerpt": text_excerpt,
            "screenshot_path": str(screenshot_path.resolve()),
        }

    def _move_cursor(self, *, page: Any, x: float, y: float) -> dict[str, float]:
        try:
            page.mouse.move(float(x), float(y), steps=random.randint(8, 22))
        except Exception:
            pass
        metrics = self._page_metrics(page=page)
        viewport_width = max(1.0, float(metrics.get("viewport_width") or 1366.0))
        viewport_height = max(1.0, float(metrics.get("viewport_height") or 768.0))
        return {
            "cursor_x": round((float(x) / viewport_width) * 100.0, 2),
            "cursor_y": round((float(y) / viewport_height) * 100.0, 2),
        }

    def _page_metrics(self, *, page: Any) -> dict[str, float]:
        try:
            raw = page.evaluate(
                """() => {
                    const doc = document.documentElement || {};
                    const body = document.body || {};
                    const scrollTop = Number(window.scrollY || doc.scrollTop || body.scrollTop || 0);
                    const scrollHeight = Number(doc.scrollHeight || body.scrollHeight || 0);
                    const viewportHeight = Number(window.innerHeight || doc.clientHeight || 0);
                    const viewportWidth = Number(window.innerWidth || doc.clientWidth || 0);
                    const maxScrollable = Math.max(1, scrollHeight - viewportHeight);
                    const scrollPercent = Math.max(0, Math.min(100, (scrollTop / maxScrollable) * 100));
                    return {
                        scroll_top: scrollTop,
                        scroll_height: scrollHeight,
                        viewport_height: viewportHeight,
                        viewport_width: viewportWidth,
                        scroll_percent: scrollPercent,
                    };
                }"""
            )
            if isinstance(raw, dict):
                result: dict[str, float] = {}
                for key, value in raw.items():
                    try:
                        result[str(key)] = float(value)
                    except Exception:
                        continue
                return result
        except Exception:
            return {}
        return {}
