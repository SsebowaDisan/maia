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
