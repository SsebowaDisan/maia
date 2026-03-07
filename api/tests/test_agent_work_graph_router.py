from __future__ import annotations

import pytest
from fastapi import HTTPException

from api.routers.agent_api import work_graph
from api.services.agent.activity import ActivityStore
from api.services.agent.models import AgentActivityEvent


def _build_store(tmp_path, monkeypatch) -> ActivityStore:
    monkeypatch.setattr("api.services.agent.activity._storage_root", lambda: tmp_path / "activity")
    return ActivityStore()


def test_get_agent_run_work_graph_returns_run_scoped_payload(tmp_path, monkeypatch) -> None:
    store = _build_store(tmp_path, monkeypatch)
    monkeypatch.setattr("api.routers.agent_api.work_graph.get_activity_store", lambda: store)

    header = store.start_run(
        user_id="u1",
        conversation_id="c1",
        mode="company_agent",
        goal="Assemble graph",
    )
    store.append(
        AgentActivityEvent(
            event_id="evt-1",
            run_id=header.run_id,
            event_type="browser_extract",
            title="Extract",
            seq=1,
            stage="tool",
            status="in_progress",
            data={
                "event_family": "browser",
                "graph_node_id": "node.browser",
                "agent_role": "research",
                "scene_ref": "scene.browser.main",
            },
            metadata={},
        )
    )

    payload = work_graph.get_agent_run_work_graph(
        run_id=header.run_id,
        agent_role="research",
        status="running",
        event_index_min=1,
        event_index_max=3,
    )
    assert payload["run_id"] == header.run_id
    assert payload["root_id"] == f"run:{header.run_id}:root"
    assert payload["filters"]["agent_role"] == "research"
    assert any(node.get("id") == "node.browser" for node in payload["nodes"])


def test_get_agent_run_work_graph_replay_state_aligns_node_ranges(tmp_path, monkeypatch) -> None:
    store = _build_store(tmp_path, monkeypatch)
    monkeypatch.setattr("api.routers.agent_api.work_graph.get_activity_store", lambda: store)
    header = store.start_run(
        user_id="u2",
        conversation_id="c2",
        mode="company_agent",
        goal="Replay graph",
    )
    store.append(
        AgentActivityEvent(
            event_id="evt-2",
            run_id=header.run_id,
            event_type="document_opened",
            title="Open PDF",
            seq=2,
            stage="preview",
            status="completed",
            data={
                "event_family": "doc",
                "graph_node_id": "node.doc",
                "agent_role": "document_reader",
                "scene_refs": ["scene.pdf.reader"],
            },
            metadata={},
        )
    )
    payload = work_graph.get_agent_run_work_graph_replay_state(run_id=header.run_id)
    assert payload["run_id"] == header.run_id
    assert payload["latest_event_index"] == 2
    work_graph_payload = payload["work_graph"]
    assert work_graph_payload["run_id"] == header.run_id
    ranges = work_graph_payload["node_ranges"]
    assert ranges[0]["node_id"] == "node.doc"
    assert ranges[0]["event_index_start"] == 2
    assert "scene.pdf.reader" in ranges[0]["scene_refs"]


def test_get_agent_run_work_graph_raises_for_missing_run(tmp_path, monkeypatch) -> None:
    store = _build_store(tmp_path, monkeypatch)
    monkeypatch.setattr("api.routers.agent_api.work_graph.get_activity_store", lambda: store)
    with pytest.raises(HTTPException) as exc_info:
        work_graph.get_agent_run_work_graph(run_id="run-missing")
    assert exc_info.value.status_code == 404

