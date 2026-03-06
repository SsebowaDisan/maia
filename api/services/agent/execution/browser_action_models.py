from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

BrowserActionName = Literal[
    "navigate",
    "hover",
    "click",
    "type",
    "scroll",
    "extract",
    "verify",
    "open",
    "other",
]
BrowserActionPhase = Literal["start", "active", "completed", "failed"]


@dataclass(slots=True)
class BrowserActionEvent:
    event_type: str
    action: BrowserActionName
    phase: BrowserActionPhase
    status: Literal["ok", "failed"]
    scene_surface: str = "website"
    cursor_x: float | None = None
    cursor_y: float | None = None
    scroll_direction: str = ""
    scroll_percent: float | None = None
    target: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_data(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "scene_surface": self.scene_surface or "website",
            "action": self.action,
            "action_phase": self.phase,
            "action_status": self.status,
            "action_target": dict(self.target),
            "action_metadata": dict(self.metadata),
            "event_schema_version": "browser_action_v1",
        }
        if isinstance(self.cursor_x, (int, float)):
            payload["cursor_x"] = float(self.cursor_x)
        if isinstance(self.cursor_y, (int, float)):
            payload["cursor_y"] = float(self.cursor_y)
        if self.scroll_direction:
            payload["scroll_direction"] = str(self.scroll_direction).strip().lower()
        if isinstance(self.scroll_percent, (int, float)):
            payload["scroll_percent"] = max(0.0, min(100.0, float(self.scroll_percent)))
        return payload

