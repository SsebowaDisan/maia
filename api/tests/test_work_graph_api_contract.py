from __future__ import annotations

import pytest
from fastapi import HTTPException

from api.routers.agent_api import work_graph
from api.services.agent.activity import ActivityStore
from api.services.agent.models import AgentActivityEvent
from api.services.agent.work_graph.api_contract import (
    WorkGraphExternalEdgeInput,
    WorkGraphExternalNodeInput,
    WorkGraphIngestRequest,
    WorkGraphNodeEvidenceAttachRequest,
    WorkGraphNodeStatusUpdateRequest,
)


def _build_store(tmp_path, monkeypatch) -> ActivityStore:
    monkeypatch.setattr("api.services.agent.activity._storage_root", lambda: tmp_path / "activity")
    return ActivityStore()


def _seed_run(store: ActivityStore) -> str:
    header = store.start_run(
        user_id="u1",
        conversation_id="c1",
        mode="company_agent",
        goal="External work graph contract",
    )
    store.append(
        AgentActivityEvent(
            event_id="evt-seed",
            run_id=header.run_id,
            event_type="plan.start",
            title="Seed event",
            seq=1,
            stage="system",
            status="in_progress",
            data={"event_family": "plan", "graph_node_id": "node.seed", "agent_role": "planner"},
            metadata={},
        )
    )
    return header.run_id


def test_work_graph_ingest_contract_appends_nodes_and_edges(tmp_path, monkeypatch) -> None:
    store = _build_store(tmp_path, monkeypatch)
    monkeypatch.setattr("api.routers.agent_api.work_graph.get_activity_store", lambda: store)
    run_id = _seed_run(store)

    response = work_graph.ingest_agent_run_work_graph(
        run_id=run_id,
        request=WorkGraphIngestRequest(
            source_system="external_suite",
            nodes=[
                WorkGraphExternalNodeInput(
                    id="node.research",
                    title="External research",
                    status="running",
                    agent_role="research",
                ),
                WorkGraphExternalNodeInput(
                    id="node.verify",
                    title="External verify",
                    status="queued",
                    agent_role="verifier",
                ),
            ],
            edges=[
                WorkGraphExternalEdgeInput(
                    source="node.research",
                    target="node.verify",
                    edge_family="dependency",
                    relation="depends_on",
                )
            ],
        ),
    )

    assert response["run_id"] == run_id
    assert response["ingested_nodes"] == 2
    assert response["ingested_edges"] == 1
    assert response["appended_events"] == 2

    payload = work_graph.get_agent_run_work_graph(run_id=run_id)
    node_ids = {row["id"] for row in payload["nodes"]}
    assert "node.research" in node_ids
    assert "node.verify" in node_ids
    assert any(
        edge["source"] == "node.research"
        and edge["target"] == "node.verify"
        and edge["edge_family"] == "dependency"
        for edge in payload["edges"]
    )


def test_work_graph_status_and_evidence_contract_updates_node(tmp_path, monkeypatch) -> None:
    store = _build_store(tmp_path, monkeypatch)
    monkeypatch.setattr("api.routers.agent_api.work_graph.get_activity_store", lambda: store)
    run_id = _seed_run(store)

    work_graph.ingest_agent_run_work_graph(
        run_id=run_id,
        request=WorkGraphIngestRequest(
            nodes=[WorkGraphExternalNodeInput(id="node.external", title="External node", status="running")],
        ),
    )
    status_response = work_graph.update_agent_run_work_graph_node_status(
        run_id=run_id,
        node_id="node.external",
        request=WorkGraphNodeStatusUpdateRequest(
            status="blocked",
            detail="Verifier requested a re-check",
            confidence=0.42,
        ),
    )
    assert status_response["node_id"] == "node.external"
    assert status_response["appended_events"] == 1

    evidence_response = work_graph.attach_agent_run_work_graph_node_evidence(
        run_id=run_id,
        node_id="node.external",
        request=WorkGraphNodeEvidenceAttachRequest(
            evidence_refs=["ev-42"],
            detail="Primary citation",
        ),
    )
    assert evidence_response["node_id"] == "node.external"
    assert evidence_response["appended_events"] == 1

    payload = work_graph.get_agent_run_work_graph(run_id=run_id)
    node = next(row for row in payload["nodes"] if row["id"] == "node.external")
    assert node["status"] == "blocked"
    assert "ev-42" in node["evidence_refs"]
    assert any(edge["target"] == "evidence:ev-42" for edge in payload["edges"])


def test_work_graph_contract_raises_for_missing_run(tmp_path, monkeypatch) -> None:
    store = _build_store(tmp_path, monkeypatch)
    monkeypatch.setattr("api.routers.agent_api.work_graph.get_activity_store", lambda: store)
    with pytest.raises(HTTPException) as exc_info:
        work_graph.ingest_agent_run_work_graph(
            run_id="run-missing",
            request=WorkGraphIngestRequest(nodes=[WorkGraphExternalNodeInput(id="node.a", title="A")]),
        )
    assert exc_info.value.status_code == 404
