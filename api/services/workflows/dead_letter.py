"""Dead-letter store for failed workflow steps.

Records steps that exhausted all retries so operators can inspect,
diagnose, and manually replay them later.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional, Sequence

from sqlalchemy import Column
from sqlalchemy.types import JSON as SAJSON
from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine


class DeadLetterEntry(SQLModel, table=True):
    """A workflow step that failed after all retry attempts."""

    __tablename__ = "maia_workflow_dead_letter"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    tenant_id: str = Field(index=True)
    run_id: str = Field(index=True)
    workflow_id: str = Field(index=True)
    step_id: str = Field(index=True)
    step_type: str = Field(default="agent")
    error: str = Field(default="")
    inputs: dict[str, Any] = Field(default_factory=dict, sa_column=Column(SAJSON))
    attempt: int = Field(default=1)
    date_created: datetime = Field(default_factory=datetime.utcnow, index=True)


def _ensure_tables() -> None:
    DeadLetterEntry.metadata.create_all(engine)


def record_dead_letter(
    tenant_id: str,
    run_id: str,
    workflow_id: str,
    step_id: str,
    error: str,
    inputs: dict[str, Any],
    attempt: int = 1,
    step_type: str = "agent",
) -> DeadLetterEntry:
    """Record a step that exhausted retries into the dead-letter table."""
    _ensure_tables()
    entry = DeadLetterEntry(
        tenant_id=tenant_id,
        run_id=run_id,
        workflow_id=workflow_id,
        step_id=step_id,
        step_type=step_type,
        error=str(error)[:2000],
        inputs={k: str(v)[:1000] for k, v in inputs.items()},
        attempt=attempt,
    )
    with Session(engine) as session:
        session.add(entry)
        session.commit()
        session.refresh(entry)
    return entry


def list_dead_letters(
    tenant_id: str,
    workflow_id: Optional[str] = None,
    limit: int = 100,
) -> Sequence[DeadLetterEntry]:
    """List dead-letter entries for a tenant, newest first."""
    _ensure_tables()
    with Session(engine) as session:
        q = select(DeadLetterEntry).where(DeadLetterEntry.tenant_id == tenant_id)
        if workflow_id:
            q = q.where(DeadLetterEntry.workflow_id == workflow_id)
        q = q.order_by(DeadLetterEntry.date_created.desc()).limit(limit)  # type: ignore[union-attr]
        return list(session.exec(q).all())
