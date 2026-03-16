from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

WorkGraphNodeStatus = Literal["queued", "running", "completed", "failed", "blocked"]
WorkGraphEdgeFamily = Literal["hierarchy", "dependency", "evidence", "verification", "handoff"]


class WorkGraphNode(BaseModel):
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
    started_at: str | None = None
    ended_at: str | None = None
    duration_ms: int | None = None
    event_index_start: int | None = None
    event_index_end: int | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    scene_refs: list[str] = Field(default_factory=list)
    event_refs: list[str] = Field(default_factory=list)
    evidence_count: int = 0
    artifact_count: int = 0
    scene_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkGraphEdge(BaseModel):
    id: str
    source: str
    target: str
    edge_family: WorkGraphEdgeFamily
    relation: str = ""
    event_index: int | None = None
    weight: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkGraphPayload(BaseModel):
    version: int = 1
    map_type: str = "work_graph"
    kind: str = "work_graph"
    schema_version: str = "work_graph.v2"
    run_id: str
    title: str
    root_id: str
    nodes: list[WorkGraphNode] = Field(default_factory=list)
    edges: list[WorkGraphEdge] = Field(default_factory=list)
    graph: dict[str, Any] = Field(default_factory=dict)
    filters: dict[str, Any] = Field(default_factory=dict)

