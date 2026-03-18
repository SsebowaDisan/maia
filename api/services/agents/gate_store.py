"""Durable persistence layer for HITL gate state.

Backs the in-memory gate engine (``gate_engine.py``) with a SQLModel table so
that pending gates survive process restarts and provide a full audit trail.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Optional

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine

logger = logging.getLogger(__name__)


# ── SQLModel table ────────────────────────────────────────────────────────────

class GateRecord(SQLModel, table=True):
    """Persistent record of a single HITL gate checkpoint."""

    __tablename__ = "maia_gate_record"
    __table_args__ = {"extend_existing": True}

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True,
    )
    run_id: str = Field(default="", index=True)
    gate_id: str = Field(default="")
    tenant_id: str = Field(default="", index=True)
    agent_id: str = Field(default="")
    gate_type: str = Field(default="tool_approval")
    description: str = Field(default="")
    status: str = Field(default="pending", index=True)  # pending|approved|rejected|expired
    requested_at: float = Field(default_factory=time.time)
    decided_at: Optional[float] = Field(default=None)
    decided_by: Optional[str] = Field(default=None)
    timeout_seconds: float = Field(default=300.0)
    fallback_action: str = Field(default="abort")  # abort|skip|auto_approve
    metadata_json: str = Field(default="{}")


# ── Ensure table exists ──────────────────────────────────────────────────────

def _ensure_table() -> None:
    """Create the gate_record table if it does not exist yet."""
    SQLModel.metadata.create_all(engine, tables=[GateRecord.__table__])


_ensure_table()


# ── Public helpers ────────────────────────────────────────────────────────────

def record_gate(
    run_id: str,
    gate_id: str,
    tenant_id: str,
    *,
    agent_id: str = "",
    gate_type: str = "tool_approval",
    description: str = "",
    timeout_seconds: float = 300.0,
    fallback_action: str = "abort",
    metadata: dict[str, Any] | None = None,
) -> GateRecord:
    """Persist a newly-created pending gate and return the record."""
    rec = GateRecord(
        id=gate_id,
        run_id=run_id,
        gate_id=gate_id,
        tenant_id=tenant_id,
        agent_id=agent_id,
        gate_type=gate_type,
        description=description,
        status="pending",
        requested_at=time.time(),
        timeout_seconds=timeout_seconds,
        fallback_action=fallback_action,
        metadata_json=json.dumps(metadata or {}, default=str),
    )
    with Session(engine) as session:
        session.add(rec)
        session.commit()
        session.refresh(rec)
    logger.debug("Persisted pending gate %s for run %s", gate_id, run_id)
    return rec


def decide_gate(
    run_id: str,
    gate_id: str,
    decision: str,
    decided_by: str,
) -> GateRecord | None:
    """Record an approve/reject decision.  Returns the updated record or None."""
    with Session(engine) as session:
        stmt = select(GateRecord).where(
            GateRecord.run_id == run_id,
            GateRecord.gate_id == gate_id,
            GateRecord.status == "pending",
        )
        rec = session.exec(stmt).first()
        if rec is None:
            return None
        rec.status = "approved" if decision == "approve" else "rejected"
        rec.decided_at = time.time()
        rec.decided_by = decided_by
        session.add(rec)
        session.commit()
        session.refresh(rec)
    logger.debug("Gate %s decided=%s by=%s", gate_id, rec.status, decided_by)
    return rec


def get_pending_gates(
    run_id: str | None = None,
    tenant_id: str | None = None,
) -> list[GateRecord]:
    """Return all pending gates, optionally filtered by run or tenant."""
    with Session(engine) as session:
        stmt = select(GateRecord).where(GateRecord.status == "pending")
        if run_id is not None:
            stmt = stmt.where(GateRecord.run_id == run_id)
        if tenant_id is not None:
            stmt = stmt.where(GateRecord.tenant_id == tenant_id)
        return list(session.exec(stmt).all())


def get_gate(run_id: str, gate_id: str) -> GateRecord | None:
    """Fetch a single gate record."""
    with Session(engine) as session:
        stmt = select(GateRecord).where(
            GateRecord.run_id == run_id,
            GateRecord.gate_id == gate_id,
        )
        return session.exec(stmt).first()


def expire_stale_gates() -> int:
    """Mark pending gates whose timeout has elapsed as expired.  Returns count."""
    now = time.time()
    count = 0
    with Session(engine) as session:
        stmt = select(GateRecord).where(GateRecord.status == "pending")
        for rec in session.exec(stmt).all():
            if now - rec.requested_at > rec.timeout_seconds:
                rec.status = "expired"
                rec.decided_at = now
                session.add(rec)
                count += 1
        if count:
            session.commit()
    logger.info("Expired %d stale gates", count)
    return count


def get_gate_history(run_id: str) -> list[GateRecord]:
    """Return all gates for a run (any status), ordered by requested_at."""
    with Session(engine) as session:
        stmt = (
            select(GateRecord)
            .where(GateRecord.run_id == run_id)
            .order_by(GateRecord.requested_at)  # type: ignore[arg-type]
        )
        return list(session.exec(stmt).all())


def cleanup_old_gates(max_age_days: int = 30) -> int:
    """Delete gate records older than *max_age_days*.  Returns count deleted."""
    cutoff = time.time() - (max_age_days * 86400)
    count = 0
    with Session(engine) as session:
        stmt = select(GateRecord).where(GateRecord.requested_at < cutoff)
        for rec in session.exec(stmt).all():
            session.delete(rec)
            count += 1
        if count:
            session.commit()
    logger.info("Cleaned up %d old gate records (older than %d days)", count, max_age_days)
    return count
