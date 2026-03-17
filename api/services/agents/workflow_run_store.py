"""B11 — Workflow run history store.

Responsibility: persist workflow-level execution records so developers can
inspect past runs, see per-step outputs, and replay from any step.

Table: maia_workflow_run
  - One record per workflow execution
  - step_outputs_json: serialised dict mapping step_id → { output, status, duration_ms }
  - Replay from step N is supported by re-executing from that step using
    the stored step_outputs of all prior steps as the starting context.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Literal, Optional, Sequence

from sqlalchemy import Column
from sqlalchemy.types import JSON as SAJSON
from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine

WorkflowRunStatus = Literal["running", "completed", "failed", "partial"]


class WorkflowRunRecord(SQLModel, table=True):
    __tablename__ = "maia_workflow_run"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(index=True)
    workflow_id: str = Field(index=True)
    triggered_by: str = Field(default="manual")   # manual | scheduled | event
    status: str = Field(default="running")
    started_at: float = Field(default_factory=time.time)
    completed_at: Optional[float] = Field(default=None)
    error: Optional[str] = Field(default=None)
    # Per-step outputs: { step_id: { output, status, duration_ms, agent_id } }
    step_outputs: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(SAJSON),
    )


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


# ── Public API ──────────────────────────────────────────────────────────────────

def create_run(
    tenant_id: str,
    workflow_id: str,
    triggered_by: str = "manual",
) -> WorkflowRunRecord:
    _ensure_tables()
    record = WorkflowRunRecord(
        tenant_id=tenant_id,
        workflow_id=workflow_id,
        triggered_by=triggered_by,
    )
    with Session(engine) as session:
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


def record_step_output(
    run_id: str,
    step_id: str,
    agent_id: str,
    output: Any,
    status: str,
    duration_ms: int,
) -> None:
    """Persist the output of a single workflow step."""
    with Session(engine) as session:
        rec = session.get(WorkflowRunRecord, run_id)
        if not rec:
            return
        current = dict(rec.step_outputs or {})
        current[step_id] = {
            "agent_id": agent_id,
            "output": str(output)[:5_000],  # cap at 5 KB per step
            "status": status,
            "duration_ms": duration_ms,
        }
        rec.step_outputs = current
        session.add(rec)
        session.commit()


def complete_run(run_id: str) -> None:
    _update_run(run_id, status="completed")


def fail_run(run_id: str, error: str) -> None:
    _update_run(run_id, status="failed", error=error[:500])


def list_runs(
    tenant_id: str,
    workflow_id: str | None = None,
    *,
    limit: int = 50,
    offset: int = 0,
) -> Sequence[WorkflowRunRecord]:
    with Session(engine) as session:
        q = select(WorkflowRunRecord).where(WorkflowRunRecord.tenant_id == tenant_id)
        if workflow_id:
            q = q.where(WorkflowRunRecord.workflow_id == workflow_id)
        q = (
            q.order_by(WorkflowRunRecord.started_at.desc())  # type: ignore[attr-defined]
            .offset(offset)
            .limit(limit)
        )
        return session.exec(q).all()


def get_run(run_id: str) -> WorkflowRunRecord | None:
    with Session(engine) as session:
        return session.get(WorkflowRunRecord, run_id)


def get_step_outputs_for_replay(
    run_id: str,
    from_step_id: str,
    ordered_step_ids: list[str],
    step_output_keys: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return the stored outputs for all steps BEFORE from_step_id.

    Used by the replay endpoint to seed the context for partial re-execution.
    Results are keyed by output_key (not step_id) so the executor's
    _resolve_inputs can find them correctly.

    Args:
        step_output_keys: mapping of step_id → output_key. When provided,
            results are keyed by output_key. Falls back to step_id if missing.
    """
    rec = get_run(run_id)
    if not rec or not rec.step_outputs:
        return {}
    key_map = step_output_keys or {}
    pre_outputs: dict[str, Any] = {}
    for sid in ordered_step_ids:
        if sid == from_step_id:
            break
        step_data = rec.step_outputs.get(sid)
        if step_data:
            out_key = key_map.get(sid, sid)
            pre_outputs[out_key] = step_data.get("output", "")
    return pre_outputs


# ── Private helpers ────────────────────────────────────────────────────────────

def _update_run(run_id: str, **fields: Any) -> None:
    with Session(engine) as session:
        rec = session.get(WorkflowRunRecord, run_id)
        if rec:
            for k, v in fields.items():
                setattr(rec, k, v)
            # Only set completed_at when the run actually finishes
            new_status = fields.get("status")
            if new_status in ("completed", "failed"):
                rec.completed_at = time.time()
            session.add(rec)
            session.commit()
