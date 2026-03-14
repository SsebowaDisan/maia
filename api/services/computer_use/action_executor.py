"""B1-CU-02 — Action executor.

Responsibility: translate Claude's computer_20251124 tool_use blocks into
concrete Playwright calls on a BrowserSession.

Claude sends tool_use with name="computer" and an "action" field.
Supported actions mirror the Anthropic computer tool spec:
  screenshot, click, double_click, right_click, mouse_move, left_click_drag,
  type, key, scroll, cursor_position.
"""
from __future__ import annotations

import logging
from typing import Any

from .browser_session import BrowserSession

logger = logging.getLogger(__name__)


class ActionError(Exception):
    """Raised when an action cannot be executed."""


def execute_action(session: BrowserSession, tool_input: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a single computer tool_use input to the browser session.

    Returns a dict describing the outcome.  On screenshot actions the dict
    contains ``screenshot_b64``.
    """
    action: str = str(tool_input.get("action", "")).strip()

    if action == "screenshot":
        b64 = session.screenshot_b64()
        return {"action": "screenshot", "screenshot_b64": b64}

    if action in ("left_click", "click"):
        x, y = _coords(tool_input)
        session.click(x, y)
        return {"action": "click", "x": x, "y": y}

    if action == "double_click":
        x, y = _coords(tool_input)
        session.double_click(x, y)
        return {"action": "double_click", "x": x, "y": y}

    if action == "right_click":
        x, y = _coords(tool_input)
        session.right_click(x, y)
        return {"action": "right_click", "x": x, "y": y}

    if action == "mouse_move":
        x, y = _coords(tool_input)
        session.mouse_move(x, y)
        return {"action": "mouse_move", "x": x, "y": y}

    if action == "left_click_drag":
        sx, sy = _field_coords(tool_input, "start_coordinate")
        ex, ey = _field_coords(tool_input, "coordinate")
        session.mouse_down(sx, sy)
        session.mouse_up(ex, ey)
        return {"action": "left_click_drag", "from": [sx, sy], "to": [ex, ey]}

    if action == "type":
        text = str(tool_input.get("text", ""))
        session.type_text(text)
        return {"action": "type", "text_length": len(text)}

    if action == "key":
        key = str(tool_input.get("text", ""))
        session.key_press(key)
        return {"action": "key", "key": key}

    if action == "scroll":
        x, y = _coords(tool_input)
        delta_x = int(tool_input.get("delta_x") or 0)
        delta_y = int(tool_input.get("delta_y") or 0)
        # Claude uses "coordinate" + scroll_direction / scroll_amount in some specs
        direction = str(tool_input.get("scroll_direction", "")).lower()
        amount = int(tool_input.get("scroll_amount") or 3)
        if direction == "down":
            delta_y = amount * 100
        elif direction == "up":
            delta_y = -(amount * 100)
        elif direction == "right":
            delta_x = amount * 100
        elif direction == "left":
            delta_x = -(amount * 100)
        session.scroll(x, y, delta_x=delta_x, delta_y=delta_y)
        return {"action": "scroll", "x": x, "y": y, "delta_x": delta_x, "delta_y": delta_y}

    if action == "cursor_position":
        vp = session.viewport()
        return {"action": "cursor_position", "x": vp["width"] // 2, "y": vp["height"] // 2}

    raise ActionError(f"Unknown computer action: {action!r}")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _coords(tool_input: dict[str, Any]) -> tuple[int, int]:
    """Extract [x, y] from tool_input.coordinate."""
    return _field_coords(tool_input, "coordinate")


def _field_coords(tool_input: dict[str, Any], field: str) -> tuple[int, int]:
    coord = tool_input.get(field)
    if isinstance(coord, (list, tuple)) and len(coord) >= 2:
        return int(coord[0]), int(coord[1])
    raise ActionError(f"Missing or invalid '{field}' in tool input: {tool_input!r}")
