from __future__ import annotations

from api.services.agent.events import EVENT_SCHEMA_VERSION, RunEventEmitter


def test_run_event_emitter_increments_sequence() -> None:
    emitter = RunEventEmitter(run_id="run_test")
    first = emitter.emit(event_type="planning_started", title="Start planning")
    second = emitter.emit(event_type="plan_ready", title="Plan ready")

    assert first.seq == 1
    assert second.seq == 2
    assert second.seq > first.seq


def test_agent_event_dict_contains_schema_and_legacy_keys() -> None:
    emitter = RunEventEmitter(run_id="run_test")
    event = emitter.emit(
        event_type="document_opened",
        title="Open document",
        detail="Loaded PDF",
        data={"file_id": "file_1"},
        snapshot_ref="snapshot://run_test/1",
    )
    payload = event.to_dict()

    assert payload["event_schema_version"] == EVENT_SCHEMA_VERSION
    assert payload["run_id"] == "run_test"
    assert payload["seq"] == 1
    assert payload["type"] == "document_opened"
    assert payload["ts"]
    assert payload["stage"]
    assert payload["status"]
    assert payload["data"]["file_id"] == "file_1"
    assert payload["snapshot_ref"] == "snapshot://run_test/1"

    # Backward-compatible aliases are still emitted.
    assert payload["event_type"] == "document_opened"
    assert payload["timestamp"] == payload["ts"]
    assert payload["metadata"]["file_id"] == "file_1"


def test_web_routing_event_is_planning_stage() -> None:
    emitter = RunEventEmitter(run_id="run_test")
    event = emitter.emit(
        event_type="llm.web_routing_decision",
        title="Web routing decision ready",
        data={"routing_mode": "online_research"},
    )
    assert event.stage == "plan"
    assert event.status == "info"


def test_web_kpi_summary_event_is_result_stage() -> None:
    emitter = RunEventEmitter(run_id="run_test")
    event = emitter.emit(
        event_type="web_kpi_summary",
        title="Web reliability summary",
        data={"web_steps_total": 3},
    )
    assert event.stage == "result"
    assert event.status == "info"


def test_web_release_and_evidence_events_are_result_stage() -> None:
    emitter = RunEventEmitter(run_id="run_test")
    evidence_event = emitter.emit(
        event_type="web_evidence_summary",
        title="Web evidence summary",
        data={"web_evidence_total": 4},
    )
    gate_event = emitter.emit(
        event_type="web_release_gate",
        title="Web rollout gate evaluation",
        data={"ready_for_scale": True},
    )
    assert evidence_event.stage == "result"
    assert evidence_event.status == "info"
    assert gate_event.stage == "result"
    assert gate_event.status == "info"
