from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Generator
from urllib.parse import urljoin, urlparse

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
    ) -> dict[str, Any]:
        stream = self.browse_live_stream(
            url=url,
            timeout_ms=timeout_ms,
            wait_ms=wait_ms,
            max_pages=1,
            max_scroll_steps=1,
            auto_accept_cookies=auto_accept_cookies,
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

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 768})

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(max(200, wait_ms))
            except Exception as exc:
                browser.close()
                raise ConnectorError(f"Failed to open URL: {url}. {exc}") from exc

            open_cursor = self._move_cursor(page=page, x=124, y=88)
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
                consent = self._accept_cookie_banner(page=page, wait_ms=wait_ms)
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
            quick_cursor = self._move_cursor(page=page, x=220, y=192)
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

            current_url = str(open_capture["url"] or url)
            targets = [current_url]
            targets.extend(
                self._extract_same_origin_links(
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
                    last_cursor = self._move_cursor(page=page, x=138, y=106)
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
                        consent = self._accept_cookie_banner(page=page, wait_ms=wait_ms)
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
                    cursor_x_px = max(
                        48,
                        min(
                            viewport_width - 48,
                            140 + ((scroll_index + page_index) * 170) % max(220, viewport_width - 120),
                        ),
                    )
                    cursor_y_px = max(
                        96,
                        min(
                            viewport_height - 60,
                            170 + ((scroll_index + page_index) * 90) % max(200, viewport_height - 120),
                        ),
                    )
                    last_cursor = self._move_cursor(page=page, x=cursor_x_px, y=cursor_y_px)
                    page.mouse.wheel(0, 900)
                    page.wait_for_timeout(max(200, wait_ms // 2))
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
                        "detail": f"Viewport pass {scroll_index + 1}",
                        "data": {
                            "url": scroll_capture["url"],
                            "title": scroll_capture["title"],
                            "page_index": page_index,
                            "scroll_pass": scroll_index + 1,
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
            page.mouse.move(float(x), float(y), steps=14)
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

    def _extract_same_origin_links(
        self,
        *,
        page: Any,
        origin_url: str,
        limit: int,
    ) -> list[str]:
        if limit <= 0:
            return []
        parsed_origin = urlparse(origin_url)
        origin_host = (parsed_origin.hostname or "").lower()
        if not origin_host:
            return []

        hrefs: list[str] = page.evaluate(
            """() => Array.from(document.querySelectorAll('a[href]'))
                .map((element) => element.getAttribute('href') || '')
                .filter(Boolean)
            """
        )
        targets: list[str] = []
        seen: set[str] = {origin_url}
        for href in hrefs:
            candidate = urljoin(origin_url, str(href))
            parsed = urlparse(candidate)
            if parsed.scheme not in {"http", "https"}:
                continue
            host = (parsed.hostname or "").lower()
            if host != origin_host:
                continue
            normalized = parsed._replace(fragment="").geturl()
            if normalized in seen:
                continue
            seen.add(normalized)
            targets.append(normalized)
            if len(targets) >= limit:
                break
        return targets

    def _accept_cookie_banner(self, *, page: Any, wait_ms: int = 1200) -> dict[str, Any]:
        """
        Best-effort cookie consent acceptance for common CMP banners.
        """
        selectors = [
            "#onetrust-accept-btn-handler",
            "button#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
            "button:has-text('ALLOW ALL COOKIES')",
            "button:has-text('Allow all cookies')",
            "button:has-text('Accept all cookies')",
            "button:has-text('Accept all')",
            "button:has-text('Allow all')",
            "button:has-text('I agree')",
            "button:has-text('Tout accepter')",
            "button:has-text('Accepter')",
            "button:has-text('Akzeptieren')",
            "button:has-text('Accepteer')",
            "button:has-text('Alle cookies toestaan')",
            "button:has-text('Aceptar todo')",
        ]
        label_regex = re.compile(
            r"(accept|allow|agree|consent|accepter|akzeptieren|accepteer|toestaan|aceptar|tout accepter)",
            re.IGNORECASE,
        )

        def _try_click(locator: Any, label: str) -> bool:
            try:
                if locator.count() <= 0:
                    return False
                candidate = locator.first
                if hasattr(candidate, "is_visible") and not candidate.is_visible():
                    return False
                candidate.click(timeout=2000)
                page.wait_for_timeout(max(120, min(800, wait_ms)))
                return True
            except Exception:
                return False

        # First try highly-specific selectors.
        for selector in selectors:
            if _try_click(page.locator(selector), selector):
                return {"accepted": True, "label": selector}

        # Then try role-based scanning in page + iframes.
        frames = [page.main_frame] + list(page.frames)
        for frame in frames:
            try:
                buttons = frame.get_by_role("button")
                total = min(buttons.count(), 40)
            except Exception:
                continue
            for index in range(total):
                try:
                    button = buttons.nth(index)
                    text = str(button.inner_text(timeout=300) or "").strip()
                except Exception:
                    continue
                if not text or not label_regex.search(text):
                    continue
                if _try_click(button, text):
                    return {"accepted": True, "label": text}

        return {"accepted": False}
