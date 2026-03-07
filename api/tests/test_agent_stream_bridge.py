from __future__ import annotations

import pytest

from api.services.agent.models import AgentActivityEvent
from api.services.agent.orchestration.stream_bridge import LiveRunStream
from api.services.agent.planner import PlannedStep
from api.services.agent.tools.base import ToolTraceEvent


class _ActivityStoreStub:
    def __init__(self) -> None:
        self.rows: list[AgentActivityEvent] = []

    def append(self, event: AgentActivityEvent) -> None:
        self.rows.append(event)


class _BrokerStub:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def publish(self, *, user_id: str, event: dict, run_id: str | None = None) -> None:
        self.rows.append({"user_id": user_id, "run_id": run_id, "event": dict(event)})


def _factory_builder(run_id: str = "run-test"):
    seq = {"value": 0}

    def _factory(
        *,
        event_type: str,
        title: str,
        detail: str = "",
        metadata: dict | None = None,
        stage: str | None = None,
        status: str | None = None,
        snapshot_ref: str | None = None,
    ) -> AgentActivityEvent:
        seq["value"] += 1
        return AgentActivityEvent(
            event_id=f"evt-{seq['value']}",
            run_id=run_id,
            event_type=event_type,
            title=title,
            detail=detail,
            metadata=dict(metadata or {}),
            seq=seq["value"],
            stage=stage or "system",
            status=status or "info",
            snapshot_ref=snapshot_ref,
        )

    return _factory


def _emit_single_trace(
    *,
    tool_id: str,
    trace: ToolTraceEvent,
) -> dict:
    observed: list[str] = []
    stream = LiveRunStream(
        activity_store=_ActivityStoreStub(),
        user_id="u1",
        run_id="run-test",
        observed_event_types=observed,
    )
    step = PlannedStep(tool_id=tool_id, title="step", params={})
    event_rows = list(
        stream.stream_traces(
            step=step,
            step_index=1,
            traces=[trace],
            activity_event_factory=_factory_builder(),
        )
    )
    assert len(event_rows) == 1
    return event_rows[0]["event"]["data"]


def test_stream_bridge_infers_google_sheets_surface() -> None:
    payload = _emit_single_trace(
        tool_id="workspace.sheets.track_step",
        trace=ToolTraceEvent(event_type="sheet_cell_update", title="Cell updated", detail="A1"),
    )
    assert payload["scene_surface"] == "google_sheets"


def test_stream_bridge_infers_google_docs_surface() -> None:
    payload = _emit_single_trace(
        tool_id="workspace.docs.research_notes",
        trace=ToolTraceEvent(event_type="doc_type_text", title="Typing", detail="chunk"),
    )
    assert payload["scene_surface"] == "google_docs"


def test_stream_bridge_keeps_document_surface_for_doc_copy_clipboard() -> None:
    payload = _emit_single_trace(
        tool_id="documents.highlight.extract",
        trace=ToolTraceEvent(
            event_type="doc_copy_clipboard",
            title="Copy highlights",
            detail="Copied top snippet",
            data={"scene_surface": "document"},
        ),
    )
    assert payload["scene_surface"] == "document"


def test_stream_bridge_infers_pdf_surface_as_document() -> None:
    payload = _emit_single_trace(
        tool_id="documents.highlight.extract",
        trace=ToolTraceEvent(event_type="pdf_page_change", title="Page changed", detail="Page 2"),
    )
    assert payload["scene_surface"] == "document"


def test_stream_bridge_infers_surface_from_drive_source_url() -> None:
    payload = _emit_single_trace(
        tool_id="workspace.docs.research_notes",
        trace=ToolTraceEvent(
            event_type="drive.share_started",
            title="Share",
            detail="doc",
            data={"source_url": "https://docs.google.com/spreadsheets/d/example/edit"},
        ),
    )
    assert payload["scene_surface"] == "google_sheets"


def test_stream_bridge_preserves_explicit_scene_surface() -> None:
    payload = _emit_single_trace(
        tool_id="workspace.docs.research_notes",
        trace=ToolTraceEvent(
            event_type="tool_progress",
            title="Progress",
            data={"scene_surface": "email"},
        ),
    )
    assert payload["scene_surface"] == "email"


def test_stream_bridge_adds_cursor_for_interactive_scene_events() -> None:
    payload = _emit_single_trace(
        tool_id="marketing.web_research",
        trace=ToolTraceEvent(
            event_type="browser_navigate",
            title="Open page",
            data={"url": "https://example.com"},
        ),
    )
    assert payload["scene_surface"] == "website"
    assert isinstance(payload.get("cursor_x"), float)
    assert isinstance(payload.get("cursor_y"), float)
    assert 0.0 <= float(payload.get("cursor_x") or 0.0) <= 100.0
    assert 0.0 <= float(payload.get("cursor_y") or 0.0) <= 100.0


def test_stream_bridge_keeps_browser_events_on_website_surface_for_docs_google_urls() -> None:
    payload = _emit_single_trace(
        tool_id="marketing.web_research",
        trace=ToolTraceEvent(
            event_type="browser_navigate",
            title="Open result",
            data={"source_url": "https://docs.google.com/document/d/123/edit"},
        ),
    )
    assert payload["scene_surface"] == "website"


def test_stream_bridge_keeps_existing_cursor_values() -> None:
    payload = _emit_single_trace(
        tool_id="marketing.web_research",
        trace=ToolTraceEvent(
            event_type="browser_click",
            title="Click",
            data={
                "scene_surface": "website",
                "cursor_x": 64.0,
                "cursor_y": 18.0,
            },
        ),
    )
    assert payload["cursor_x"] == 64.0
    assert payload["cursor_y"] == 18.0


def test_stream_bridge_infers_scroll_fields_for_browser_scroll() -> None:
    payload = _emit_single_trace(
        tool_id="marketing.web_research",
        trace=ToolTraceEvent(
            event_type="browser_scroll",
            title="Scroll",
            detail="Reviewing lower cards",
            data={"scene_surface": "website"},
        ),
    )
    assert payload["scroll_direction"] == "down"
    assert isinstance(payload.get("scroll_percent"), float)


def test_stream_bridge_adds_owner_role_to_normalized_trace() -> None:
    payload = _emit_single_trace(
        tool_id="report.generate",
        trace=ToolTraceEvent(
            event_type="tool_progress",
            title="Draft report",
            data={"scene_surface": "system"},
        ),
    )
    assert payload.get("owner_role") == "writer"


def test_stream_bridge_marks_drive_search_surface_as_document() -> None:
    payload = _emit_single_trace(
        tool_id="workspace.drive.search",
        trace=ToolTraceEvent(
            event_type="drive.search_completed",
            title="Drive search",
            detail="query",
            data={"query": "Q4 report"},
        ),
    )
    assert payload["scene_surface"] == "document"


def test_stream_bridge_adds_cursor_for_non_browser_interactive_surfaces() -> None:
    checks = [
        ("workspace.docs.research_notes", "doc_type_text", "google_docs"),
        ("workspace.sheets.track_step", "sheet_append_row", "google_sheets"),
        ("email.send", "email_set_body", "email"),
        ("documents.highlight.extract", "pdf_scan_region", "document"),
    ]
    for tool_id, event_type, expected_surface in checks:
        payload = _emit_single_trace(
            tool_id=tool_id,
            trace=ToolTraceEvent(
                event_type=event_type,
                title="interaction",
                detail="test",
            ),
        )
        assert payload["scene_surface"] == expected_surface
        assert isinstance(payload.get("cursor_x"), float)
        assert isinstance(payload.get("cursor_y"), float)


def test_stream_bridge_handles_dotted_zoom_event_surface_and_cursor() -> None:
    payload = _emit_single_trace(
        tool_id="marketing.web_research",
        trace=ToolTraceEvent(
            event_type="browser.zoom_in",
            title="Zoom in",
            data={"zoom_level": 1.6},
        ),
    )
    assert payload["scene_surface"] == "website"
    assert payload["action"] == "zoom_in"
    assert isinstance(payload.get("cursor_x"), float)
    assert isinstance(payload.get("cursor_y"), float)


def test_stream_bridge_maps_api_call_surface_and_plugin_hints() -> None:
    payload = _emit_single_trace(
        tool_id="analytics.fetch",
        trace=ToolTraceEvent(
            event_type="api_call_started",
            title="Fetch report",
            data={
                "connector_id": "google_analytics",
                "action_id": "analytics.fetch_report",
            },
        ),
    )
    assert payload["scene_surface"] == "api"
    assert payload["plugin_connector_label"] == "Google Analytics"
    assert payload["plugin_action_title"] == "Fetch report"


def test_stream_bridge_emit_publishes_event_envelope_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    activity_store = _ActivityStoreStub()
    broker = _BrokerStub()
    monkeypatch.setattr(
        "api.services.agent.orchestration.stream_bridge.get_live_event_broker",
        lambda: broker,
    )
    stream = LiveRunStream(
        activity_store=activity_store,
        user_id="u1",
        run_id="run-test",
        observed_event_types=[],
    )
    event = AgentActivityEvent(
        event_id="evt-1",
        run_id="run-test",
        event_type="document_opened",
        title="Open document",
        detail="Loaded file",
        stage="ui_action",
        status="completed",
        event_schema_version="1.0",
        data={
            "event_family": "doc",
            "event_priority": "contextual",
            "event_render_mode": "animate_live",
            "event_replay_importance": "normal",
            "graph_node_id": "node-7",
            "scene_ref": "scene.document.preview",
            "event_envelope": {"event_family": "doc"},
        },
        seq=6,
    )
    stream.emit(event)
    assert len(broker.rows) == 1
    payload = broker.rows[0]["event"]
    assert payload["event_type"] == "document_opened"
    assert payload["stage"] == "ui_action"
    assert payload["status"] == "completed"
    assert payload["event_family"] == "doc"
    assert payload["event_priority"] == "contextual"
    assert payload["event_render_mode"] == "animate_live"
    assert payload["event_index"] == 6
    assert payload["replay_importance"] == "normal"
    assert payload["graph_node_id"] == "node-7"
    assert payload["scene_ref"] == "scene.document.preview"
    assert payload["data"]["graph_node_ids"] == ["node-7"]
    assert payload["data"]["scene_refs"] == ["scene.document.preview"]
    assert payload["data"]["event_refs"] == ["evt-1"]


def test_stream_bridge_emit_persists_zoom_event_with_graph_linkage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    activity_store = _ActivityStoreStub()
    broker = _BrokerStub()
    monkeypatch.setattr(
        "api.services.agent.orchestration.stream_bridge.get_live_event_broker",
        lambda: broker,
    )
    stream = LiveRunStream(
        activity_store=activity_store,
        user_id="u1",
        run_id="run-test",
        observed_event_types=[],
    )
    event = AgentActivityEvent(
        event_id="evt-zoom-1",
        run_id="run-test",
        event_type="pdf_zoom_to_region",
        title="Zoom PDF",
        detail="Inspect totals block",
        stage="ui_action",
        status="in_progress",
        event_schema_version="1.0",
        data={
            "scene_surface": "document",
            "action": "zoom_to_region",
            "zoom_level": 2.1,
            "zoom_reason": "verifier escalation",
            "zoom_policy_triggers": ["verifier_escalation"],
            "graph_node_id": "node-zoom-1",
            "scene_ref": "scene.pdf.reader",
        },
        seq=11,
    )
    payload = stream.emit(event)["event"]["data"]
    zoom_event = payload.get("zoom_event") or {}
    assert zoom_event.get("action") == "zoom_to_region"
    assert zoom_event.get("event_ref") == "evt-zoom-1"
    assert zoom_event.get("event_index") == 11
    assert zoom_event.get("graph_node_id") == "node-zoom-1"
    assert zoom_event.get("scene_ref") == "scene.pdf.reader"
    assert payload.get("zoom_history") and isinstance(payload.get("zoom_history"), list)
    assert payload.get("event_refs") == ["evt-zoom-1"]


def test_stream_bridge_links_copy_source_to_later_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    activity_store = _ActivityStoreStub()
    broker = _BrokerStub()
    monkeypatch.setattr(
        "api.services.agent.orchestration.stream_bridge.get_live_event_broker",
        lambda: broker,
    )
    stream = LiveRunStream(
        activity_store=activity_store,
        user_id="u1",
        run_id="run-test",
        observed_event_types=[],
    )
    copy_event = AgentActivityEvent(
        event_id="evt-copy-1",
        run_id="run-test",
        event_type="browser_copy_selection",
        title="Copy snippet",
        detail="Copied from source",
        stage="preview",
        status="completed",
        data={
            "scene_surface": "website",
            "action": "extract",
            "source_url": "https://example.com",
            "clipboard_text": "Revenue grew 31 percent year over year.",
            "copied_words": ["Revenue", "grew", "31%", "year-over-year"],
            "graph_node_id": "node-copy-1",
            "scene_ref": "scene.browser.main",
        },
        seq=3,
    )
    usage_event = AgentActivityEvent(
        event_id="evt-usage-1",
        run_id="run-test",
        event_type="email_type_body",
        title="Type email body",
        detail="Drafting summary",
        stage="ui_action",
        status="in_progress",
        data={
            "scene_surface": "email",
            "action": "type",
        },
        seq=4,
    )
    copy_payload = stream.emit(copy_event)["event"]["data"]
    usage_payload = stream.emit(usage_event)["event"]["data"]
    assert copy_payload.get("copy_role") == "source"
    assert copy_payload.get("copy_provenance", {}).get("copy_event_ref") == "evt-copy-1"
    assert usage_payload.get("copy_role") == "usage"
    assert usage_payload.get("copy_usage_refs") == ["evt-copy-1"]
    assert usage_payload.get("copy_provenance", {}).get("copy_event_ref") == "evt-copy-1"
