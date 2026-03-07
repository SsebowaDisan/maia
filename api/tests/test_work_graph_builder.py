from __future__ import annotations

from api.services.agent.activity import ActivityStore
from api.services.agent.models import AgentActivityEvent
from api.services.agent.work_graph.builder import WorkGraphBuilder


def _build_store(tmp_path, monkeypatch) -> ActivityStore:
    monkeypatch.setattr("api.services.agent.activity._storage_root", lambda: tmp_path / "activity")
    return ActivityStore()


def test_work_graph_builder_materializes_nodes_edges_and_metadata(tmp_path, monkeypatch) -> None:
    store = _build_store(tmp_path, monkeypatch)
    header = store.start_run(
        user_id="u1",
        conversation_id="c1",
        mode="company_agent",
        goal="Prepare machine-learning report and email",
    )
    store.append(
        AgentActivityEvent(
            event_id="evt-1",
            run_id=header.run_id,
            event_type="plan_ready",
            title="Plan finalized",
            seq=1,
            stage="plan",
            status="completed",
            data={
                "event_family": "plan",
                "graph_node_id": "node.plan",
                "agent_id": "agent.planner",
                "agent_role": "planner",
                "agent_label": "Planner",
                "agent_color": "#7c3aed",
                "scene_ref": "scene.plan",
            },
            metadata={},
        )
    )
    store.append(
        AgentActivityEvent(
            event_id="evt-2",
            run_id=header.run_id,
            event_type="browser_extract",
            title="Collected source evidence",
            seq=2,
            stage="tool",
            status="in_progress",
            data={
                "event_family": "browser",
                "graph_node_id": "node.research",
                "agent_role": "research",
                "evidence_refs": ["ev-1", "ev-2"],
                "scene_refs": ["scene.browser.main"],
            },
            metadata={},
        )
    )
    store.append(
        AgentActivityEvent(
            event_id="evt-3",
            run_id=header.run_id,
            event_type="verification_completed",
            title="Verification passed",
            seq=3,
            stage="result",
            status="completed",
            data={
                "event_family": "verify",
                "graph_node_id": "node.verify",
                "depends_on": ["node.research"],
                "confidence": 0.82,
                "scene_ref": "scene.verify.main",
            },
            metadata={},
        )
    )
    store.append(
        AgentActivityEvent(
            event_id="evt-4",
            run_id=header.run_id,
            event_type="agent.handoff",
            title="Handoff to writer",
            seq=4,
            stage="tool",
            status="completed",
            data={
                "event_family": "plan",
                "graph_node_id": "node.handoff",
                "from_role": "research",
                "to_role": "writer",
                "agent_role": "writer",
                "artifact_refs": ["artifact.report"],
            },
            metadata={},
        )
    )

    payload = WorkGraphBuilder(store=store).build_for_run(run_id=header.run_id)

    assert payload.run_id == header.run_id
    assert payload.root_id == f"run:{header.run_id}:root"
    assert payload.title == "Prepare machine-learning report and email"
    assert any(node.id == "node.research" for node in payload.nodes)
    research = next(node for node in payload.nodes if node.id == "node.research")
    assert research.agent_role == "research"
    assert research.scene_refs == ["scene.browser.main"]
    assert research.evidence_refs == ["ev-1", "ev-2"]
    assert research.event_refs == ["evt-2"]
    assert research.event_index_start == 2
    assert research.event_index_end == 2

    edge_families = {edge.edge_family for edge in payload.edges}
    assert "hierarchy" in edge_families
    assert "dependency" in edge_families
    assert "evidence" in edge_families
    assert "verification" in edge_families
    assert "handoff" in edge_families
    assert payload.graph.get("schema") == "work_graph.v2"


def test_work_graph_builder_reconstructs_order_from_event_index(tmp_path, monkeypatch) -> None:
    store = _build_store(tmp_path, monkeypatch)
    header = store.start_run(
        user_id="u2",
        conversation_id="c2",
        mode="company_agent",
        goal="Ordering check",
    )
    store.append(
        AgentActivityEvent(
            event_id="evt-a",
            run_id=header.run_id,
            event_type="tool_progress",
            title="Late step",
            seq=0,
            data={
                "event_family": "plan",
                "graph_node_id": "node.late",
                "event_index": 8,
            },
            metadata={},
        )
    )
    store.append(
        AgentActivityEvent(
            event_id="evt-b",
            run_id=header.run_id,
            event_type="tool_progress",
            title="Early step",
            seq=0,
            data={
                "event_family": "plan",
                "graph_node_id": "node.early",
                "event_index": 2,
            },
            metadata={},
        )
    )

    payload = WorkGraphBuilder(store=store).build_for_run(run_id=header.run_id)
    early = next(node for node in payload.nodes if node.id == "node.early")
    late = next(node for node in payload.nodes if node.id == "node.late")
    assert early.event_index_start == 2
    assert late.event_index_start == 8
    assert payload.nodes[0].id == payload.root_id
    assert payload.nodes[1].id == "node.early"
    assert payload.nodes[2].id == "node.late"


def test_work_graph_builder_filters_agent_status_and_event_window(tmp_path, monkeypatch) -> None:
    store = _build_store(tmp_path, monkeypatch)
    header = store.start_run(
        user_id="u3",
        conversation_id="c3",
        mode="company_agent",
        goal="Filter check",
    )
    store.append(
        AgentActivityEvent(
            event_id="evt-plan",
            run_id=header.run_id,
            event_type="plan_ready",
            title="Plan",
            seq=1,
            status="completed",
            data={
                "event_family": "plan",
                "graph_node_id": "node.plan",
                "agent_role": "planner",
            },
            metadata={},
        )
    )
    store.append(
        AgentActivityEvent(
            event_id="evt-browser",
            run_id=header.run_id,
            event_type="browser_extract",
            title="Research",
            seq=2,
            status="in_progress",
            data={
                "event_family": "browser",
                "graph_node_id": "node.browser",
                "agent_role": "research",
            },
            metadata={},
        )
    )

    payload = WorkGraphBuilder(store=store).build_for_run(
        run_id=header.run_id,
        agent_role="research",
        status="running",
        event_index_min=2,
        event_index_max=3,
    )
    node_ids = {node.id for node in payload.nodes}
    assert payload.root_id in node_ids
    assert "node.browser" in node_ids
    assert "node.plan" not in node_ids
    assert payload.filters["agent_role"] == "research"
    assert payload.filters["status"] == "running"

