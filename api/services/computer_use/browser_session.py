"""B1-CU-01 — Playwright browser session.

Responsibility: own a single Playwright browser + page, expose screenshot and
low-level action primitives.  All Computer Use logic sits above this layer.
"""
from __future__ import annotations

import base64
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
        try:
            raw: bytes = self._page.screenshot(type="png", timeout=5_000)
        except Exception:
            try:
                raw = self._page.screenshot(
                    type="png",
                    timeout=2_000,
                    animations="disabled",
                    caret="hide",
                )
            except Exception:
                return ""
        return base64.b64encode(raw).decode("ascii")

    def screenshot_bytes(self) -> bytes:
        """Return raw PNG bytes."""
        try:
            return self._page.screenshot(type="png", timeout=5_000)
        except Exception:
            try:
                return self._page.screenshot(
                    type="png",
                    timeout=2_000,
                    animations="disabled",
                    caret="hide",
                )
            except Exception:
                return b""

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

    def scroll_metrics(self) -> dict[str, float]:
        try:
            payload = self._page.evaluate(
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
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}
        output: dict[str, float] = {}
        for key, value in payload.items():
            try:
                output[str(key)] = float(value)
            except Exception:
                continue
        return output

    def scroll_through_page(self, *, max_steps: int = 12) -> list[dict[str, float]]:
        steps: list[dict[str, float]] = []
        prior_percent = -1.0
        for _ in range(max(1, int(max_steps))):
            before = self.scroll_metrics()
            viewport_height = int(before.get("viewport_height") or VIEWPORT_HEIGHT)
            viewport_width = int(before.get("viewport_width") or VIEWPORT_WIDTH)
            delta = max(220, int(viewport_height * 0.88))
            self.scroll(viewport_width // 2, viewport_height // 2, delta_y=delta)
            try:
                self._page.wait_for_timeout(140)
            except Exception:
                pass
            after = self.scroll_metrics()
            moved = float(after.get("scroll_top", 0.0) - before.get("scroll_top", 0.0))
            percent = float(after.get("scroll_percent") or 0.0)
            steps.append(
                {
                    "scroll_top": float(after.get("scroll_top") or 0.0),
                    "scroll_percent": percent,
                    "moved": moved,
                }
            )
            if percent >= 99.3:
                break
            if abs(moved) < 2.0:
                break
            if prior_percent >= 0.0 and abs(percent - prior_percent) < 0.2:
                break
            prior_percent = percent
        return steps

    def type_text(self, text: str) -> None:
        self._page.keyboard.type(text)

    def key_press(self, key: str) -> None:
        """Press a named key (e.g. 'Return', 'Escape', 'ctrl+a')."""
        self._page.keyboard.press(key)

    def extract_page_text(self, *, max_chars: int = 12000) -> str:
        try:
            payload = self._page.evaluate(
                """() => {
                    const read = (node) => {
                        if (!node) return "";
                        return (node.innerText || node.textContent || "").replace(/\\s+/g, " ").trim();
                    };
                    const article = read(document.querySelector("article"));
                    const main = read(document.querySelector("main"));
                    const body = read(document.body);
                    return article || main || body || "";
                }"""
            )
        except Exception:
            return ""
        text = " ".join(str(payload or "").split()).strip()
        if len(text) <= max(1, int(max_chars)):
            return text
        return text[: max(1, int(max_chars))].rstrip()

    def keyword_regions(self, *, keywords: list[str], limit: int = 8) -> list[dict[str, float | str]]:
        terms = [str(item).strip().lower() for item in keywords if str(item).strip()]
        if not terms:
            return []
        try:
            payload = self._page.evaluate(
                """(payload) => {
                    const values = Array.isArray(payload?.values) ? payload.values : [];
                    const maxItems = Math.max(1, Number(payload?.maxItems || 1));
                    const nodes = Array.from(document.querySelectorAll("h1,h2,h3,h4,p,li,a,button,span"));
                    const out = [];
                    const seen = new Set();
                    for (const term of values || []) {
                        for (const el of nodes) {
                            const text = (el.innerText || el.textContent || "").toLowerCase();
                            if (!text.includes(term)) continue;
                            try { el.scrollIntoView({ block: "center", inline: "nearest" }); } catch {}
                            const rect = el.getBoundingClientRect();
                            if (rect.width < 20 || rect.height < 10) continue;
                            const x = Math.max(0, Math.min(100, (rect.left / Math.max(1, window.innerWidth)) * 100));
                            const y = Math.max(0, Math.min(100, (rect.top / Math.max(1, window.innerHeight)) * 100));
                            const width = Math.max(2, Math.min(100, (rect.width / Math.max(1, window.innerWidth)) * 100));
                            const height = Math.max(2, Math.min(100, (rect.height / Math.max(1, window.innerHeight)) * 100));
                            const signature = `${term}:${Math.round(x)}:${Math.round(y)}`;
                            if (seen.has(signature)) continue;
                            seen.add(signature);
                            out.push({ keyword: term, x, y, width, height });
                            break;
                        }
                        if (out.length >= Math.max(1, Number(maxItems || 1))) break;
                    }
                    return out;
                }""",
                {"values": terms[: max(1, int(limit))], "maxItems": int(limit)},
            )
        except Exception:
            return []
        if not isinstance(payload, list):
            return []
        rows: list[dict[str, float | str]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            keyword = str(item.get("keyword") or "").strip()
            if not keyword:
                continue
            rows.append(
                {
                    "keyword": keyword,
                    "x": max(0.0, min(100.0, float(item.get("x") or 0.0))),
                    "y": max(0.0, min(100.0, float(item.get("y") or 0.0))),
                    "width": max(1.0, min(100.0, float(item.get("width") or 1.0))),
                    "height": max(1.0, min(100.0, float(item.get("height") or 1.0))),
                }
            )
        return rows

    def sentence_regions(self, *, terms: list[str], limit: int = 8) -> list[dict[str, float | str]]:
        values = [str(item).strip().lower() for item in terms if str(item).strip()]
        if not values:
            return []
        try:
            payload = self._page.evaluate(
                """(payload) => {
                    const terms = Array.isArray(payload?.terms) ? payload.terms : [];
                    const maxItems = Math.max(1, Number(payload?.maxItems || 1));
                    const nodes = Array.from(document.querySelectorAll("h1,h2,h3,h4,p,li,td"));
                    const out = [];
                    const seen = new Set();

                    const firstSentenceWithTerm = (rawText, term) => {
                        const compact = String(rawText || "").replace(/\\s+/g, " ").trim();
                        if (!compact) return "";
                        const chunks = compact.match(/[^.!?]+[.!?]?/g) || [compact];
                        for (const chunk of chunks) {
                            const sentence = String(chunk || "").trim();
                            if (sentence.toLowerCase().includes(term)) return sentence;
                        }
                        return chunks[0] ? String(chunks[0]).trim() : compact;
                    };

                    for (const term of terms) {
                        if (!term) continue;
                        for (const el of nodes) {
                            const raw = String(el.innerText || el.textContent || "");
                            const lowered = raw.toLowerCase();
                            if (!lowered.includes(term)) continue;
                            const sentence = firstSentenceWithTerm(raw, term);
                            if (!sentence) continue;
                            const signature = `${term}:${sentence.slice(0, 120)}`;
                            if (seen.has(signature)) continue;
                            seen.add(signature);
                            try { el.scrollIntoView({ block: "center", inline: "nearest" }); } catch {}
                            const rect = el.getBoundingClientRect();
                            if (rect.width < 20 || rect.height < 10) continue;
                            const x = Math.max(0, Math.min(100, (rect.left / Math.max(1, window.innerWidth)) * 100));
                            const y = Math.max(0, Math.min(100, (rect.top / Math.max(1, window.innerHeight)) * 100));
                            const width = Math.max(2, Math.min(100, (rect.width / Math.max(1, window.innerWidth)) * 100));
                            const height = Math.max(2, Math.min(100, (rect.height / Math.max(1, window.innerHeight)) * 100));
                            out.push({ keyword: term, sentence, x, y, width, height });
                            break;
                        }
                        if (out.length >= maxItems) break;
                    }
                    return out;
                }""",
                {"terms": values[: max(1, int(limit))], "maxItems": int(limit)},
            )
        except Exception:
            return []
        if not isinstance(payload, list):
            return []
        rows: list[dict[str, float | str]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            sentence = " ".join(str(item.get("sentence") or "").split()).strip()
            keyword = str(item.get("keyword") or "").strip().lower()
            if not sentence or not keyword or len(sentence) < 24:
                continue
            rows.append(
                {
                    "keyword": keyword,
                    "sentence": sentence[:220],
                    "x": max(0.0, min(100.0, float(item.get("x") or 0.0))),
                    "y": max(0.0, min(100.0, float(item.get("y") or 0.0))),
                    "width": max(1.0, min(100.0, float(item.get("width") or 1.0))),
                    "height": max(1.0, min(100.0, float(item.get("height") or 1.0))),
                }
            )
        return rows

    def apply_highlight_regions(self, *, regions: list[dict[str, float | str]], color: str = "yellow") -> None:
        safe_rows = [row for row in regions if isinstance(row, dict)]
        if not safe_rows:
            return
        fill = "rgba(255, 214, 10, 0.36)" if str(color).strip().lower() != "green" else "rgba(34, 197, 94, 0.30)"
        self._page.evaluate(
            """(payload) => {
                const rows = Array.isArray(payload?.rows) ? payload.rows : [];
                const fillColor = String(payload?.fillColor || "rgba(255,214,10,0.36)");
                document.querySelectorAll("[data-maia-highlight='true']").forEach((node) => node.remove());
                for (const row of rows || []) {
                    const box = document.createElement("div");
                    box.setAttribute("data-maia-highlight", "true");
                    box.style.position = "fixed";
                    box.style.pointerEvents = "none";
                    box.style.left = `${Math.max(0, Number(row.x || 0))}%`;
                    box.style.top = `${Math.max(0, Number(row.y || 0))}%`;
                    box.style.width = `${Math.max(1, Number(row.width || 1))}%`;
                    box.style.height = `${Math.max(1, Number(row.height || 1))}%`;
                    box.style.border = "2px solid rgba(245, 158, 11, 0.92)";
                    box.style.background = fillColor;
                    box.style.borderRadius = "8px";
                    box.style.boxSizing = "border-box";
                    box.style.zIndex = "2147483646";
                    document.body.appendChild(box);
                }
            }""",
            {"rows": safe_rows[:12], "fillColor": fill},
        )

    # ── Metadata ──────────────────────────────────────────────────────────────

    def current_url(self) -> str:
        return self._page.url

    def page_title(self) -> str:
        return self._page.title()

    def viewport(self) -> dict[str, int]:
        return {"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT}

    def dom_snapshot(self) -> str | None:
        """Return a numbered text index of visible interactive DOM elements.

        Used alongside screenshots to give the vision model precise element
        coordinates without relying purely on visual inference.
        Returns None if the page is not ready or evaluation fails.
        """
        from .dom_snapshot import get_dom_snapshot
        return get_dom_snapshot(self._page)
