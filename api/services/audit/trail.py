"""Persistent audit trail service.

Provides insert, query, count, and NDJSON export for the ``maia_audit_event``
table.  All public functions open their own Session so callers don't need to
manage DB lifecycle.
"""
from __future__ import annotations

import json
import time
from typing import Any, Generator

from sqlmodel import Session, col, func, select

from api.models.audit_event import AuditEvent
from ktem.db.engine import engine

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_tables_ready = False


def _ensure_tables() -> None:
    """Create the audit table if it doesn't exist yet (idempotent)."""
    global _tables_ready
    if _tables_ready:
        return
    from sqlmodel import SQLModel

    SQLModel.metadata.create_all(engine, tables=[AuditEvent.__table__])
    _tables_ready = True


def _base_filter(
    stmt,
    tenant_id: str,
    *,
    action: str | None = None,
    user_id: str | None = None,
    resource_type: str | None = None,
    since: float | None = None,
    until: float | None = None,
):
    """Apply common WHERE clauses and return the modified statement."""
    stmt = stmt.where(AuditEvent.tenant_id == tenant_id)
    if action is not None:
        stmt = stmt.where(AuditEvent.action == action)
    if user_id is not None:
        stmt = stmt.where(AuditEvent.user_id == user_id)
    if resource_type is not None:
        stmt = stmt.where(AuditEvent.resource_type == resource_type)
    if since is not None:
        stmt = stmt.where(col(AuditEvent.timestamp) >= since)
    if until is not None:
        stmt = stmt.where(col(AuditEvent.timestamp) <= until)
    return stmt


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def record_event(
    tenant_id: str,
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    *,
    actor_type: str = "user",
    detail: str = "",
    ip_address: str = "",
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    """Insert a new audit event and return it."""
    _ensure_tables()
    event = AuditEvent(
        timestamp=time.time(),
        tenant_id=tenant_id,
        user_id=user_id,
        actor_type=actor_type,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail[:1000],
        ip_address=ip_address,
        metadata_json=json.dumps(metadata or {}),
    )
    with Session(engine) as session:
        session.add(event)
        session.commit()
        session.refresh(event)
    return event


def query_events(
    tenant_id: str,
    *,
    action: str | None = None,
    user_id: str | None = None,
    resource_type: str | None = None,
    since: float | None = None,
    until: float | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditEvent]:
    """Return filtered, paginated audit events (newest first)."""
    _ensure_tables()
    stmt = select(AuditEvent)
    stmt = _base_filter(
        stmt, tenant_id,
        action=action, user_id=user_id, resource_type=resource_type,
        since=since, until=until,
    )
    stmt = stmt.order_by(col(AuditEvent.timestamp).desc()).offset(offset).limit(limit)
    with Session(engine) as session:
        return list(session.exec(stmt).all())


def count_events(
    tenant_id: str,
    *,
    action: str | None = None,
    user_id: str | None = None,
    resource_type: str | None = None,
    since: float | None = None,
    until: float | None = None,
) -> int:
    """Count matching audit events."""
    _ensure_tables()
    stmt = select(func.count()).select_from(AuditEvent)
    stmt = _base_filter(
        stmt, tenant_id,
        action=action, user_id=user_id, resource_type=resource_type,
        since=since, until=until,
    )
    with Session(engine) as session:
        return session.exec(stmt).one()


def export_events_ndjson(
    tenant_id: str,
    *,
    since: float | None = None,
    until: float | None = None,
) -> Generator[str, None, None]:
    """Yield newline-delimited JSON strings for SIEM export."""
    _ensure_tables()
    stmt = select(AuditEvent)
    stmt = _base_filter(stmt, tenant_id, since=since, until=until)
    stmt = stmt.order_by(col(AuditEvent.timestamp).asc())
    with Session(engine) as session:
        results = session.exec(stmt).all()
        for event in results:
            row = {
                "id": event.id,
                "timestamp": event.timestamp,
                "tenant_id": event.tenant_id,
                "user_id": event.user_id,
                "actor_type": event.actor_type,
                "action": event.action,
                "resource_type": event.resource_type,
                "resource_id": event.resource_id,
                "detail": event.detail,
                "ip_address": event.ip_address,
                "metadata": json.loads(event.metadata_json),
            }
            yield json.dumps(row, separators=(",", ":")) + "\n"
