"""Workflow CRUD service — DB-backed storage for workflow definitions.

Replaces the JSON-file _load_all / _save_all pattern in the router
with proper SQLModel persistence.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional, Sequence

from sqlmodel import Session, select

from ktem.db.engine import engine
from api.models.workflow import WorkflowRecord

logger = logging.getLogger(__name__)


def _ensure_tables() -> None:
    WorkflowRecord.metadata.create_all(engine)


def create_workflow(
    tenant_id: str,
    name: str,
    description: str,
    definition: dict[str, Any],
    created_by: Optional[str] = None,
) -> WorkflowRecord:
    """Create and persist a new workflow definition."""
    _ensure_tables()
    record = WorkflowRecord(
        tenant_id=tenant_id,
        name=name.strip() or "Untitled workflow",
        description=description,
        definition=definition,
        created_by=created_by or tenant_id,
    )
    with Session(engine) as session:
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


def get_workflow(workflow_id: str, tenant_id: str) -> WorkflowRecord | None:
    """Fetch a single workflow by ID, scoped to tenant."""
    _ensure_tables()
    with Session(engine) as session:
        record = session.get(WorkflowRecord, workflow_id)
        if record and record.tenant_id == tenant_id and record.is_active:
            return record
    return None


def list_workflows(tenant_id: str) -> Sequence[WorkflowRecord]:
    """List all active workflows for a tenant, newest first."""
    _ensure_tables()
    with Session(engine) as session:
        q = (
            select(WorkflowRecord)
            .where(WorkflowRecord.tenant_id == tenant_id)
            .where(WorkflowRecord.is_active == True)  # noqa: E712
            .order_by(WorkflowRecord.date_updated.desc())  # type: ignore[union-attr]
        )
        return list(session.exec(q).all())


def update_workflow(
    workflow_id: str,
    tenant_id: str,
    name: str,
    description: str,
    definition: dict[str, Any],
) -> WorkflowRecord | None:
    """Update an existing workflow. Returns None if not found."""
    _ensure_tables()
    with Session(engine) as session:
        record = session.get(WorkflowRecord, workflow_id)
        if not record or record.tenant_id != tenant_id or not record.is_active:
            return None
        record.name = name.strip() or record.name
        record.description = description
        record.definition = definition
        record.date_updated = datetime.utcnow()
        session.add(record)
        session.commit()
        session.refresh(record)
        return record


def delete_workflow(workflow_id: str, tenant_id: str) -> bool:
    """Soft-delete a workflow. Returns True if deleted, False if not found."""
    _ensure_tables()
    with Session(engine) as session:
        record = session.get(WorkflowRecord, workflow_id)
        if not record or record.tenant_id != tenant_id or not record.is_active:
            return False
        record.is_active = False
        record.date_updated = datetime.utcnow()
        session.add(record)
        session.commit()
        return True


def workflow_to_dict(record: WorkflowRecord) -> dict[str, Any]:
    """Serialize a WorkflowRecord to the dict format the frontend expects."""
    return {
        "id": record.id,
        "tenant_id": record.tenant_id,
        "name": record.name,
        "description": record.description,
        "definition": record.definition,
        "created_at": record.date_created.timestamp() if record.date_created else 0,
        "updated_at": record.date_updated.timestamp() if record.date_updated else 0,
    }
