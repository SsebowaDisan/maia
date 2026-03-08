from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
import uuid


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


@dataclass
class AgentActivityEvent:
    event_id: str
    run_id: str
    event_type: str
    title: str
    detail: str = ""
    timestamp: str = field(default_factory=lambda: utc_now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)
    seq: int = 0
    stage: str = "system"
    status: str = "info"
    event_schema_version: str = "1.0"
    snapshot_ref: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.data and self.metadata:
            self.data = dict(self.metadata)
        elif not self.metadata and self.data:
            self.metadata = dict(self.data)
        elif self.data and self.metadata and self.data != self.metadata:
            merged = dict(self.metadata)
            merged.update(self.data)
            self.data = merged
            self.metadata = dict(merged)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_schema_version": self.event_schema_version,
            "event_id": self.event_id,
            "run_id": self.run_id,
            "seq": self.seq,
            "ts": self.timestamp,
            "type": self.event_type,
            "stage": self.stage,
            "status": self.status,
            "title": self.title,
            "detail": self.detail,
            "data": self.data,
            "snapshot_ref": self.snapshot_ref,
            # Backward-compatible aliases used by current frontend.
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "metadata": self.data,
        }


@dataclass
class AgentAction:
    tool_id: str
    action_class: Literal["read", "draft", "execute"]
    status: Literal["success", "failed", "skipped"]
    summary: str
    started_at: str
    ended_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "action_class": self.action_class,
            "status": self.status,
            "summary": self.summary,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "metadata": self.metadata,
        }


@dataclass
class AgentSource:
    source_type: str
    label: str
    url: str | None = None
    file_id: str | None = None
    score: float | None = None
    credibility_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "label": self.label,
            "url": self.url,
            "file_id": self.file_id,
            "score": self.score,
            "credibility_score": self.credibility_score,
            "metadata": self.metadata,
        }


@dataclass
class AgentRunResult:
    run_id: str
    answer: str
    info_html: str
    actions_taken: list[AgentAction]
    sources_used: list[AgentSource]
    next_recommended_steps: list[str]
    evidence_items: list[dict[str, Any]] = field(default_factory=list)
    needs_human_review: bool = False
    human_review_notes: str = ""
    web_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "answer": self.answer,
            "info_html": self.info_html,
            "actions_taken": [item.to_dict() for item in self.actions_taken],
            "sources_used": [item.to_dict() for item in self.sources_used],
            "evidence_items": [dict(item) for item in self.evidence_items],
            "next_recommended_steps": self.next_recommended_steps,
            "needs_human_review": self.needs_human_review,
            "human_review_notes": self.human_review_notes,
            "web_summary": self.web_summary,
        }
