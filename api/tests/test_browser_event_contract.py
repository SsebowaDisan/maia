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


def test_normalize_browser_event_maps_contact_fill_variants() -> None:
    normalized = normalize_browser_event(
        {
            "event_type": "browser_contact_fill_email",
            "title": "Fill email",
            "detail": "contact email",
            "data": {
                "field": "email",
                "field_label": "Work email",
            },
        }
    )
    data = normalized.get("data") or {}
    assert data.get("action") == "type"
    assert data.get("action_target", {}).get("field") == "email"
    assert data.get("action_target", {}).get("field_label") == "Work email"


def test_normalize_browser_event_maps_open_to_navigate_action() -> None:
    normalized = normalize_browser_event(
        {
            "event_type": "browser_open",
            "title": "Open site",
            "detail": "https://example.com",
            "data": {"url": "https://example.com"},
        }
    )
    data = normalized.get("data") or {}
    assert data.get("action") == "navigate"
    assert data.get("action_target", {}).get("url") == "https://example.com"


def test_normalize_browser_event_maps_contact_handoff_event_to_verify() -> None:
    normalized = normalize_browser_event(
        {
            "event_type": "browser_contact_human_verification_required",
            "title": "Human verification required",
            "detail": "Challenge detected",
            "data": {"url": "https://example.com/contact"},
        }
    )
    data = normalized.get("data") or {}
    assert data.get("action") == "verify"
    assert data.get("action_status") == "ok"


def test_normalize_browser_event_propagates_owner_role_and_v2_schema() -> None:
    normalized = normalize_browser_event(
        {
            "event_type": "browser_click",
            "title": "Click CTA",
            "detail": "submit",
            "data": {
                "selector": "button.submit",
                "__owner_role": "browser",
            },
        }
    )
    data = normalized.get("data") or {}
    assert data.get("owner_role") == "browser"
    assert data.get("event_schema_version") == "interaction_v2"
    assert data.get("event_family") == "browser"
    assert data.get("event_render_mode") in {"animate_live", "summarize", "compress", "replay_later"}
    assert isinstance(data.get("event_envelope"), dict)


def test_normalize_browser_event_maps_zoom_to_region_action() -> None:
    normalized = normalize_browser_event(
        {
            "event_type": "browser_zoom_to_region",
            "title": "Zoom to region",
            "detail": "Inspect totals table",
            "data": {
                "zoom_level": 2.0,
                "content_density": 0.82,
                "confidence": 0.41,
                "target_region": {"x": 120, "y": 220, "width": 300, "height": 160},
                "zoom_reason": "small text",
            },
        }
    )
    data = normalized.get("data") or {}
    assert data.get("action") == "zoom_to_region"
    assert data.get("scene_surface") == "website"
    assert data.get("action_target", {}).get("zoom_level") == 2.0
    assert isinstance(data.get("action_target", {}).get("target_region"), dict)
    assert data.get("zoom_policy_version") == "zoom_policy_v1"
    assert data.get("zoom_policy_triggered") is True
    assert "text_density_high" in list(data.get("zoom_policy_triggers") or [])


def test_normalize_browser_event_marks_zoom_recommendation_for_low_confidence_extract() -> None:
    normalized = normalize_browser_event(
        {
            "event_type": "browser_extract",
            "title": "Extract facts",
            "detail": "Capture page summary",
            "data": {
                "confidence": 0.2,
                "content_density": 0.9,
            },
        }
    )
    data = normalized.get("data") or {}
    assert data.get("zoom_policy_recommended") is True
    assert data.get("zoom_policy_triggered") is False
    assert "confidence_low" in list(data.get("zoom_policy_triggers") or [])


def test_normalize_browser_event_derives_semantic_find_results() -> None:
    normalized = normalize_browser_event(
        {
            "event_type": "browser_find_in_page",
            "title": "Find in page",
            "detail": "operating margin",
            "data": {
                "find_query": "operating margin",
                "keywords": ["operating margin", "gross margin", "net margin"],
                "match_count": 4,
            },
        }
    )
    data = normalized.get("data") or {}
    results = list(data.get("semantic_find_results") or [])
    assert data.get("semantic_find_query") == "operating margin"
    assert data.get("semantic_find_source") in {"keywords", "semantic_find_terms"}
    assert len(results) >= 1
    assert results[0].get("term")
    assert isinstance(results[0].get("confidence"), float)


def test_normalize_browser_event_sets_compare_mode_payload() -> None:
    normalized = normalize_browser_event(
        {
            "event_type": "browser_compare_sources",
            "title": "Compare sources",
            "detail": "Cross-check claims",
            "data": {
                "scene_surface": "website",
                "compare_left": "Source A revenue growth: 31%",
                "compare_right": "Source B revenue growth: 29%",
                "compare_verdict": "Minor discrepancy",
                "compare_confidence": 0.74,
            },
        }
    )
    data = normalized.get("data") or {}
    assert data.get("compare_mode_enabled") is True
    assert data.get("compare_left")
    assert data.get("compare_right")
    assert isinstance(data.get("compare_mode"), dict)


def test_normalize_browser_event_flags_verifier_conflict_for_low_confidence_verify() -> None:
    normalized = normalize_browser_event(
        {
            "event_type": "browser_verify",
            "title": "Verify claim support",
            "detail": "Checking evidence",
            "data": {
                "action": "verify",
                "verification_confidence": 0.49,
                "citation_support_ratio": 0.44,
            },
        }
    )
    data = normalized.get("data") or {}
    assert data.get("verifier_conflict") is True
    assert data.get("verifier_recheck_required") is True
    assert data.get("zoom_escalation_requested") is True
