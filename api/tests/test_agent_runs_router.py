from __future__ import annotations

import pytest
from fastapi import HTTPException

from api.routers.agent_api import runs
from api.services.agent.activity import ActivityStore
from api.services.agent.models import AgentActivityEvent


def _build_store(tmp_path, monkeypatch) -> ActivityStore:
    monkeypatch.setattr("api.services.agent.activity._storage_root", lambda: tmp_path / "activity")
    return ActivityStore()


def test_export_agent_run_events_includes_graph_snapshots(tmp_path, monkeypatch) -> None:
    store = _build_store(tmp_path, monkeypatch)
    monkeypatch.setattr("api.routers.agent_api.runs.get_activity_store", lambda: store)

    header = store.start_run(
        user_id="u1",
        conversation_id="c1",
        mode="company_agent",
        goal="Export run",
    )
    store.append(
        AgentActivityEvent(
            event_id="evt-1",
            run_id=header.run_id,
            event_type="browser_click",
            title="Click",
            seq=3,
            data={
                "graph_node_id": "node-3",
                "scene_ref": "scene.browser.main",
                "evidence_refs": ["evidence-a"],
                "artifact_refs": ["artifact-a"],
            },
            metadata={},
        )
    )

    payload = runs.export_agent_run_events(header.run_id)
    assert payload["run_id"] == header.run_id
    assert payload["total_events"] == 1
    assert payload["total_graph_snapshots"] == 1
    assert payload["total_evidence_snapshots"] == 1
    assert payload["total_artifact_snapshots"] == 1
    graph_snapshots = payload["graph_snapshots"]
    assert isinstance(graph_snapshots, list)
    assert graph_snapshots[0]["event_id"] == "evt-1"
    assert graph_snapshots[0]["event_index"] == 3
    assert payload["evidence_snapshots"][0]["evidence_refs"] == ["evidence-a"]
    assert payload["artifact_snapshots"][0]["artifact_refs"] == ["artifact-a"]
    assert payload["replay_state"]["latest_event_index"] == 3


def test_get_agent_run_replay_state_returns_snapshots(tmp_path, monkeypatch) -> None:
    store = _build_store(tmp_path, monkeypatch)
    monkeypatch.setattr("api.routers.agent_api.runs.get_activity_store", lambda: store)

    header = store.start_run(
        user_id="u2",
        conversation_id="c2",
        mode="company_agent",
        goal="Replay state",
    )
    store.append(
        AgentActivityEvent(
            event_id="evt-replay-1",
            run_id=header.run_id,
            event_type="document_extract",
            title="Extract",
            seq=2,
            data={
                "graph_node_id": "node-2",
                "evidence_refs": ["ev-2"],
            },
            metadata={},
        )
    )
    replay_state = runs.get_agent_run_replay_state(header.run_id)
    assert replay_state["latest_event_index"] == 2
    assert replay_state["graph_snapshots"][0]["graph_node_ids"] == ["node-2"]
    assert replay_state["evidence_snapshots"][0]["evidence_refs"] == ["ev-2"]


def test_get_agent_run_graph_snapshots_raises_for_missing_run(tmp_path, monkeypatch) -> None:
    store = _build_store(tmp_path, monkeypatch)
    monkeypatch.setattr("api.routers.agent_api.runs.get_activity_store", lambda: store)
    with pytest.raises(HTTPException) as exc_info:
        runs.get_agent_run_graph_snapshots("run-missing")
    assert exc_info.value.status_code == 404
