"""Task persistence models — audit trail for all queued tasks.

Every enqueued task gets a TaskRecord row so operators can inspect history,
debug failures, and rehydrate tasks after a crash.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Optional, Sequence

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine


class TaskRecord(SQLModel, table=True):
    __tablename__ = "maia_task"

    id: str = Field(primary_key=True)
    task_type: str = Field(index=True)
    tenant_id: str = Field(index=True)
    status: str = Field(
        default="queued",
        description='One of: "queued", "running", "completed", "failed", "dead_letter"',
    )
    payload_json: str = ""
    result_json: str = ""
    error: str = ""
    created_at: float = Field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    retry_count: int = 0
    max_retries: int = 3


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def record_task(
    task_id: str,
    task_type: str,
    tenant_id: str,
    payload: dict,
    *,
    max_retries: int = 3,
) -> TaskRecord:
    """Insert a new task record."""
    rec = TaskRecord(
        id=task_id,
        task_type=task_type,
        tenant_id=tenant_id,
        payload_json=json.dumps(payload),
        max_retries=max_retries,
    )
    with Session(engine) as session:
        session.add(rec)
        session.commit()
        session.refresh(rec)
    return rec


def update_task_status(
    task_id: str,
    status: str,
    *,
    result: Any = None,
    error: Optional[str] = None,
) -> None:
    """Update an existing task record's status and optional result/error."""
    with Session(engine) as session:
        rec = session.get(TaskRecord, task_id)
        if rec is None:
            return
        rec.status = status
        now = time.time()
        if status == "running":
            rec.started_at = now
        if status in ("completed", "failed", "dead_letter"):
            rec.completed_at = now
        if result is not None:
            rec.result_json = json.dumps(result)
        if error is not None:
            rec.error = error
        if status == "failed":
            rec.retry_count += 1
        session.add(rec)
        session.commit()


def get_pending_tasks(
    task_type: Optional[str] = None,
    limit: int = 50,
) -> list[TaskRecord]:
    """Return queued/failed tasks for rehydration on startup."""
    with Session(engine) as session:
        stmt = select(TaskRecord).where(
            TaskRecord.status.in_(["queued", "failed"])  # type: ignore[attr-defined]
        )
        if task_type is not None:
            stmt = stmt.where(TaskRecord.task_type == task_type)
        stmt = stmt.order_by(TaskRecord.created_at).limit(limit)
        return list(session.exec(stmt).all())
