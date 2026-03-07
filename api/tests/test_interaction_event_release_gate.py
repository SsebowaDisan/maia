from __future__ import annotations

from api.services.agent.execution.interaction_event_contract import normalize_interaction_event


def test_interaction_release_gate_core_surfaces_and_actions() -> None:
    coverage_rows = [
        (
            "browser_click",
            {"url": "https://example.com", "selector": "a.result-link"},
            "website",
            "click",
            "website",
        ),
        (
            "pdf_scan_region",
            {"pdf_page": 2, "page_index": 2, "page_total": 6},
            "document",
            "extract",
            "document",
        ),
        (
            "pdf_zoom_to_region",
            {"pdf_page": 2, "zoom_level": 2.1, "target_region": {"x": 10, "y": 12, "width": 100, "height": 50}},
            "document",
            "zoom_to_region",
            "document",
        ),
        (
            "doc_insert_text",
            {"document_id": "doc-123", "source_url": "https://docs.google.com/document/d/doc-123/edit"},
            "google_docs",
            "type",
            "google_docs",
        ),
        (
            "sheets.append_completed",
            {"spreadsheet_id": "sheet-123", "source_url": "https://docs.google.com/spreadsheets/d/sheet-123/edit"},
            "google_sheets",
            "verify",
            "google_sheets",
        ),
        (
            "sheet_zoom_in",
            {"zoom_level": 1.25},
            "google_sheets",
            "zoom_in",
            "google_sheets",
        ),
        (
            "email_set_subject",
            {"subject": "Weekly update"},
            "email",
            "type",
            "email",
        ),
        (
            "email_sent",
            {"to": "recipient@example.com", "subject": "Weekly update"},
            "email",
            "verify",
            "email",
        ),
        (
            "drive.search_completed",
            {"query": "quarterly report", "count": 3},
            "document",
            "extract",
            "document",
        ),
    ]
    for event_type, data, default_surface, expected_action, expected_surface in coverage_rows:
        normalized = normalize_interaction_event(
            {
                "event_type": event_type,
                "title": "Interaction",
                "detail": "coverage",
                "data": data,
            },
            default_scene_surface=default_surface,
        )
        payload = normalized.get("data") or {}
        assert payload.get("event_schema_version") == "interaction_v2"
        assert payload.get("action") == expected_action
        assert payload.get("scene_surface") == expected_surface
        assert payload.get("action") != "other"
