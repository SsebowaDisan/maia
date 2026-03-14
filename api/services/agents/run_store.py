"""Agent run store — persists run state for gate resume and history.

Responsibility: lightweight SQLModel table to track the lifecycle of an
agent run: created, running, completed, failed, cancelled.
"""
from __future__ import annotations

import time
import uuid
from typing import Literal, Optional, Sequence

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine

RunStatus = Literal["running", "completed", "failed", "cancelled"]


class AgentRunRecord(SQLModel, table=True):
    __tablename__ = "maia_agent_run"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    conversation_id: Optional[str] = None
    trigger_type: str = "manual"  # manual | scheduled | event
    status: RunStatus = "running"
    started_at: float = Field(default_factory=time.time)
    ended_at: Optional[float] = None
    error: Optional[str] = None
    result_summary: Optional[str] = None


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


def create_run(
    tenant_id: str,
    agent_id: str,
    *,
    conversation_id: str | None = None,
    trigger_type: str = "manual",
) -> AgentRunRecord:
    _ensure_tables()
    record = AgentRunRecord(
        tenant_id=tenant_id,
        agent_id=agent_id,
        conversation_id=conversation_id,
        trigger_type=trigger_type,
    )
    with Session(engine) as session:
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


def complete_run(run_id: str, *, result_summary: str | None = None) -> None:
    _update_run(run_id, status="completed", result_summary=result_summary)


def fail_run(run_id: str, *, error: str | None = None) -> None:
    _update_run(run_id, status="failed", error=error)


def cancel_run(run_id: str) -> None:
    _update_run(run_id, status="cancelled")


def get_run(run_id: str) -> AgentRunRecord | None:
    with Session(engine) as session:
        return session.get(AgentRunRecord, run_id)


def list_runs(
    tenant_id: str,
    agent_id: str | None = None,
    *,
    limit: int = 50,
) -> Sequence[AgentRunRecord]:
    with Session(engine) as session:
        q = select(AgentRunRecord).where(AgentRunRecord.tenant_id == tenant_id)
        if agent_id:
            q = q.where(AgentRunRecord.agent_id == agent_id)
        q = q.order_by(AgentRunRecord.started_at.desc()).limit(limit)  # type: ignore[attr-defined]
        return session.exec(q).all()


def _update_run(run_id: str, **fields) -> None:
    with Session(engine) as session:
        record = session.get(AgentRunRecord, run_id)
        if record:
            for k, v in fields.items():
                setattr(record, k, v)
            record.ended_at = time.time()
            session.add(record)
            session.commit()
