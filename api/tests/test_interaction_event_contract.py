from __future__ import annotations

from api.services.agent.execution.interaction_event_contract import normalize_interaction_event


def test_normalize_interaction_event_maps_web_result_opened() -> None:
    normalized = normalize_interaction_event(
        {
            "event_type": "web_result_opened",
            "title": "Open source",
            "detail": "example.com",
            "data": {
                "url": "https://example.com",
                "source_url": "https://example.com",
            },
        }
    )
    data = normalized.get("data") or {}
    assert data.get("action") == "click"
    assert data.get("scene_surface") == "website"
    assert data.get("action_target", {}).get("url") == "https://example.com"


def test_normalize_interaction_event_maps_pdf_scan_region() -> None:
    normalized = normalize_interaction_event(
        {
            "event_type": "pdf_scan_region",
            "title": "Scan PDF page 3",
            "detail": "Scanning visible text region",
            "data": {
                "pdf_page": 3,
                "page_index": 3,
                "page_total": 10,
            },
        }
    )
    data = normalized.get("data") or {}
    assert data.get("action") == "extract"
    assert data.get("scene_surface") == "document"
    assert data.get("action_target", {}).get("pdf_page") == 3


def test_normalize_interaction_event_preserves_browser_contract() -> None:
    normalized = normalize_interaction_event(
        {
            "event_type": "browser_navigate",
            "title": "Navigate",
            "detail": "Open page",
            "data": {"url": "https://example.com"},
        }
    )
    data = normalized.get("data") or {}
    assert data.get("action") == "navigate"
    assert data.get("scene_surface") == "website"
    assert data.get("action_target", {}).get("url") == "https://example.com"


def test_normalize_interaction_event_maps_tool_failure_to_verify() -> None:
    normalized = normalize_interaction_event(
        {
            "event_type": "tool_failed",
            "title": "Tool failed",
            "detail": "Provider timeout",
            "data": {"tool_id": "marketing.web_research"},
        }
    )
    data = normalized.get("data") or {}
    assert data.get("action") == "verify"
    assert data.get("action_status") == "failed"
