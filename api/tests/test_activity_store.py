from __future__ import annotations

from api.services.agent.activity import ActivityStore
from api.services.agent.models import AgentActivityEvent


def _build_store(tmp_path, monkeypatch) -> ActivityStore:
    monkeypatch.setattr("api.services.agent.activity._storage_root", lambda: tmp_path / "activity")
    return ActivityStore()


def test_activity_store_persists_graph_snapshot_with_event_index(tmp_path, monkeypatch) -> None:
    store = _build_store(tmp_path, monkeypatch)
    header = store.start_run(
        user_id="u1",
        conversation_id="c1",
        mode="company_agent",
        goal="Persist graph refs",
    )
    store.append(
        AgentActivityEvent(
            event_id="evt-graph-1",
            run_id=header.run_id,
            event_type="browser_click",
            title="Click target",
            seq=4,
            data={
                "graph_node_id": "node-plan-4",
                "scene_ref": "scene.browser.main",
            },
            metadata={},
        )
    )

    snapshots = store.load_graph_snapshots(header.run_id)
    assert len(snapshots) == 1
    assert snapshots[0]["event_id"] == "evt-graph-1"
    assert snapshots[0]["event_index"] == 4
    assert snapshots[0]["graph_node_ids"] == ["node-plan-4"]
    assert snapshots[0]["scene_refs"] == ["scene.browser.main"]


def test_activity_store_graph_snapshot_index_falls_back_to_row_order(tmp_path, monkeypatch) -> None:
    store = _build_store(tmp_path, monkeypatch)
    header = store.start_run(
        user_id="u2",
        conversation_id="c2",
        mode="company_agent",
        goal="Fallback index",
    )
    store.append(
        AgentActivityEvent(
            event_id="evt-graph-a",
            run_id=header.run_id,
            event_type="browser_extract",
            title="Extract values",
            seq=0,
            data={
                "graph_node_ids": ["node-a", "node-a"],
                "scene_refs": ["scene.browser.main", "scene.browser.main"],
            },
            metadata={},
        )
    )
    store.append(
        AgentActivityEvent(
            event_id="evt-graph-b",
            run_id=header.run_id,
            event_type="document_verify",
            title="Verify numbers",
            seq=0,
            data={
                "event_index": 8,
                "graph_node_id": "node-b",
                "scene_ref": "scene.pdf.reader",
            },
            metadata={},
        )
    )

    snapshots = store.load_graph_snapshots(header.run_id)
    assert [item["event_id"] for item in snapshots] == ["evt-graph-a", "evt-graph-b"]
    assert snapshots[0]["event_index"] == 1
    assert snapshots[0]["graph_node_ids"] == ["node-a"]
    assert snapshots[0]["scene_refs"] == ["scene.browser.main"]
    assert snapshots[1]["event_index"] == 8


def test_activity_store_persists_evidence_and_artifact_snapshots(tmp_path, monkeypatch) -> None:
    store = _build_store(tmp_path, monkeypatch)
    header = store.start_run(
        user_id="u3",
        conversation_id="c3",
        mode="company_agent",
        goal="Persist evidence and artifacts",
    )
    store.append(
        AgentActivityEvent(
            event_id="evt-proof-1",
            run_id=header.run_id,
            event_type="verification_completed",
            title="Verification completed",
            seq=6,
            data={
                "evidence_ids": ["evidence-1", "evidence-2", "evidence-1"],
                "artifact_ids": ["artifact-report"],
            },
            metadata={},
        )
    )

    evidence = store.load_evidence_snapshots(header.run_id)
    artifacts = store.load_artifact_snapshots(header.run_id)
    replay_state = store.load_replay_state(header.run_id)

    assert evidence[0]["event_id"] == "evt-proof-1"
    assert evidence[0]["event_index"] == 6
    assert evidence[0]["evidence_refs"] == ["evidence-1", "evidence-2"]
    assert artifacts[0]["artifact_refs"] == ["artifact-report"]
    assert replay_state["latest_event_index"] == 6
    assert replay_state["evidence_snapshots"][0]["event_id"] == "evt-proof-1"
