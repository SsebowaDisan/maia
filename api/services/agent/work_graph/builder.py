from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import HTTPException

from api.services.agent.activity import ActivityStore, get_activity_store
from api.services.agent.work_graph.assembly import (
    add_edge,
    clean_text,
    normalize_events,
    positive_int,
    root_title,
    snapshot_by_event_id,
    upsert_node,
)
from api.services.agent.work_graph.models import WorkGraphEdge, WorkGraphNode, WorkGraphPayload
from api.services.agent.work_graph.normalize import duration_ms, normalize_status


class WorkGraphBuilder:
    def __init__(self, *, store: ActivityStore | None = None) -> None:
        self._store = store or get_activity_store()

    def build_for_run(
        self,
        *,
        run_id: str,
        agent_role: str = "",
        status: str = "",
        event_index_min: int = 0,
        event_index_max: int = 0,
    ) -> WorkGraphPayload:
        rows = self._store.load_events(run_id)
        if not rows:
            raise HTTPException(status_code=404, detail="Run events not found.")
        payload = self.build_from_rows(
            run_id=run_id,
            rows=rows,
            graph_snapshots=self._store.load_graph_snapshots(run_id),
            evidence_snapshots=self._store.load_evidence_snapshots(run_id),
            artifact_snapshots=self._store.load_artifact_snapshots(run_id),
        )
        self._persist_snapshot_if_needed(payload=payload)
        return self._apply_filters(
            payload=payload,
            agent_role=agent_role,
            status=status,
            event_index_min=event_index_min,
            event_index_max=event_index_max,
        )

    def build_replay_state_for_run(self, *, run_id: str) -> dict[str, Any]:
        payload = self.build_for_run(run_id=run_id)
        replay_state = self._store.load_replay_state(run_id)
        return {
            **replay_state,
            "work_graph": {
                "run_id": payload.run_id,
                "root_id": payload.root_id,
                "latest_event_index": replay_state.get("latest_event_index", 0),
                "active_node_ids": [
                    node.id
                    for node in payload.nodes
                    if node.id != payload.root_id and node.status in {"queued", "running", "blocked", "failed"}
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
                    for node in payload.nodes
                    if node.id != payload.root_id
                ],
            },
        }

    def build_from_rows(
        self,
        *,
        run_id: str,
        rows: list[dict[str, Any]],
        graph_snapshots: list[dict[str, Any]],
        evidence_snapshots: list[dict[str, Any]],
        artifact_snapshots: list[dict[str, Any]],
    ) -> WorkGraphPayload:
        root_id = f"run:{run_id}:root"
        root_node = WorkGraphNode(
            id=root_id,
            title=root_title(rows),
            detail="Run-scoped execution graph",
            node_type="task",
            status="running",
            event_refs=[],
        )
        nodes: dict[str, WorkGraphNode] = {root_id: root_node}
        edges: dict[str, WorkGraphEdge] = {}
        ordered_events = normalize_events(
            rows=rows,
            graph_snapshot_map=snapshot_by_event_id(graph_snapshots),
            evidence_snapshot_map=snapshot_by_event_id(evidence_snapshots),
            artifact_snapshot_map=snapshot_by_event_id(artifact_snapshots),
        )

        previous_primary_node_id = ""
        previous_non_verify_node_id = ""
        node_first_seen_index: dict[str, int] = defaultdict(lambda: 10**9)
        node_first_seen_index[root_id] = 0

        for event in ordered_events:
            if not event.graph_node_ids:
                event.graph_node_ids = [f"event:{event.event_id}"]
            primary_node_id = event.graph_node_ids[0]
            for index, node_id in enumerate(event.graph_node_ids):
                upsert_node(nodes=nodes, node_id=node_id, event=event, is_primary=index == 0)
                node_first_seen_index[node_id] = min(node_first_seen_index[node_id], event.event_index)
                if index > 0:
                    add_edge(
                        edges=edges,
                        source=primary_node_id,
                        target=node_id,
                        edge_family="dependency",
                        relation="co_reference",
                        event_index=event.event_index,
                    )

            if previous_primary_node_id and previous_primary_node_id != primary_node_id:
                add_edge(
                    edges=edges,
                    source=previous_primary_node_id,
                    target=primary_node_id,
                    edge_family="hierarchy",
                    relation="sequential",
                    event_index=event.event_index,
                )
            elif not previous_primary_node_id:
                add_edge(
                    edges=edges,
                    source=root_id,
                    target=primary_node_id,
                    edge_family="hierarchy",
                    relation="root",
                    event_index=event.event_index,
                )
            previous_primary_node_id = primary_node_id

            for dependency_id in event.dependencies:
                if dependency_id == primary_node_id:
                    continue
                if dependency_id not in nodes:
                    nodes[dependency_id] = WorkGraphNode(
                        id=dependency_id,
                        title=dependency_id,
                        detail="Dependency reference",
                        node_type="plan_step",
                        status="queued",
                    )
                add_edge(
                    edges=edges,
                    source=dependency_id,
                    target=primary_node_id,
                    edge_family="dependency",
                    relation="depends_on",
                    event_index=event.event_index,
                )

            raw_external_edges = event.data.get("external_edges")
            if isinstance(raw_external_edges, list):
                for row in raw_external_edges:
                    if not isinstance(row, dict):
                        continue
                    source_id = clean_text(row.get("source")) or primary_node_id
                    target_id = clean_text(row.get("target"))
                    if not source_id or not target_id or source_id == target_id:
                        continue
                    edge_family = clean_text(row.get("edge_family")).lower() or "dependency"
                    if edge_family not in {"hierarchy", "dependency", "evidence", "verification", "handoff"}:
                        edge_family = "dependency"
                    relation = clean_text(row.get("relation")) or "external"
                    if source_id not in nodes:
                        nodes[source_id] = WorkGraphNode(
                            id=source_id,
                            title=source_id,
                            detail="External reference source",
                            node_type="plan_step",
                            status="queued",
                        )
                        node_first_seen_index[source_id] = min(node_first_seen_index[source_id], event.event_index)
                    if target_id not in nodes:
                        nodes[target_id] = WorkGraphNode(
                            id=target_id,
                            title=target_id,
                            detail="External reference target",
                            node_type="plan_step",
                            status="queued",
                        )
                        node_first_seen_index[target_id] = min(node_first_seen_index[target_id], event.event_index)
                    add_edge(
                        edges=edges,
                        source=source_id,
                        target=target_id,
                        edge_family=edge_family,
                        relation=relation,
                        event_index=event.event_index,
                    )

            for evidence_ref in event.evidence_refs:
                evidence_node_id = f"evidence:{evidence_ref}"
                if evidence_node_id not in nodes:
                    nodes[evidence_node_id] = WorkGraphNode(
                        id=evidence_node_id,
                        title=evidence_ref,
                        detail="Evidence reference",
                        node_type="artifact",
                        status="completed",
                    )
                add_edge(
                    edges=edges,
                    source=primary_node_id,
                    target=evidence_node_id,
                    edge_family="evidence",
                    relation="supports",
                    event_index=event.event_index,
                )

            for artifact_ref in event.artifact_refs:
                artifact_node_id = f"artifact:{artifact_ref}"
                if artifact_node_id not in nodes:
                    nodes[artifact_node_id] = WorkGraphNode(
                        id=artifact_node_id,
                        title=artifact_ref,
                        detail="Artifact output",
                        node_type="artifact",
                        status="completed",
                    )
                add_edge(
                    edges=edges,
                    source=primary_node_id,
                    target=artifact_node_id,
                    edge_family="hierarchy",
                    relation="produces",
                    event_index=event.event_index,
                )

            event_family = clean_text(event.data.get("event_family")).lower()
            if event_family == "verify" and previous_non_verify_node_id:
                add_edge(
                    edges=edges,
                    source=previous_non_verify_node_id,
                    target=primary_node_id,
                    edge_family="verification",
                    relation="verified_by",
                    event_index=event.event_index,
                )
            if event.event_type in {"agent.handoff", "role_handoff"}:
                from_role = clean_text(event.data.get("from_role"))
                to_role = clean_text(event.data.get("to_role"))
                add_edge(
                    edges=edges,
                    source=previous_non_verify_node_id or root_id,
                    target=primary_node_id,
                    edge_family="handoff",
                    relation=f"{from_role}->{to_role}" if from_role or to_role else "handoff",
                    event_index=event.event_index,
                )
            if event_family != "verify":
                previous_non_verify_node_id = primary_node_id

        if ordered_events:
            root_node.event_index_start = ordered_events[0].event_index
            root_node.event_index_end = ordered_events[-1].event_index
            root_node.status = nodes.get(previous_primary_node_id, root_node).status
        root_node.started_at = min((node.started_at for node in nodes.values() if node.started_at), default=None)
        root_node.ended_at = max((node.ended_at for node in nodes.values() if node.ended_at), default=None)
        root_node.duration_ms = duration_ms(started_at=root_node.started_at, ended_at=root_node.ended_at)

        ordered_nodes = sorted(
            nodes.values(),
            key=lambda item: (node_first_seen_index.get(item.id, 10**9), item.event_index_start or 10**9, item.id),
        )
        ordered_edges = sorted(
            edges.values(),
            key=lambda item: (item.event_index or 0, item.source, item.target, item.edge_family),
        )
        return WorkGraphPayload(
            run_id=run_id,
            title=root_node.title,
            root_id=root_id,
            nodes=ordered_nodes,
            edges=ordered_edges,
            graph={
                "schema": "work_graph.v2",  # keep key name for wire-format compatibility

                "root_id": root_id,
                "nodes": [node.model_dump(mode="json") for node in ordered_nodes],
                "edges": [edge.model_dump(mode="json") for edge in ordered_edges],
            },
        )

    def _apply_filters(
        self,
        *,
        payload: WorkGraphPayload,
        agent_role: str,
        status: str,
        event_index_min: int,
        event_index_max: int,
    ) -> WorkGraphPayload:
        role_filter = clean_text(agent_role).lower()
        status_filter = normalize_status(status) if clean_text(status) else ""
        min_index = positive_int(event_index_min)
        max_index = positive_int(event_index_max)

        keep_ids: set[str] = {payload.root_id}
        for node in payload.nodes:
            if node.id == payload.root_id:
                continue
            if role_filter and clean_text(node.agent_role).lower() != role_filter:
                continue
            if status_filter and node.status != status_filter:
                continue
            if min_index and (node.event_index_end or 0) < min_index:
                continue
            if max_index and (node.event_index_start or 0) > max_index:
                continue
            keep_ids.add(node.id)

        if len(keep_ids) > 1:
            for edge in payload.edges:
                if edge.source in keep_ids and (
                    edge.edge_family == "evidence" or clean_text(edge.relation) == "produces"
                ):
                    keep_ids.add(edge.target)

        filtered_nodes = [node for node in payload.nodes if node.id in keep_ids]
        filtered_edges = [edge for edge in payload.edges if edge.source in keep_ids and edge.target in keep_ids]
        payload_data = payload.model_dump(mode="python")
        payload_data["nodes"] = filtered_nodes
        payload_data["edges"] = filtered_edges
        payload_data["graph"] = {
            "schema": payload.schema_version,
            "root_id": payload.root_id,
            "nodes": [node.model_dump(mode="json") for node in filtered_nodes],
            "edges": [edge.model_dump(mode="json") for edge in filtered_edges],
        }
        payload_data["filters"] = {
            "agent_role": role_filter,
            "status": status_filter,
            "event_index_min": min_index,
            "event_index_max": max_index,
        }
        return WorkGraphPayload(**payload_data)

    def _persist_snapshot_if_needed(self, *, payload: WorkGraphPayload) -> None:
        latest_event_index = max((node.event_index_end or 0) for node in payload.nodes)
        if latest_event_index <= 0:
            return
        existing = self._store.load_work_graph_snapshots(payload.run_id)
        if existing and max(positive_int(row.get("event_index")) for row in existing) >= latest_event_index:
            return
        self._store.append_work_graph_snapshot(
            run_id=payload.run_id,
            event_index=latest_event_index,
            schema_version=payload.schema,
            graph_payload={
                "run_id": payload.run_id,
                "root_id": payload.root_id,
                "title": payload.title,
                "schema": payload.schema_version,
                "nodes": [node.model_dump(mode="json") for node in payload.nodes],
                "edges": [edge.model_dump(mode="json") for edge in payload.edges],
            },
        )


__all__ = ["WorkGraphBuilder"]
