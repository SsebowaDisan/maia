from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from api.services.agent.activity import get_activity_store
from api.services.agent.models import AgentActivityEvent
from api.services.agent.work_graph.api_contract import (
    WorkGraphAnalyticsResponse,
    WorkGraphIngestRequest,
    WorkGraphMutationResponse,
    WorkGraphNodeEvidenceAttachRequest,
    WorkGraphNodeStatusUpdateRequest,
    WorkGraphReplayStateResponse,
)
from api.services.agent.work_graph.analytics import build_work_graph_analytics
from api.services.agent.work_graph.builder import WorkGraphBuilder
from api.services.agent.work_graph.models import WorkGraphPayload

router = APIRouter(tags=["agent"])


def _builder() -> WorkGraphBuilder:
    return WorkGraphBuilder(store=get_activity_store())


def _store():
    return get_activity_store()


def _ensure_run_exists(*, run_id: str) -> None:
    if not _store().load_events(run_id):
        raise HTTPException(status_code=404, detail="Run events not found.")


def _append_external_event(
    *,
    run_id: str,
    event_type: str,
    title: str,
    detail: str,
    status: str,
    data: dict[str, Any],
) -> str:
    event_id = f"external_{uuid4().hex}"
    _store().append(
        AgentActivityEvent(
            event_id=event_id,
            run_id=run_id,
            event_type=event_type,
            title=title,
            detail=detail,
            stage="tool",
            status=status,
            data=data,
            metadata=dict(data),
        )
    )
    return event_id


def _latest_event_index(*, run_id: str) -> int:
    replay_state = _store().load_replay_state(run_id)
    try:
        return int(replay_state.get("latest_event_index") or 0)
    except Exception:
        return 0


@router.get("/runs/{run_id}/work-graph", response_model=WorkGraphPayload)
def get_agent_run_work_graph(
    run_id: str,
    agent_role: str = "",
    status: str = "",
    event_index_min: int = 0,
    event_index_max: int = 0,
) -> dict[str, Any]:
    payload = _builder().build_for_run(
        run_id=run_id,
        agent_role=agent_role,
        status=status,
        event_index_min=event_index_min,
        event_index_max=event_index_max,
    )
    return payload.model_dump(mode="json")


@router.get("/runs/{run_id}/work-graph/replay-state", response_model=WorkGraphReplayStateResponse)
def get_agent_run_work_graph_replay_state(
    run_id: str,
    agent_role: str = "",
    status: str = "",
    event_index_min: int = 0,
    event_index_max: int = 0,
) -> dict[str, Any]:
    builder = _builder()
    replay_state = builder.build_replay_state_for_run(run_id=run_id)
    filtered_payload = builder.build_for_run(
        run_id=run_id,
        agent_role=agent_role,
        status=status,
        event_index_min=event_index_min,
        event_index_max=event_index_max,
    )
    replay_state["work_graph"] = {
        "run_id": filtered_payload.run_id,
        "root_id": filtered_payload.root_id,
        "filters": filtered_payload.filters,
        "active_node_ids": [
            node.id
            for node in filtered_payload.nodes
            if node.id != filtered_payload.root_id and node.status in {"queued", "running", "blocked", "failed"}
        ],
        "node_ranges": [
            {
                "node_id": node.id,
                "status": node.status,
                "agent_role": node.agent_role,
                "event_index_start": node.event_index_start,
                "event_index_end": node.event_index_end,
                "scene_refs": list(node.scene_refs),
                "event_refs": list(node.event_refs),
            }
            for node in filtered_payload.nodes
            if node.id != filtered_payload.root_id
        ],
    }
    return replay_state


@router.post("/runs/{run_id}/work-graph/ingest", response_model=WorkGraphMutationResponse)
def ingest_agent_run_work_graph(
    run_id: str,
    request: WorkGraphIngestRequest,
) -> dict[str, Any]:
    _ensure_run_exists(run_id=run_id)
    event_ids: list[str] = []
    edges_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    dependencies_by_target: dict[str, list[str]] = defaultdict(list)
    for edge in request.edges:
        edge_payload = edge.model_dump(mode="python")
        source_id = str(edge_payload.get("source") or "").strip()
        target_id = str(edge_payload.get("target") or "").strip()
        if not source_id or not target_id:
            continue
        edges_by_source[source_id].append(edge_payload)
        if edge.edge_family == "dependency":
            dependencies_by_target[target_id].append(source_id)

    if request.nodes:
        for node in request.nodes:
            node_payload = node.model_dump(mode="python")
            node_id = str(node_payload.get("id") or "").strip()
            if not node_id:
                continue
            event_data = {
                "event_family": "graph",
                "source_system": request.source_system,
                "graph_node_id": node_id,
                "graph_node_ids": [node_id],
                "node_type": node.node_type,
                "agent_id": node.agent_id or request.agent_id,
                "agent_role": node.agent_role or request.agent_role,
                "agent_label": node.agent_label or request.agent_label,
                "agent_color": node.agent_color or request.agent_color,
                "confidence": node.confidence,
                "progress": node.progress,
                "evidence_refs": list(node.evidence_refs),
                "artifact_refs": list(node.artifact_refs),
                "scene_refs": list(node.scene_refs),
                "event_refs": list(node.event_refs),
                "metadata": dict(node.metadata),
                "external_edges": edges_by_source.get(node_id, []),
            }
            dependency_rows = dependencies_by_target.get(node_id, [])
            if dependency_rows:
                event_data["depends_on"] = dependency_rows
            event_id = _append_external_event(
                run_id=run_id,
                event_type=request.event_type or "external.work_graph_ingest",
                title=node.title or request.title,
                detail=node.detail or request.detail or f"External upsert for {node_id}",
                status=node.status,
                data=event_data,
            )
            event_ids.append(event_id)
    elif request.edges:
        primary_node_id = request.edges[0].source
        event_ids.append(
            _append_external_event(
                run_id=run_id,
                event_type=request.event_type or "external.work_graph_ingest",
                title=request.title,
                detail=request.detail or "External edge update",
                status="in_progress",
                data={
                    "event_family": "graph",
                    "source_system": request.source_system,
                    "graph_node_id": primary_node_id,
                    "graph_node_ids": [primary_node_id],
                    "external_edges": [edge.model_dump(mode="python") for edge in request.edges],
                },
            )
        )

    return WorkGraphMutationResponse(
        run_id=run_id,
        ingested_nodes=len(request.nodes),
        ingested_edges=len(request.edges),
        appended_events=len(event_ids),
        event_ids=event_ids,
        latest_event_index=_latest_event_index(run_id=run_id),
    ).model_dump(mode="json")


@router.post(
    "/runs/{run_id}/work-graph/nodes/{node_id}/status",
    response_model=WorkGraphMutationResponse,
)
def update_agent_run_work_graph_node_status(
    run_id: str,
    node_id: str,
    request: WorkGraphNodeStatusUpdateRequest,
) -> dict[str, Any]:
    _ensure_run_exists(run_id=run_id)
    event_id = _append_external_event(
        run_id=run_id,
        event_type="external.work_graph_status_update",
        title=f"Update node {node_id}",
        detail=request.detail or f"Status updated to {request.status}",
        status=request.status,
        data={
            "event_family": "graph",
            "graph_node_id": node_id,
            "graph_node_ids": [node_id],
            "confidence": request.confidence,
            "progress": request.progress,
            "evidence_refs": list(request.evidence_refs),
            "artifact_refs": list(request.artifact_refs),
            "scene_refs": list(request.scene_refs),
            "metadata": dict(request.metadata),
        },
    )
    return WorkGraphMutationResponse(
        run_id=run_id,
        node_id=node_id,
        appended_events=1,
        event_ids=[event_id],
        latest_event_index=_latest_event_index(run_id=run_id),
    ).model_dump(mode="json")


@router.post(
    "/runs/{run_id}/work-graph/nodes/{node_id}/evidence",
    response_model=WorkGraphMutationResponse,
)
def attach_agent_run_work_graph_node_evidence(
    run_id: str,
    node_id: str,
    request: WorkGraphNodeEvidenceAttachRequest,
) -> dict[str, Any]:
    _ensure_run_exists(run_id=run_id)
    event_id = _append_external_event(
        run_id=run_id,
        event_type="external.work_graph_evidence_attach",
        title=f"Attach evidence to {node_id}",
        detail=request.detail or "Evidence linked to node",
        status="completed",
        data={
            "event_family": "graph",
            "graph_node_id": node_id,
            "graph_node_ids": [node_id],
            "evidence_refs": list(request.evidence_refs),
            "scene_refs": list(request.scene_refs),
            "metadata": dict(request.metadata),
        },
    )
    return WorkGraphMutationResponse(
        run_id=run_id,
        node_id=node_id,
        appended_events=1,
        event_ids=[event_id],
        latest_event_index=_latest_event_index(run_id=run_id),
    ).model_dump(mode="json")


@router.get(
    "/runs/{run_id}/work-graph/analytics",
    response_model=WorkGraphAnalyticsResponse,
)
def get_agent_run_work_graph_analytics(
    run_id: str,
    agent_role: str = "",
    status: str = "",
    event_index_min: int = 0,
    event_index_max: int = 0,
) -> dict[str, Any]:
    payload = _builder().build_for_run(
        run_id=run_id,
        agent_role=agent_role,
        status=status,
        event_index_min=event_index_min,
        event_index_max=event_index_max,
    )
    analytics = build_work_graph_analytics(payload)
    return analytics.model_dump(mode="json")
