from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from api.services.agent.work_graph.models import WorkGraphEdgeFamily, WorkGraphNodeStatus


class WorkGraphExternalNodeInput(BaseModel):
    id: str
    title: str
    detail: str = ""
    node_type: str = "plan_step"
    status: WorkGraphNodeStatus = "queued"
    agent_id: str | None = None
    agent_role: str | None = None
    agent_label: str | None = None
    agent_color: str | None = None
    confidence: float | None = None
    progress: float | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    scene_refs: list[str] = Field(default_factory=list)
    event_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkGraphExternalEdgeInput(BaseModel):
    source: str
    target: str
    edge_family: WorkGraphEdgeFamily = "dependency"
    relation: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkGraphIngestRequest(BaseModel):
    source_system: str = "external_agent"
    event_type: str = "external.work_graph_ingest"
    title: str = "External work graph update"
    detail: str = ""
    agent_id: str | None = None
    agent_role: str | None = None
    agent_label: str | None = None
    agent_color: str | None = None
    nodes: list[WorkGraphExternalNodeInput] = Field(default_factory=list)
    edges: list[WorkGraphExternalEdgeInput] = Field(default_factory=list)


class WorkGraphNodeStatusUpdateRequest(BaseModel):
    status: WorkGraphNodeStatus
    detail: str = ""
    confidence: float | None = None
    progress: float | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    scene_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkGraphNodeEvidenceAttachRequest(BaseModel):
    evidence_refs: list[str] = Field(default_factory=list)
    detail: str = ""
    scene_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkGraphNodeRange(BaseModel):
    node_id: str
    status: str = ""
    agent_role: str | None = None
    event_index_start: int | None = None
    event_index_end: int | None = None
    scene_refs: list[str] = Field(default_factory=list)
    event_refs: list[str] = Field(default_factory=list)


class WorkGraphReplayStateSlice(BaseModel):
    run_id: str
    root_id: str
    filters: dict[str, Any] = Field(default_factory=dict)
    active_node_ids: list[str] = Field(default_factory=list)
    node_ranges: list[WorkGraphNodeRange] = Field(default_factory=list)


class WorkGraphReplayStateResponse(BaseModel):
    run_id: str
    latest_event_index: int = 0
    graph_snapshots: list[dict[str, Any]] = Field(default_factory=list)
    evidence_snapshots: list[dict[str, Any]] = Field(default_factory=list)
    artifact_snapshots: list[dict[str, Any]] = Field(default_factory=list)
    work_graph: WorkGraphReplayStateSlice


class WorkGraphMutationResponse(BaseModel):
    run_id: str
    node_id: str | None = None
    ingested_nodes: int = 0
    ingested_edges: int = 0
    appended_events: int = 0
    event_ids: list[str] = Field(default_factory=list)
    latest_event_index: int = 0


class WorkGraphCongestionItem(BaseModel):
    node_id: str
    title: str
    outgoing_edges: int = 0


class WorkGraphVerifierHotspotItem(BaseModel):
    node_id: str
    title: str
    status: str = ""
    confidence: float | None = None
    evidence_count: int = 0
    reasons: list[str] = Field(default_factory=list)


class WorkGraphRiskCluster(BaseModel):
    cluster_id: str
    node_ids: list[str] = Field(default_factory=list)
    node_count: int = 0
    average_confidence: float | None = None


class WorkGraphAnalyticsResponse(BaseModel):
    run_id: str
    generated_at: str
    critical_path_node_ids: list[str] = Field(default_factory=list)
    critical_path_score: int = 0
    branch_congestion: list[WorkGraphCongestionItem] = Field(default_factory=list)
    verifier_hotspots: list[WorkGraphVerifierHotspotItem] = Field(default_factory=list)
    low_confidence_clusters: list[WorkGraphRiskCluster] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
