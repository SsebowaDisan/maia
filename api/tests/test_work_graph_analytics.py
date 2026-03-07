from __future__ import annotations

from api.routers.agent_api import work_graph
from api.services.agent.activity import ActivityStore
from api.services.agent.models import AgentActivityEvent
from api.services.agent.work_graph.analytics import build_work_graph_analytics
from api.services.agent.work_graph.models import WorkGraphEdge, WorkGraphNode, WorkGraphPayload


def _build_store(tmp_path, monkeypatch) -> ActivityStore:
    monkeypatch.setattr("api.services.agent.activity._storage_root", lambda: tmp_path / "activity")
    return ActivityStore()


def test_build_work_graph_analytics_computes_critical_path_and_clusters() -> None:
    payload = WorkGraphPayload(
        run_id="run-1",
        title="Analytics",
        root_id="run:run-1:root",
        nodes=[
            WorkGraphNode(id="run:run-1:root", title="Root", event_index_start=1, event_index_end=1),
            WorkGraphNode(id="node.plan", title="Plan", event_index_start=2, event_index_end=2, status="completed"),
            WorkGraphNode(id="node.research", title="Research", event_index_start=3, event_index_end=3, status="running"),
            WorkGraphNode(
                id="node.verify",
                title="Verify",
                node_type="verification",
                status="blocked",
                confidence=0.45,
                event_index_start=4,
                event_index_end=4,
            ),
        ],
        edges=[
            WorkGraphEdge(id="h1", source="run:run-1:root", target="node.plan", edge_family="hierarchy"),
            WorkGraphEdge(id="h2", source="node.plan", target="node.research", edge_family="hierarchy"),
            WorkGraphEdge(id="v1", source="node.research", target="node.verify", edge_family="verification"),
        ],
    )

    analytics = build_work_graph_analytics(payload)
    assert analytics.run_id == "run-1"
    assert analytics.critical_path_node_ids[:2] == ["run:run-1:root", "node.plan"]
    assert analytics.critical_path_score >= 2
    assert analytics.verifier_hotspots
    assert analytics.low_confidence_clusters


def test_work_graph_analytics_router_returns_hotspots(tmp_path, monkeypatch) -> None:
    store = _build_store(tmp_path, monkeypatch)
    monkeypatch.setattr("api.routers.agent_api.work_graph.get_activity_store", lambda: store)
    header = store.start_run(
        user_id="u1",
        conversation_id="c1",
        mode="company_agent",
        goal="Work graph analytics",
    )
    store.append(
        AgentActivityEvent(
            event_id="evt-1",
            run_id=header.run_id,
            event_type="plan_step",
            title="Plan",
            seq=1,
            stage="system",
            status="completed",
            data={"event_family": "plan", "graph_node_id": "node.plan", "agent_role": "planner"},
            metadata={},
        )
    )
    store.append(
        AgentActivityEvent(
            event_id="evt-2",
            run_id=header.run_id,
            event_type="verify_step",
            title="Verify",
            seq=2,
            stage="tool",
            status="blocked",
            data={
                "event_family": "verify",
                "graph_node_id": "node.verify",
                "agent_role": "verifier",
                "depends_on": ["node.plan"],
                "confidence": 0.4,
            },
            metadata={},
        )
    )

    payload = work_graph.get_agent_run_work_graph_analytics(run_id=header.run_id)
    assert payload["run_id"] == header.run_id
    assert payload["summary"]["node_count"] >= 2
    assert payload["critical_path_node_ids"]
    assert any(item["node_id"] == "node.verify" for item in payload["verifier_hotspots"])
