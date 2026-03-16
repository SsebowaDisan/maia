"""Workflow SSE event contracts.

All events emitted by workflow_executor.py and streamed to the frontend
over the /api/workflows/{id}/run SSE endpoint inherit from WorkflowEventBase.

The ``event_type`` discriminator matches what the executor already emits so
the frontend can switch on a single string field.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class WorkflowEventBase(BaseModel):
    event_type: str
    workflow_id: str


class WorkflowStartedEvent(WorkflowEventBase):
    event_type: Literal["workflow_started"] = "workflow_started"
    step_count: int
    step_order: list[str]


class StepStartedEvent(WorkflowEventBase):
    event_type: Literal["workflow_step_started"] = "workflow_step_started"
    step_id: str
    agent_id: str


class StepProgressEvent(WorkflowEventBase):
    """Streaming text delta from the agent running this step."""
    event_type: Literal["workflow_step_progress"] = "workflow_step_progress"
    step_id: str
    agent_id: str
    delta: str


class StepCompletedEvent(WorkflowEventBase):
    event_type: Literal["workflow_step_completed"] = "workflow_step_completed"
    step_id: str
    agent_id: str
    output_key: str
    result_preview: str
    duration_ms: int


class StepSkippedEvent(WorkflowEventBase):
    event_type: Literal["workflow_step_skipped"] = "workflow_step_skipped"
    step_id: str
    reason: str = "condition_false"


class StepFailedEvent(WorkflowEventBase):
    event_type: Literal["workflow_step_failed"] = "workflow_step_failed"
    step_id: str
    error: str
    retryable: bool = False


class WorkflowCompletedEvent(WorkflowEventBase):
    event_type: Literal["workflow_completed"] = "workflow_completed"
    outputs: dict[str, str]
    duration_ms: int


class WorkflowFailedEvent(WorkflowEventBase):
    event_type: Literal["workflow_failed"] = "workflow_failed"
    failed_step_id: Optional[str] = None
    error: str


# ── Run history record ─────────────────────────────────────────────────────────

class StepRunResult(BaseModel):
    step_id: str
    agent_id: str
    status: Literal["completed", "failed", "skipped"]
    output_preview: str = ""
    error: str = ""
    duration_ms: int = 0


class WorkflowRunRecord(BaseModel):
    """Persisted record for a single workflow execution."""
    run_id: str
    workflow_id: str
    tenant_id: str
    status: Literal["running", "completed", "failed"]
    started_at: float
    finished_at: Optional[float] = None
    duration_ms: int = 0
    step_results: list[StepRunResult] = Field(default_factory=list)
    final_outputs: dict[str, str] = Field(default_factory=dict)
    error: str = ""
