from __future__ import annotations

from api.services.agent.execution.browser_event_contract import normalize_browser_event


def test_normalize_browser_event_maps_click_action_contract() -> None:
    normalized = normalize_browser_event(
        {
            "event_type": "browser_click",
            "title": "Click",
            "detail": "selector",
            "data": {
                "url": "https://example.com",
                "selector": "button[type='submit']",
                "cursor_x": 52.2,
                "cursor_y": 64.1,
            },
            "snapshot_ref": "capture.png",
        }
    )
    data = normalized.get("data") or {}
    assert data.get("action") == "click"
    assert data.get("action_phase") == "active"
    assert data.get("action_status") == "ok"
    assert data.get("scene_surface") == "website"
    assert isinstance(data.get("action_target"), dict)
    assert data.get("action_target", {}).get("selector") == "button[type='submit']"


def test_normalize_browser_event_marks_failed_action_status() -> None:
    normalized = normalize_browser_event(
        {
            "event_type": "browser_interaction_failed",
            "title": "Failed action",
            "detail": "error",
            "data": {"url": "https://example.com"},
        }
    )
    data = normalized.get("data") or {}
    assert data.get("action_status") == "failed"
    assert data.get("action_phase") == "failed"


def test_normalize_browser_event_preserves_scroll_fields() -> None:
    normalized = normalize_browser_event(
        {
            "event_type": "browser_scroll",
            "title": "Scroll",
            "detail": "down",
            "data": {
                "scroll_direction": "down",
                "scroll_percent": 43.5,
                "cursor_x": 30.0,
                "cursor_y": 70.0,
            },
        }
    )
    data = normalized.get("data") or {}
    assert data.get("action") == "scroll"
    assert data.get("scroll_direction") == "down"
    assert data.get("scroll_percent") == 43.5
    assert data.get("cursor_x") == 30.0
    assert data.get("cursor_y") == 70.0

