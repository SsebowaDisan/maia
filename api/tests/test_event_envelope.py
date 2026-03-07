from __future__ import annotations

from api.services.agent.event_envelope import (
    EVENT_ENVELOPE_VERSION,
    apply_workspace_mode_policy,
    build_event_envelope,
    infer_event_family,
    infer_event_priority,
    merge_event_envelope_data,
)


def test_infer_event_family_maps_core_surfaces() -> None:
    assert infer_event_family(event_type="browser_click", stage="ui_action") == "browser"
    assert infer_event_family(event_type="pdf_scan_region", stage="preview") == "pdf"
    assert infer_event_family(event_type="doc_insert_text", stage="ui_action") == "doc"
    assert infer_event_family(event_type="sheet_open", stage="ui_action") == "sheet"
    assert infer_event_family(event_type="email_sent", stage="result") == "email"
    assert infer_event_family(event_type="approval_required", stage="system") == "approval"
    assert infer_event_family(event_type="browser.zoom_in", stage="preview") == "browser"
    assert infer_event_family(event_type="pdf.zoom_to_region", stage="ui_action") == "pdf"
    assert infer_event_family(event_type="sheet.zoom_out", stage="ui_action") == "sheet"


def test_infer_event_priority_respects_blockers_and_progress() -> None:
    assert (
        infer_event_priority(
            event_type="approval_required",
            status="waiting",
            stage="system",
            event_family="approval",
        )
        == "critical"
    )
    assert (
        infer_event_priority(
            event_type="tool_progress",
            status="info",
            stage="tool",
            event_family="scene",
        )
        == "background"
    )
    assert (
        infer_event_priority(
            event_type="tool_failed",
            status="failed",
            stage="tool",
            event_family="scene",
        )
        == "important"
    )


def test_build_event_envelope_captures_agent_and_refs() -> None:
    envelope = build_event_envelope(
        event_type="verification_check",
        stage="result",
        status="info",
        data={
            "owner_role": "verifier",
            "scene_surface": "document",
            "graph_node_id": "node_1",
            "evidence_ids": ["ev_1", "ev_2"],
            "artifact_refs": ["artifact_1"],
        },
    )
    assert envelope.event_family == "verify"
    assert envelope.agent_id == "agent.verifier"
    assert envelope.agent_role == "verifier"
    assert envelope.agent_label == "Verifier"
    assert envelope.agent_color
    assert envelope.graph_node_id == "node_1"
    assert envelope.scene_ref == "document"
    assert envelope.evidence_refs == ["ev_1", "ev_2"]
    assert envelope.artifact_refs == ["artifact_1"]


def test_merge_event_envelope_data_adds_v2_fields() -> None:
    envelope = build_event_envelope(
        event_type="browser_click",
        stage="ui_action",
        status="in_progress",
        data={"owner_role": "browser"},
    )
    merged = merge_event_envelope_data(
        data={"url": "https://example.com"},
        envelope=envelope,
        event_schema_version="interaction_v2",
    )
    assert merged["event_schema_version"] == "interaction_v2"
    assert merged["event_family"] == "browser"
    assert merged["event_priority"] in {"critical", "important", "contextual", "background", "internal"}
    assert merged["event_render_mode"] in {"animate_live", "summarize", "compress", "replay_later"}
    assert merged["event_replay_importance"] in {"critical", "high", "normal", "low", "internal"}
    assert merged["event_envelope_version"] == EVENT_ENVELOPE_VERSION
    assert isinstance(merged["event_envelope"], dict)
    assert merged["agent_id"] == "agent.browser"
    assert merged["agent_role"] == "browser"
    assert merged["agent_label"] == "Browser"
    assert merged["agent_color"]


def test_merge_event_envelope_data_adds_reference_lists_from_envelope() -> None:
    envelope = build_event_envelope(
        event_type="pdf_zoom_to_region",
        stage="ui_action",
        status="in_progress",
        data={
            "owner_role": "verifier",
            "graph_node_id": "node-zoom-4",
            "scene_ref": "scene.pdf.reader",
        },
    )
    merged = merge_event_envelope_data(
        data={},
        envelope=envelope,
        event_schema_version="interaction_v2",
    )
    assert merged["graph_node_id"] == "node-zoom-4"
    assert merged["scene_ref"] == "scene.pdf.reader"
    assert merged["graph_node_ids"] == ["node-zoom-4"]
    assert merged["scene_refs"] == ["scene.pdf.reader"]


def test_merge_event_envelope_data_sets_agent_event_alias() -> None:
    envelope = build_event_envelope(
        event_type="role_handoff",
        stage="tool",
        status="info",
        data={"from_role": "planner", "to_role": "research"},
    )
    merged = merge_event_envelope_data(
        data={"from_role": "planner"},
        envelope=envelope,
        event_schema_version="1.0",
    )
    assert merged["agent_event_type"] == "agent.handoff"


def test_apply_workspace_mode_policy_fast_compresses_contextual_events() -> None:
    render_mode, replay_importance = apply_workspace_mode_policy(
        payload={"__workspace_render_mode": "fast"},
        priority="contextual",
        default_render_mode="animate_live",
        default_replay_importance="normal",
    )
    assert render_mode == "compress"
    assert replay_importance == "low"


def test_apply_workspace_mode_policy_full_theatre_promotes_contextual_events() -> None:
    render_mode, replay_importance = apply_workspace_mode_policy(
        payload={"workspace_render_mode": "full"},
        priority="contextual",
        default_render_mode="animate_live",
        default_replay_importance="normal",
    )
    assert render_mode == "animate_live"
    assert replay_importance == "high"


def test_merge_event_envelope_data_adds_plugin_hints_for_api_events() -> None:
    envelope = build_event_envelope(
        event_type="api_call_started",
        stage="tool",
        status="in_progress",
        data={
            "connector_id": "google_analytics",
            "action_id": "analytics.fetch_report",
        },
    )
    merged = merge_event_envelope_data(
        data={
            "connector_id": "google_analytics",
            "action_id": "analytics.fetch_report",
        },
        envelope=envelope,
        event_schema_version="interaction_v2",
    )
    assert merged["plugin_connector_label"] == "Google Analytics"
    assert merged["plugin_action_title"] == "Fetch report"
    assert merged["plugin_graph_node_type"] == "api_operation"
    assert merged["scene_surface"] == "api"
