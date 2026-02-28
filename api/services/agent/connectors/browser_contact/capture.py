from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def capture_page_state(
    *,
    page: Any,
    label: str,
    output_dir: Path,
    stamp_prefix: str,
) -> dict[str, str]:
    safe_label = "".join(
        char if char.isalnum() or char in ("-", "_") else "-" for char in label
    )[:40]
    suffix = datetime.now(timezone.utc).strftime("%H%M%S%f")
    screenshot_path = output_dir / f"{stamp_prefix}-{safe_label}-{suffix}.png"
    page.screenshot(path=str(screenshot_path), full_page=False)
    return {
        "url": str(page.url or ""),
        "title": str(page.title() or ""),
        "screenshot_path": str(screenshot_path.resolve()),
    }


def move_cursor(
    *,
    page: Any,
    locator: Any | None = None,
    x: float = 120,
    y: float = 120,
) -> dict[str, float]:
    cursor_x = float(x)
    cursor_y = float(y)
    if locator is not None:
        try:
            box = locator.bounding_box()
            if box:
                cursor_x = float(box.get("x", cursor_x)) + min(
                    80.0, float(box.get("width", 0.0)) / 2.0
                )
                cursor_y = float(box.get("y", cursor_y)) + min(
                    16.0, float(box.get("height", 0.0)) / 2.0
                )
        except Exception:
            pass
    try:
        page.mouse.move(cursor_x, cursor_y, steps=14)
    except Exception:
        pass
    viewport = page.viewport_size or {"width": 1366, "height": 768}
    width = max(1.0, float(viewport.get("width") or 1366.0))
    height = max(1.0, float(viewport.get("height") or 768.0))
    return {
        "cursor_x": round((cursor_x / width) * 100.0, 2),
        "cursor_y": round((cursor_y / height) * 100.0, 2),
    }
