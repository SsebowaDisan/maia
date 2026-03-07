from __future__ import annotations

from api.services.agent.activity import ActivityStore
from api.services.agent.models import AgentActivityEvent
from api.services.agent.work_graph.builder import WorkGraphBuilder


def _build_store(tmp_path, monkeypatch) -> ActivityStore:
    monkeypatch.setattr("api.services.agent.activity._storage_root", lambda: tmp_path / "activity")
    return ActivityStore()


def test_activity_store_persists_work_graph_snapshots_append_only(tmp_path, monkeypatch) -> None:
    store = _build_store(tmp_path, monkeypatch)
    header = store.start_run(
        user_id="u1",
        conversation_id="c1",
        mode="company_agent",
        goal="Persist graph snapshots",
    )
    store.append(
        AgentActivityEvent(
            event_id="evt-1",
            run_id=header.run_id,
            event_type="planning_started",
            title="Plan",
            seq=1,
            data={"event_family": "plan", "graph_node_id": "node.plan"},
            metadata={},
        )
    )
    store.append(
        AgentActivityEvent(
            event_id="evt-2",
            run_id=header.run_id,
            event_type="browser_extract",
            title="Research",
            seq=2,
            data={"event_family": "browser", "graph_node_id": "node.research"},
            metadata={},
        )
    )

    builder = WorkGraphBuilder(store=store)
    builder.build_for_run(run_id=header.run_id)
    builder.build_for_run(run_id=header.run_id)  # same event window: no duplicate snapshot

    snapshots = store.load_work_graph_snapshots(header.run_id)
    assert len(snapshots) == 1
    assert snapshots[0]["event_index"] == 2
    assert snapshots[0]["storage_backend"] == "jsonl"
    graph_payload = snapshots[0]["graph"]
    assert graph_payload["run_id"] == header.run_id
    assert graph_payload["root_id"] == f"run:{header.run_id}:root"
    assert isinstance(graph_payload["nodes"], list)
    assert isinstance(graph_payload["edges"], list)

    store.append(
        AgentActivityEvent(
            event_id="evt-3",
            run_id=header.run_id,
            event_type="verification_completed",
            title="Verify",
            seq=3,
            data={"event_family": "verify", "graph_node_id": "node.verify"},
            metadata={},
        )
    )
    builder.build_for_run(run_id=header.run_id)
    snapshots = store.load_work_graph_snapshots(header.run_id)
    assert len(snapshots) == 2
    assert [row["event_index"] for row in snapshots] == [2, 3]


def test_replay_state_includes_work_graph_snapshots(tmp_path, monkeypatch) -> None:
    store = _build_store(tmp_path, monkeypatch)
    header = store.start_run(
        user_id="u2",
        conversation_id="c2",
        mode="company_agent",
        goal="Replay work graph snapshots",
    )
    store.append(
        AgentActivityEvent(
            event_id="evt-1",
            run_id=header.run_id,
            event_type="plan_ready",
            title="Ready",
            seq=1,
            data={"event_family": "plan", "graph_node_id": "node.plan"},
            metadata={},
        )
    )
    WorkGraphBuilder(store=store).build_for_run(run_id=header.run_id)

    replay_state = store.load_replay_state(header.run_id)
    assert replay_state["latest_event_index"] == 1
    assert isinstance(replay_state.get("work_graph_snapshots"), list)
    assert replay_state["work_graph_snapshots"][0]["event_index"] == 1

