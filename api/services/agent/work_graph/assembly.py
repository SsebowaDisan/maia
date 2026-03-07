from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from api.services.agent.work_graph.models import WorkGraphEdge, WorkGraphNode
from api.services.agent.work_graph.normalize import (
    bounded_float,
    clean_text,
    duration_ms,
    infer_node_type,
    normalize_status,
    parse_iso_datetime,
    positive_int,
    progress_percent,
    status_precedence,
    unique_strings,
)


def as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def snapshot_by_event_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        event_id = clean_text(row.get("event_id"))
        if not event_id:
            continue
        output[event_id] = dict(row)
    return output


def event_index_from_payload(payload: dict[str, Any], fallback_index: int) -> int:
    data = as_dict(payload.get("data"))
    event_index = positive_int(data.get("event_index"))
    if event_index <= 0:
        event_index = positive_int(payload.get("event_index"))
    if event_index <= 0:
        event_index = positive_int(payload.get("seq"))
    if event_index <= 0:
        event_index = fallback_index
    return event_index


def merge_sorted_unique(left: list[str], right: list[str]) -> list[str]:
    if not left and not right:
        return []
    return list(dict.fromkeys([*left, *right]))


def node_title_from_event(*, event_title: str, node_id: str, event_type: str) -> str:
    title = clean_text(event_title)
    if title:
        return title
    normalized_type = clean_text(event_type).replace("_", " ").replace(".", " ").strip()
    if normalized_type:
        return normalized_type[:1].upper() + normalized_type[1:]
    return node_id


def root_title(rows: list[dict[str, Any]]) -> str:
    for row in rows:
        if row.get("type") != "run_started":
            continue
        payload = as_dict(row.get("payload"))
        goal = clean_text(payload.get("goal"))
        if goal:
            return goal
    return "Agent execution run"


@dataclass
class EventRow:
    event_id: str
    event_type: str
    event_index: int
    stage: str
    status: str
    title: str
    detail: str
    timestamp: str
    data: dict[str, Any]
    graph_node_ids: list[str]
    scene_refs: list[str]
    evidence_refs: list[str]
    artifact_refs: list[str]
    dependencies: list[str]


def normalize_events(
    *,
    rows: list[dict[str, Any]],
    graph_snapshot_map: dict[str, dict[str, Any]],
    evidence_snapshot_map: dict[str, dict[str, Any]],
    artifact_snapshot_map: dict[str, dict[str, Any]],
) -> list[EventRow]:
    event_rows: list[EventRow] = []
    fallback_index = 0
    for row in rows:
        if row.get("type") != "event":
            continue
        payload = as_dict(row.get("payload"))
        if not payload:
            continue
        event_id = clean_text(payload.get("event_id"))
        if not event_id:
            continue
        data = as_dict(payload.get("data"))
        fallback_index += 1
        event_index = event_index_from_payload(payload, fallback_index)
        event_type = clean_text(payload.get("event_type") or payload.get("type")) or "system_update"
        stage = clean_text(payload.get("stage") or data.get("stage") or "system")
        status = clean_text(payload.get("status") or data.get("status") or "info")
        title = clean_text(payload.get("title"))
        detail = clean_text(payload.get("detail"))
        timestamp = clean_text(payload.get("timestamp") or payload.get("ts"))

        graph_snapshot = graph_snapshot_map.get(event_id, {})
        evidence_snapshot = evidence_snapshot_map.get(event_id, {})
        artifact_snapshot = artifact_snapshot_map.get(event_id, {})

        graph_node_ids = unique_strings(data.get("graph_node_ids"))
        if not graph_node_ids:
            graph_node_ids = unique_strings(data.get("graph_node_id"))
        if not graph_node_ids:
            graph_node_ids = unique_strings(graph_snapshot.get("graph_node_ids"))

        scene_refs = merge_sorted_unique(
            unique_strings(data.get("scene_refs")) or unique_strings(data.get("scene_ref")),
            unique_strings(graph_snapshot.get("scene_refs")),
        )
        evidence_refs = merge_sorted_unique(
            unique_strings(data.get("evidence_refs")) or unique_strings(data.get("evidence_ids")),
            unique_strings(evidence_snapshot.get("evidence_refs")),
        )
        artifact_refs = merge_sorted_unique(
            unique_strings(data.get("artifact_refs")) or unique_strings(data.get("artifact_ids")),
            unique_strings(artifact_snapshot.get("artifact_refs")),
        )
        dependencies = merge_sorted_unique(
            unique_strings(data.get("depends_on")) or unique_strings(data.get("dependency_node_ids")),
            unique_strings(data.get("dependencies")),
        )
        event_rows.append(
            EventRow(
                event_id=event_id,
                event_type=event_type,
                event_index=event_index,
                stage=stage,
                status=status,
                title=title,
                detail=detail,
                timestamp=timestamp,
                data=data,
                graph_node_ids=graph_node_ids,
                scene_refs=scene_refs,
                evidence_refs=evidence_refs,
                artifact_refs=artifact_refs,
                dependencies=dependencies,
            )
        )
    event_rows.sort(key=lambda item: (item.event_index, item.timestamp, item.event_id))
    return event_rows


def upsert_node(
    *,
    nodes: dict[str, WorkGraphNode],
    node_id: str,
    event: EventRow,
    is_primary: bool,
) -> None:
    event_family = clean_text(event.data.get("event_family")) or "system"
    status = normalize_status(event.status)
    node_type = infer_node_type(event_type=event.event_type, event_family=event_family, data=event.data)
    confidence = bounded_float(event.data.get("confidence"), low=0.0, high=1.0)
    progress = progress_percent(event.data.get("progress"))
    agent_id = clean_text(event.data.get("agent_id")) or None
    agent_role = clean_text(event.data.get("agent_role")) or clean_text(event.data.get("owner_role")) or None
    agent_label = clean_text(event.data.get("agent_label")) or None
    agent_color = clean_text(event.data.get("agent_color")) or None
    started_at = clean_text(event.data.get("started_at")) or event.timestamp or None
    ended_at = clean_text(event.data.get("ended_at")) or None
    if status in {"completed", "failed", "blocked"} and not ended_at:
        ended_at = event.timestamp or None

    if node_id not in nodes:
        nodes[node_id] = WorkGraphNode(
            id=node_id,
            title=node_title_from_event(event_title=event.title, node_id=node_id, event_type=event.event_type),
            detail=event.detail or "",
            node_type=node_type,
            status=status,
            agent_id=agent_id,
            agent_role=agent_role,
            agent_label=agent_label,
            agent_color=agent_color,
            confidence=confidence,
            progress=progress,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=duration_ms(started_at=started_at, ended_at=ended_at),
            event_index_start=event.event_index,
            event_index_end=event.event_index,
            evidence_refs=list(event.evidence_refs),
            artifact_refs=list(event.artifact_refs),
            scene_refs=list(event.scene_refs),
            event_refs=[event.event_id],
            evidence_count=len(event.evidence_refs),
            artifact_count=len(event.artifact_refs),
            scene_count=len(event.scene_refs),
            metadata={
                "event_family": event_family,
                "event_type": event.event_type,
                "stage": event.stage,
                "is_primary": is_primary,
            },
        )
        return

    node = nodes[node_id]
    if is_primary and clean_text(event.title):
        node.title = node_title_from_event(event_title=event.title, node_id=node_id, event_type=event.event_type)
    if clean_text(event.detail):
        node.detail = clean_text(event.detail)
    if node.node_type == "plan_step" and node_type != "plan_step":
        node.node_type = node_type
    if status_precedence(status) >= status_precedence(node.status):
        node.status = status  # type: ignore[assignment]
    node.agent_id = node.agent_id or agent_id
    node.agent_role = node.agent_role or agent_role
    node.agent_label = node.agent_label or agent_label
    node.agent_color = node.agent_color or agent_color
    if confidence is not None:
        node.confidence = confidence
    if progress is not None:
        node.progress = progress
    if started_at and (
        not node.started_at
        or (parse_iso_datetime(started_at) and parse_iso_datetime(node.started_at) and parse_iso_datetime(started_at) < parse_iso_datetime(node.started_at))
    ):
        node.started_at = started_at
    if ended_at and (
        not node.ended_at
        or (parse_iso_datetime(ended_at) and parse_iso_datetime(node.ended_at) and parse_iso_datetime(ended_at) > parse_iso_datetime(node.ended_at))
    ):
        node.ended_at = ended_at
    node.duration_ms = duration_ms(started_at=node.started_at, ended_at=node.ended_at)
    node.event_index_start = min(node.event_index_start or event.event_index, event.event_index)
    node.event_index_end = max(node.event_index_end or event.event_index, event.event_index)
    node.evidence_refs = merge_sorted_unique(node.evidence_refs, event.evidence_refs)
    node.artifact_refs = merge_sorted_unique(node.artifact_refs, event.artifact_refs)
    node.scene_refs = merge_sorted_unique(node.scene_refs, event.scene_refs)
    node.event_refs = merge_sorted_unique(node.event_refs, [event.event_id])
    node.evidence_count = len(node.evidence_refs)
    node.artifact_count = len(node.artifact_refs)
    node.scene_count = len(node.scene_refs)
    families = merge_sorted_unique(unique_strings(node.metadata.get("event_families")), [event_family])
    node.metadata["event_families"] = families
    node.metadata["stage"] = event.stage
    node.metadata["event_type"] = event.event_type
    node.metadata["is_primary"] = bool(node.metadata.get("is_primary")) or is_primary


def add_edge(
    *,
    edges: dict[str, WorkGraphEdge],
    source: str,
    target: str,
    edge_family: str,
    relation: str,
    event_index: int,
) -> None:
    if not source or not target or source == target:
        return
    edge_id = f"{edge_family}:{source}->{target}:{relation}"
    existing = edges.get(edge_id)
    if existing is not None:
        existing.event_index = min(existing.event_index or event_index, event_index)
        return
    edges[edge_id] = WorkGraphEdge(
        id=edge_id,
        source=source,
        target=target,
        edge_family=edge_family,  # type: ignore[arg-type]
        relation=relation,
        event_index=event_index,
    )

