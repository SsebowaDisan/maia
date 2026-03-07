from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone

from api.services.agent.work_graph.api_contract import (
    WorkGraphAnalyticsResponse,
    WorkGraphCongestionItem,
    WorkGraphRiskCluster,
    WorkGraphVerifierHotspotItem,
)
from api.services.agent.work_graph.models import WorkGraphPayload

PATH_EDGE_FAMILIES = {"hierarchy", "dependency", "handoff"}


def _event_index_by_node(payload: WorkGraphPayload) -> dict[str, int]:
    output: dict[str, int] = {}
    for node in payload.nodes:
        index = int(node.event_index_start or node.event_index_end or 0)
        output[node.id] = max(index, 0)
    return output


def _critical_path(payload: WorkGraphPayload) -> tuple[list[str], int]:
    order = _event_index_by_node(payload)
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in payload.edges:
        if edge.edge_family not in PATH_EDGE_FAMILIES:
            continue
        source_index = order.get(edge.source, 0)
        target_index = order.get(edge.target, 0)
        if source_index and target_index and source_index > target_index:
            continue
        adjacency[edge.source].append(edge.target)

    nodes_sorted = sorted(payload.nodes, key=lambda node: (order.get(node.id, 0), node.id))
    score: dict[str, int] = {node.id: 1 for node in nodes_sorted}
    parent: dict[str, str] = {}

    for node in nodes_sorted:
        source_score = score.get(node.id, 1)
        for target in adjacency.get(node.id, []):
            if source_score + 1 > score.get(target, 1):
                score[target] = source_score + 1
                parent[target] = node.id

    if not score:
        return ([], 0)
    end_node_id = max(score, key=score.get)
    path = [end_node_id]
    while path[-1] in parent:
        path.append(parent[path[-1]])
    path.reverse()
    return (path, score.get(end_node_id, len(path)))


def _branch_congestion(payload: WorkGraphPayload) -> list[WorkGraphCongestionItem]:
    node_title = {node.id: node.title for node in payload.nodes}
    outgoing = defaultdict(int)
    for edge in payload.edges:
        if edge.edge_family not in PATH_EDGE_FAMILIES:
            continue
        outgoing[edge.source] += 1
    rows = [
        WorkGraphCongestionItem(
            node_id=node_id,
            title=node_title.get(node_id, node_id),
            outgoing_edges=count,
        )
        for node_id, count in outgoing.items()
        if count >= 2
    ]
    rows.sort(key=lambda row: (-row.outgoing_edges, row.node_id))
    return rows[:8]


def _verifier_hotspots(payload: WorkGraphPayload) -> list[WorkGraphVerifierHotspotItem]:
    verification_targets = {
        edge.target for edge in payload.edges if edge.edge_family == "verification"
    }
    rows: list[WorkGraphVerifierHotspotItem] = []
    for node in payload.nodes:
        reasons: list[str] = []
        if node.node_type == "verification":
            reasons.append("verification_node")
        if node.id in verification_targets:
            reasons.append("verification_target")
        if node.status in {"failed", "blocked"}:
            reasons.append("execution_risk")
        if isinstance(node.confidence, float) and node.confidence < 0.6:
            reasons.append("low_confidence")
        if not reasons:
            continue
        rows.append(
            WorkGraphVerifierHotspotItem(
                node_id=node.id,
                title=node.title,
                status=node.status,
                confidence=node.confidence,
                evidence_count=node.evidence_count,
                reasons=reasons,
            )
        )
    rows.sort(
        key=lambda row: (
            -len(row.reasons),
            row.status != "blocked",
            row.status != "failed",
            row.node_id,
        )
    )
    return rows[:12]


def _low_confidence_clusters(payload: WorkGraphPayload) -> list[WorkGraphRiskCluster]:
    risk_nodes = {
        node.id
        for node in payload.nodes
        if node.status in {"blocked", "failed"}
        or (isinstance(node.confidence, float) and node.confidence < 0.6)
    }
    if not risk_nodes:
        return []

    node_confidence = {node.id: node.confidence for node in payload.nodes}
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in payload.edges:
        if edge.source in risk_nodes and edge.target in risk_nodes:
            adjacency[edge.source].add(edge.target)
            adjacency[edge.target].add(edge.source)

    clusters: list[WorkGraphRiskCluster] = []
    visited: set[str] = set()
    cluster_index = 0
    for node_id in sorted(risk_nodes):
        if node_id in visited:
            continue
        queue = deque([node_id])
        visited.add(node_id)
        members: list[str] = []
        while queue:
            current = queue.popleft()
            members.append(current)
            for neighbor in adjacency.get(current, set()):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                queue.append(neighbor)
        cluster_index += 1
        confidences = [
            float(node_confidence.get(member))
            for member in members
            if isinstance(node_confidence.get(member), float)
        ]
        average_confidence = (
            round(sum(confidences) / len(confidences), 4) if confidences else None
        )
        clusters.append(
            WorkGraphRiskCluster(
                cluster_id=f"cluster-{cluster_index}",
                node_ids=members,
                node_count=len(members),
                average_confidence=average_confidence,
            )
        )
    clusters.sort(key=lambda row: (-row.node_count, row.cluster_id))
    return clusters


def build_work_graph_analytics(payload: WorkGraphPayload) -> WorkGraphAnalyticsResponse:
    critical_path_node_ids, critical_path_score = _critical_path(payload)
    branch_congestion = _branch_congestion(payload)
    verifier_hotspots = _verifier_hotspots(payload)
    low_confidence_clusters = _low_confidence_clusters(payload)

    return WorkGraphAnalyticsResponse(
        run_id=payload.run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        critical_path_node_ids=critical_path_node_ids,
        critical_path_score=critical_path_score,
        branch_congestion=branch_congestion,
        verifier_hotspots=verifier_hotspots,
        low_confidence_clusters=low_confidence_clusters,
        summary={
            "node_count": len(payload.nodes),
            "edge_count": len(payload.edges),
            "hotspot_count": len(verifier_hotspots),
            "risk_cluster_count": len(low_confidence_clusters),
        },
    )


__all__ = ["build_work_graph_analytics"]
