"""ACP v1 type definitions — Pydantic models for all 6 primitives."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Literals ──────────────────────────────────────────────────────────────────

MessageIntent = Literal[
    "propose", "challenge", "clarify", "review",
    "handoff", "summarize", "agree", "escalate",
]

AgentMood = Literal[
    "neutral", "confident", "uncertain",
    "excited", "concerned", "focused",
]

DeliveryStatus = Literal[
    "draft", "queued", "sent", "delivered", "acknowledged", "failed",
]

AgentAvailability = Literal["available", "focused", "busy", "offline"]

TaskLifecycleStatus = Literal[
    "proposed", "accepted", "in_progress", "blocked", "completed", "rejected",
]

ActivityKind = Literal[
    "thinking", "searching", "reading", "writing",
    "browsing", "coding", "analyzing", "tool_calling",
    "waiting", "reviewing", "idle", "error",
]

ReviewVerdict = Literal["approve", "revise", "reject", "escalate"]

ArtifactKind = Literal[
    "text", "markdown", "json", "csv", "html",
    "code", "image", "pdf", "url", "binary",
]

EventType = Literal[
    "message", "handoff", "review",
    "artifact", "event", "capabilities",
]

Priority = Literal["low", "normal", "high", "critical"]


# ── Shared ────────────────────────────────────────────────────────────────────

class CostInfo(BaseModel):
    tokens_used: int = 0
    cost_usd: float = 0.0
    model: str | None = None


class AgentPresence(BaseModel):
    availability: AgentAvailability | None = None
    status_text: str | None = None
    current_focus: str | None = None
    current_task_id: str | None = None
    active_task_count: int | None = None
    last_seen_at: str | None = None


class ProgressInfo(BaseModel):
    current: int = 0
    total: int = 0
    percentage: float | None = None


class ToolActivity(BaseModel):
    tool_id: str
    tool_name: str | None = None
    connector_id: str | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    status: Literal["started", "running", "completed", "failed"] = "started"


class BrowserActivity(BaseModel):
    url: str
    title: str | None = None
    screenshot_url: str | None = None
    action: Literal["navigate", "click", "type", "scroll", "extract"] | None = None


class AgentPersonality(BaseModel):
    style: Literal["concise", "detailed", "conversational", "formal", "creative"] | None = None
    traits: list[str] = Field(default_factory=list)
    avatar_color: str | None = None
    avatar_emoji: str | None = None


class AgentSkill(BaseModel):
    skill_id: str
    description: str
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None


class ReviewIssue(BaseModel):
    severity: Literal["minor", "major", "critical"]
    description: str
    location: str | None = None


# ── Primitives ────────────────────────────────────────────────────────────────

class ACPMessage(BaseModel):
    from_agent: str = Field(alias="from")
    to: str
    intent: MessageIntent
    content: str
    artifacts: list[ACPArtifact] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    thinking: str | None = None
    mood: AgentMood | None = None

    model_config = {"populate_by_name": True}


class HandoffTask(BaseModel):
    task_id: str | None = None
    thread_id: str | None = None
    description: str
    constraints: list[str] = Field(default_factory=list)
    definition_of_done: str | None = None
    deadline_seconds: int | None = None
    priority: Priority = "normal"
    owner_agent_id: str | None = None
    status: TaskLifecycleStatus | None = None
    blockers: list[str] = Field(default_factory=list)


class PriorStep(BaseModel):
    agent_id: str
    summary: str
    status: Literal["completed", "partial", "failed"]


class ACPHandoff(BaseModel):
    from_agent: str = Field(alias="from")
    to: str
    task: HandoffTask
    handoff_id: str | None = None
    status: TaskLifecycleStatus | None = None
    requires_ack: bool | None = None
    accepted_by: str | None = None
    declined_reason: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[ACPArtifact] = Field(default_factory=list)
    prior_steps: list[PriorStep] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class ACPReview(BaseModel):
    reviewer: str
    author: str
    artifact_id: str | None = None
    verdict: ReviewVerdict
    score: float | None = None
    feedback: str | None = None
    revision_instructions: str | None = None
    strengths: list[str] = Field(default_factory=list)
    issues: list[ReviewIssue] = Field(default_factory=list)
    round: int = 1
    max_rounds: int = 3


class ACPArtifact(BaseModel):
    artifact_id: str
    kind: ArtifactKind
    title: str | None = None
    content: str = ""
    content_url: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    checksum: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    version: int = 1
    parent_artifact_id: str | None = None


class ACPActivity(BaseModel):
    agent_id: str
    activity: ActivityKind
    detail: str | None = None
    tool: ToolActivity | None = None
    browser: BrowserActivity | None = None
    progress: ProgressInfo | None = None
    cost: CostInfo | None = None


class ACPCapabilities(BaseModel):
    agent_id: str
    name: str
    description: str | None = None
    role: str | None = None
    personality: AgentPersonality | None = None
    skills: list[AgentSkill] = Field(default_factory=list)
    connectors: list[str] = Field(default_factory=list)
    accepts_intents: list[MessageIntent] = Field(default_factory=list)
    max_concurrent_tasks: int = 1
    presence: AgentPresence | None = None
    cost_per_invocation: CostInfo | None = None


# ── Event Envelope ────────────────────────────────────────────────────────────

class ACPEvent(BaseModel):
    acp_version: str = "1.0"
    run_id: str
    agent_id: str
    event_type: EventType
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    sequence: int | None = None
    parent_event_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    def as_message(self) -> ACPMessage:
        return ACPMessage.model_validate(self.payload)

    def as_handoff(self) -> ACPHandoff:
        return ACPHandoff.model_validate(self.payload)

    def as_review(self) -> ACPReview:
        return ACPReview.model_validate(self.payload)

    def as_artifact(self) -> ACPArtifact:
        return ACPArtifact.model_validate(self.payload)

    def as_activity(self) -> ACPActivity:
        return ACPActivity.model_validate(self.payload)

    def as_capabilities(self) -> ACPCapabilities:
        return ACPCapabilities.model_validate(self.payload)
