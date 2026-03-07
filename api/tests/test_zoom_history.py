from __future__ import annotations

from api.services.agent.zoom_history import enrich_event_data_with_zoom


def test_enrich_event_data_with_zoom_adds_refs_and_zoom_event() -> None:
    payload = enrich_event_data_with_zoom(
        data={
            "action": "zoom_to_region",
            "scene_surface": "document",
            "zoom_level": 2.0,
            "zoom_reason": "verifier escalation",
        },
        event_type="pdf_zoom_to_region",
        event_id="evt-zoom-1",
        event_index=7,
        timestamp="2026-03-07T15:10:30Z",
        graph_node_id="node-1",
        scene_ref="scene.pdf.reader",
    )
    assert payload["graph_node_ids"] == ["node-1"]
    assert payload["scene_refs"] == ["scene.pdf.reader"]
    assert payload["event_refs"] == ["evt-zoom-1"]
    assert isinstance(payload.get("zoom_event"), dict)
    assert payload["zoom_event"]["event_ref"] == "evt-zoom-1"
    assert payload["zoom_event"]["event_index"] == 7
    assert payload["zoom_event"]["graph_node_id"] == "node-1"
    assert payload["zoom_event"]["scene_ref"] == "scene.pdf.reader"
    assert isinstance(payload.get("zoom_history"), list)
    assert payload["zoom_history"][0]["action"] == "zoom_to_region"


def test_enrich_event_data_with_zoom_keeps_non_zoom_refs_only() -> None:
    payload = enrich_event_data_with_zoom(
        data={
            "action": "extract",
            "graph_node_id": "node-9",
            "scene_ref": "scene.browser.main",
        },
        event_type="browser_extract",
        event_id="evt-9",
        event_index=12,
    )
    assert payload["graph_node_ids"] == ["node-9"]
    assert payload["scene_refs"] == ["scene.browser.main"]
    assert payload["event_refs"] == ["evt-9"]
    assert "zoom_event" not in payload
    assert "zoom_history" not in payload
