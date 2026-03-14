"""B1-CU-01 — Playwright browser session.

Responsibility: own a single Playwright browser + page, expose screenshot and
low-level action primitives.  All Computer Use logic sits above this layer.
"""
from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Viewport used for Computer Use screenshots (matches Claude computer tool spec)
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 800


@dataclass
class BrowserSession:
    session_id: str
    _playwright: Any = field(default=None, repr=False)
    _browser: Any = field(default=None, repr=False)
    _context: Any = field(default=None, repr=False)
    _page: Any = field(default=None, repr=False)
    _closed: bool = False

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Launch Playwright headless Chromium and open a blank page."""
        from playwright.sync_api import sync_playwright  # type: ignore[import]

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                f"--window-size={VIEWPORT_WIDTH},{VIEWPORT_HEIGHT}",
            ],
        )
        self._context = self._browser.new_context(
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/134.0.0.0 Safari/537.36"
            ),
        )
        self._page = self._context.new_page()
        logger.info("BrowserSession %s started", self.session_id)

    def close(self) -> None:
        """Shut down the browser and Playwright cleanly."""
        if self._closed:
            return
        self._closed = True
        try:
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            logger.debug("BrowserSession %s close error", self.session_id, exc_info=True)
        logger.info("BrowserSession %s closed", self.session_id)

    # ── Navigation ─────────────────────────────────────────────────────────────

    def navigate(self, url: str, *, timeout_ms: int = 30_000) -> str:
        """Navigate to *url* and return the page title."""
        self._page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        return self._page.title()

    # ── Screenshot ────────────────────────────────────────────────────────────

    def screenshot_b64(self) -> str:
        """Return a full-page screenshot encoded as base64 PNG."""
        raw: bytes = self._page.screenshot(type="png")
        return base64.b64encode(raw).decode("ascii")

    def screenshot_bytes(self) -> bytes:
        """Return raw PNG bytes."""
        return self._page.screenshot(type="png")

    # ── Actions ────────────────────────────────────────────────────────────────

    def click(self, x: int, y: int) -> None:
        self._page.mouse.click(x, y)

    def double_click(self, x: int, y: int) -> None:
        self._page.mouse.dblclick(x, y)

    def right_click(self, x: int, y: int) -> None:
        self._page.mouse.click(x, y, button="right")

    def mouse_move(self, x: int, y: int) -> None:
        self._page.mouse.move(x, y)

    def mouse_down(self, x: int, y: int) -> None:
        self._page.mouse.move(x, y)
        self._page.mouse.down()

    def mouse_up(self, x: int, y: int) -> None:
        self._page.mouse.move(x, y)
        self._page.mouse.up()

    def scroll(self, x: int, y: int, *, delta_x: int = 0, delta_y: int = 0) -> None:
        self._page.mouse.move(x, y)
        self._page.mouse.wheel(delta_x, delta_y)

    def type_text(self, text: str) -> None:
        self._page.keyboard.type(text)

    def key_press(self, key: str) -> None:
        """Press a named key (e.g. 'Return', 'Escape', 'ctrl+a')."""
        self._page.keyboard.press(key)

    # ── Metadata ──────────────────────────────────────────────────────────────

    def current_url(self) -> str:
        return self._page.url

    def page_title(self) -> str:
        return self._page.title()

    def viewport(self) -> dict[str, int]:
        return {"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT}
