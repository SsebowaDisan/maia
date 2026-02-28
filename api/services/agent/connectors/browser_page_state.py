from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import random
from typing import Any


def playwright_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except Exception:
        return False


def capture_page_state(
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


def page_metrics(*, page: Any) -> dict[str, float]:
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


def move_cursor(*, page: Any, x: float, y: float) -> dict[str, float]:
    try:
        page.mouse.move(float(x), float(y), steps=random.randint(8, 22))
    except Exception:
        pass
    metrics = page_metrics(page=page)
    viewport_width = max(1.0, float(metrics.get("viewport_width") or 1366.0))
    viewport_height = max(1.0, float(metrics.get("viewport_height") or 768.0))
    return {
        "cursor_x": round((float(x) / viewport_width) * 100.0, 2),
        "cursor_y": round((float(y) / viewport_height) * 100.0, 2),
    }
