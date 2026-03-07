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


def test_role_events_have_tool_stage_and_expected_status() -> None:
    emitter = RunEventEmitter(run_id="run_test")
    handoff = emitter.emit(
        event_type="role_handoff",
        title="Role handoff",
        data={"from_role": "research", "to_role": "writer"},
    )
    activated = emitter.emit(
        event_type="role_activated",
        title="Role active: writer",
        data={"role": "writer"},
    )
    assert handoff.stage == "tool"
    assert handoff.status == "info"
    assert activated.stage == "tool"
    assert activated.status == "in_progress"


def test_session_context_event_is_planning_stage() -> None:
    emitter = RunEventEmitter(run_id="run_test")
    event = emitter.emit(
        event_type="llm.context_session",
        title="Loaded relevant session context",
        data={"session_context_snippets": ["snippet"]},
    )
    assert event.stage == "plan"
    assert event.status == "info"


def test_working_context_event_is_planning_stage() -> None:
    emitter = RunEventEmitter(run_id="run_test")
    event = emitter.emit(
        event_type="llm.working_context_compiled",
        title="Compiled execution working context",
        data={"working_context_version": "working_context_v1"},
    )
    assert event.stage == "plan"
    assert event.status == "info"


def test_role_dispatch_and_execution_checkpoint_stage_defaults() -> None:
    emitter = RunEventEmitter(run_id="run_test")
    dispatch = emitter.emit(
        event_type="role_dispatch_plan",
        title="Role dispatch plan ready",
    )
    checkpoint = emitter.emit(
        event_type="execution_checkpoint",
        title="Checkpoint: execution_cycle_started",
    )
    assert dispatch.stage == "plan"
    assert dispatch.status == "info"
    assert checkpoint.stage == "system"
    assert checkpoint.status == "info"


def test_handoff_events_have_waiting_and_completed_status() -> None:
    emitter = RunEventEmitter(run_id="run_test")
    paused = emitter.emit(
        event_type="handoff_paused",
        title="Execution paused for human verification",
    )
    resumed = emitter.emit(
        event_type="handoff_resumed",
        title="Resumed after human verification",
    )
    assert paused.stage == "system"
    assert paused.status == "waiting"
    assert resumed.stage == "system"
    assert resumed.status == "completed"
