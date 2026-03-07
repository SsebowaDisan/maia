from __future__ import annotations

import json

from api.services.agent.activity import ActivityStore
from api.services.agent.live_events import LiveEventBroker
from api.services.agent.models import AgentActivityEvent


def test_live_event_broker_normalizes_event_envelope_defaults() -> None:
    broker = LiveEventBroker()
    subscription = broker.subscribe(user_id="u1", run_id="run1", replay_limit=0)
    broker.publish(
        user_id="u1",
        run_id="run1",
        event={
            "event_id": "evt-broker-1",
            "type": "tool_progress",
            "message": "Working",
            "data": {"owner_role": "writer"},
        },
    )
    received = broker.receive(subscription, timeout_seconds=0.2)
    assert isinstance(received, dict)
    assert received.get("event_type") == "tool_progress"
    assert received.get("type") == "tool_progress"
    assert received.get("stage")
    assert received.get("status")
    assert received.get("event_schema_version")
    assert received.get("event_family")
    assert received.get("event_priority")
    assert received.get("event_render_mode")
    assert received.get("event_replay_importance")
    assert received.get("replay_importance")
    payload = received.get("data") or {}
    assert payload.get("event_family")
    assert payload.get("event_priority")
    assert payload.get("event_render_mode")
    assert payload.get("event_replay_importance")
    assert payload.get("replay_importance")
    assert isinstance(payload.get("timeline"), dict)
    assert isinstance(payload.get("event_envelope"), dict)
    assert payload.get("event_refs") == ["evt-broker-1"]


def test_live_event_broker_persists_zoom_event_payload() -> None:
    broker = LiveEventBroker()
    subscription = broker.subscribe(user_id="u3", run_id="run3", replay_limit=0)
    broker.publish(
        user_id="u3",
        run_id="run3",
        event={
            "event_id": "evt-zoom-2",
            "event_type": "browser_zoom_in",
            "stage": "preview",
            "status": "in_progress",
            "data": {
                "scene_surface": "website",
                "action": "zoom_in",
                "zoom_level": 1.6,
                "zoom_reason": "high text density",
                "graph_node_id": "node-browser-9",
                "scene_ref": "scene.browser.main",
            },
        },
    )
    received = broker.receive(subscription, timeout_seconds=0.2)
    payload = (received or {}).get("data") or {}
    zoom_event = payload.get("zoom_event") or {}
    assert zoom_event.get("action") == "zoom_in"
    assert zoom_event.get("event_ref") == "evt-zoom-2"
    assert zoom_event.get("graph_node_id") == "node-browser-9"
    assert zoom_event.get("scene_ref") == "scene.browser.main"


def test_live_event_broker_subscribe_backfills_from_activity_store(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("api.services.agent.activity._storage_root", lambda: tmp_path / "activity")
    store = ActivityStore()
    monkeypatch.setattr("api.services.agent.live_events.get_activity_store", lambda: store)

    header = store.start_run(
        user_id="u4",
        conversation_id="c4",
        mode="company_agent",
        goal="Backfill replay events",
    )
    store.append(
        AgentActivityEvent(
            event_id="evt-backfill-1",
            run_id=header.run_id,
            event_type="browser_navigate",
            title="Navigate",
            detail="Open source page",
            stage="preview",
            status="in_progress",
            data={"scene_surface": "website"},
            metadata={"scene_surface": "website"},
            seq=1,
        )
    )

    broker = LiveEventBroker()
    subscription = broker.subscribe(user_id="u4", run_id=header.run_id, replay_limit=10)
    received = broker.receive(subscription, timeout_seconds=0.2)
    assert isinstance(received, dict)
    assert received.get("event_type") == "browser_navigate"
    payload = received.get("data") or {}
    assert payload.get("event_index") == 1


def test_live_event_broker_hydrates_snapshot_refs_on_reconnect(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("api.services.agent.activity._storage_root", lambda: tmp_path / "activity")
    store = ActivityStore()
    monkeypatch.setattr("api.services.agent.live_events.get_activity_store", lambda: store)

    header = store.start_run(
        user_id="u5",
        conversation_id="c5",
        mode="company_agent",
        goal="Hydrate snapshot refs",
    )
    store.append(
        AgentActivityEvent(
            event_id="evt-backfill-2",
            run_id=header.run_id,
            event_type="verification_check",
            title="Verify",
            detail="Coverage",
            stage="result",
            status="completed",
            data={
                "graph_node_id": "node-check-2",
                "scene_ref": "scene.document.preview",
                "evidence_refs": ["evidence-2"],
                "artifact_refs": ["artifact-2"],
            },
            metadata={},
            seq=2,
        )
    )
    rows = store.load_events(header.run_id)
    for row in rows:
        if row.get("type") != "event":
            continue
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue
        if payload.get("event_id") != "evt-backfill-2":
            continue
        data = payload.get("data")
        if isinstance(data, dict):
            data.pop("graph_node_ids", None)
            data.pop("scene_refs", None)
            data.pop("evidence_refs", None)
            data.pop("artifact_refs", None)
            payload["data"] = data
    file_path = tmp_path / "activity" / f"{header.run_id}.jsonl"
    file_path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )

    broker = LiveEventBroker()
    subscription = broker.subscribe(user_id="u5", run_id=header.run_id, replay_limit=10)
    received = broker.receive(subscription, timeout_seconds=0.2)
    assert isinstance(received, dict)
    payload = received.get("data") or {}
    assert payload.get("graph_node_ids") == ["node-check-2"]
    assert payload.get("scene_refs") == ["scene.document.preview"]
    assert payload.get("evidence_refs") == ["evidence-2"]
    assert payload.get("artifact_refs") == ["artifact-2"]


def test_live_event_broker_preserves_declared_stage_and_status() -> None:
    broker = LiveEventBroker()
    subscription = broker.subscribe(user_id="u2", run_id="run2", replay_limit=0)
    broker.publish(
        user_id="u2",
        run_id="run2",
        event={
            "event_type": "approval_required",
            "stage": "system",
            "status": "waiting",
            "data": {"scene_surface": "website"},
        },
    )
    received = broker.receive(subscription, timeout_seconds=0.2)
    assert isinstance(received, dict)
    assert received.get("stage") == "system"
    assert received.get("status") == "waiting"
    assert received.get("event_family") == "approval"
