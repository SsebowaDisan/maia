"""P5-02 — Insight store.

Responsibility: persist proactive insights per tenant with read/unread state,
severity level, and source reference.
"""
from __future__ import annotations

import uuid
import time
from typing import Any, Optional, Sequence

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine


class InsightRecord(SQLModel, table=True):
    __tablename__ = "maia_insight"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(index=True)
    signal_type: str = ""          # e.g. "threshold_breach", "data_spike"
    severity: str = "info"         # "info" | "warning" | "critical"
    title: str = ""
    summary: str = ""
    source_ref: str = ""           # connector_id or agent_id that triggered it
    payload_json: str = "{}"
    is_read: bool = False
    created_at: float = Field(default_factory=time.time)


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


# ── Public API ─────────────────────────────────────────────────────────────────

def save_insight(
    tenant_id: str,
    *,
    signal_type: str = "",
    severity: str = "info",
    title: str,
    summary: str = "",
    source_ref: str = "",
    payload: dict[str, Any] | None = None,
) -> InsightRecord:
    _ensure_tables()
    import json
    record = InsightRecord(
        tenant_id=tenant_id,
        signal_type=signal_type,
        severity=severity,
        title=title,
        summary=summary,
        source_ref=source_ref,
        payload_json=json.dumps(payload or {}),
    )
    with Session(engine) as session:
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


def list_insights(
    tenant_id: str,
    *,
    limit: int = 50,
    unread_only: bool = False,
) -> Sequence[InsightRecord]:
    _ensure_tables()
    with Session(engine) as session:
        q = select(InsightRecord).where(InsightRecord.tenant_id == tenant_id)
        if unread_only:
            q = q.where(InsightRecord.is_read == False)  # noqa: E712
        q = q.order_by(InsightRecord.created_at.desc()).limit(limit)  # type: ignore[arg-type]
        return session.exec(q).all()


def unread_count(tenant_id: str) -> int:
    _ensure_tables()
    with Session(engine) as session:
        rows = session.exec(
            select(InsightRecord)
            .where(InsightRecord.tenant_id == tenant_id)
            .where(InsightRecord.is_read == False)  # noqa: E712
        ).all()
        return len(rows)


def mark_read(tenant_id: str, insight_id: str) -> bool:
    _ensure_tables()
    with Session(engine) as session:
        record = session.get(InsightRecord, insight_id)
        if not record or record.tenant_id != tenant_id:
            return False
        record.is_read = True
        session.add(record)
        session.commit()
    return True


def mark_all_read(tenant_id: str) -> int:
    _ensure_tables()
    with Session(engine) as session:
        rows = session.exec(
            select(InsightRecord)
            .where(InsightRecord.tenant_id == tenant_id)
            .where(InsightRecord.is_read == False)  # noqa: E712
        ).all()
        for row in rows:
            row.is_read = True
            session.add(row)
        session.commit()
        return len(rows)


def delete_insight(tenant_id: str, insight_id: str) -> bool:
    _ensure_tables()
    with Session(engine) as session:
        record = session.get(InsightRecord, insight_id)
        if not record or record.tenant_id != tenant_id:
            return False
        session.delete(record)
        session.commit()
    return True


def insight_to_dict(record: InsightRecord) -> dict[str, Any]:
    import json
    return {
        "id": record.id,
        "tenant_id": record.tenant_id,
        "signal_type": record.signal_type,
        "severity": record.severity,
        "title": record.title,
        "summary": record.summary,
        "source_ref": record.source_ref,
        "payload": json.loads(record.payload_json or "{}"),
        "is_read": record.is_read,
        "created_at": record.created_at,
    }
