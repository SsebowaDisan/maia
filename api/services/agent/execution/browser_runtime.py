from __future__ import annotations

from typing import Any

from .browser_event_contract import normalize_browser_event


class BrowserRuntime:
    """Stage 1 runtime wrapper for consistent browser event emission."""

    def __init__(self, *, scene_surface: str = "website") -> None:
        self.scene_surface = str(scene_surface or "website").strip() or "website"

    def normalize(self, event: dict[str, Any]) -> dict[str, Any]:
        return normalize_browser_event(
            event,
            default_scene_surface=self.scene_surface,
        )

