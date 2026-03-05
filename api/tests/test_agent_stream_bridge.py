from __future__ import annotations

from api.services.agent.models import AgentActivityEvent
from api.services.agent.orchestration.stream_bridge import LiveRunStream
from api.services.agent.planner import PlannedStep
from api.services.agent.tools.base import ToolTraceEvent


class _ActivityStoreStub:
    def __init__(self) -> None:
        self.rows: list[AgentActivityEvent] = []

    def append(self, event: AgentActivityEvent) -> None:
        self.rows.append(event)


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
