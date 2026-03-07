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


def test_normalize_interaction_event_carries_owner_role_and_v2_schema() -> None:
    normalized = normalize_interaction_event(
        {
            "event_type": "doc_insert_text",
            "title": "Insert text",
            "detail": "Write findings",
            "data": {
                "role": "writer",
                "source_name": "Draft",
            },
        }
    )
    data = normalized.get("data") or {}
    assert data.get("owner_role") == "writer"
    assert data.get("event_schema_version") == "interaction_v2"
    assert data.get("event_family") == "doc"
    assert data.get("event_render_mode") in {"animate_live", "summarize", "compress", "replay_later"}
    assert isinstance(data.get("event_envelope"), dict)


def test_normalize_interaction_event_prefers_default_surface_for_doc_events() -> None:
    normalized = normalize_interaction_event(
        {
            "event_type": "doc_copy_clipboard",
            "title": "Copy",
            "detail": "Copied snippet",
            "data": {"clipboard_text": "Axon summary"},
        },
        default_scene_surface="document",
    )
    data = normalized.get("data") or {}
    assert data.get("scene_surface") == "document"
    assert data.get("action") == "extract"


def test_normalize_interaction_event_maps_drive_search_completed() -> None:
    normalized = normalize_interaction_event(
        {
            "event_type": "drive.search_completed",
            "title": "Drive search",
            "detail": "Quarterly report",
            "data": {"query": "quarterly report", "count": 4},
        },
        default_scene_surface="document",
    )
    data = normalized.get("data") or {}
    assert data.get("scene_surface") == "document"
    assert data.get("action") == "extract"


def test_normalize_interaction_event_maps_pdf_zoom_to_region() -> None:
    normalized = normalize_interaction_event(
        {
            "event_type": "pdf_zoom_to_region",
            "title": "Zoom PDF",
            "detail": "Inspect footnote",
            "data": {
                "pdf_page": 5,
                "zoom_level": 2.4,
                "content_density": 0.88,
                "verification_confidence": 0.52,
                "target_region": {"x": 40, "y": 80, "width": 240, "height": 110},
            },
        }
    )
    data = normalized.get("data") or {}
    assert data.get("action") == "zoom_to_region"
    assert data.get("scene_surface") == "document"
    assert data.get("action_target", {}).get("pdf_page") == 5
    assert data.get("action_target", {}).get("zoom_level") == 2.4
    assert data.get("zoom_policy_version") == "zoom_policy_v1"
    assert data.get("zoom_policy_triggered") is True
    assert "confidence_low" in list(data.get("zoom_policy_triggers") or [])


def test_normalize_interaction_event_maps_sheet_dot_zoom_event() -> None:
    normalized = normalize_interaction_event(
        {
            "event_type": "sheet.zoom_in",
            "title": "Zoom in sheet",
            "detail": "Review pivot totals",
            "data": {"zoom_level": 1.5},
        },
        default_scene_surface="google_sheets",
    )
    data = normalized.get("data") or {}
    assert data.get("action") == "zoom_in"
    assert data.get("scene_surface") == "google_sheets"


def test_normalize_interaction_event_maps_api_surface_with_plugin_hints() -> None:
    normalized = normalize_interaction_event(
        {
            "event_type": "api_call_started",
            "title": "Fetch analytics",
            "detail": "Load report data",
            "data": {
                "connector_id": "google_analytics",
                "action_id": "analytics.fetch_report",
            },
        },
        default_scene_surface="system",
    )
    data = normalized.get("data") or {}
    assert data.get("scene_surface") == "api"
    assert data.get("event_family") == "api"
    assert data.get("plugin_connector_label") == "Google Analytics"
    assert data.get("plugin_action_title") == "Fetch report"


def test_normalize_interaction_event_derives_semantic_find_from_query_variants() -> None:
    normalized = normalize_interaction_event(
        {
            "event_type": "retrieval_query_rewrite",
            "title": "Rewrite search queries",
            "detail": "Prepared 3 query variants",
            "data": {
                "query_variants": [
                    "machine learning business applications",
                    "machine learning supervised algorithms healthcare",
                    "machine learning current trends 2026",
                ],
            },
        }
    )
    data = normalized.get("data") or {}
    results = list(data.get("semantic_find_results") or [])
    assert data.get("semantic_find_query")
    assert data.get("semantic_find_source") == "query_variants"
    assert len(results) == 3
    assert results[0].get("rank") == 1


def test_normalize_interaction_event_sets_compare_mode_for_pdf_compare() -> None:
    normalized = normalize_interaction_event(
        {
            "event_type": "pdf_compare_regions",
            "title": "Compare PDF regions",
            "detail": "Compare Q3 vs Q4",
            "data": {
                "scene_surface": "document",
                "compare_region_a": "Q3 margin 18%",
                "compare_region_b": "Q4 margin 22%",
                "compare_confidence": 0.83,
            },
        }
    )
    data = normalized.get("data") or {}
    assert data.get("compare_mode_enabled") is True
    assert data.get("compare_left") == "Q3 margin 18%"
    assert data.get("compare_right") == "Q4 margin 22%"
    assert isinstance(data.get("compare_mode"), dict)


def test_normalize_interaction_event_flags_verifier_conflict_for_low_support() -> None:
    normalized = normalize_interaction_event(
        {
            "event_type": "verification_check",
            "title": "Verify support",
            "detail": "Assessing evidence support",
            "data": {
                "action": "verify",
                "citation_support_ratio": 0.5,
                "citation_support_threshold": 0.65,
            },
        }
    )
    data = normalized.get("data") or {}
    assert data.get("verifier_conflict") is True
    assert data.get("verifier_recheck_required") is True
    assert data.get("zoom_escalation_requested") is True
