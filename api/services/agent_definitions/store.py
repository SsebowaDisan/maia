"""AgentDefinitionStore — CRUD operations for agent definitions.

Responsibility: all database reads and writes for maia_agent_definition.
All validation of the AgentDefinitionSchema happens here before persistence.
"""
from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlmodel import Session, select

from api.models.agent_definition import AgentDefinitionRecord
from api.schemas.agent_definition import AgentDefinitionSchema
from ktem.db.engine import engine


def _ensure_tables() -> None:
    from sqlmodel import SQLModel

    SQLModel.metadata.create_all(engine)


# ── Read ──────────────────────────────────────────────────────────────────────


def get_definition(record_id: str) -> AgentDefinitionRecord | None:
    """Return a record by primary-key id."""
    with Session(engine) as session:
        return session.get(AgentDefinitionRecord, record_id)


def get_definition_by_agent_id(
    tenant_id: str, agent_id: str
) -> AgentDefinitionRecord | None:
    """Return the active definition for (tenant_id, agent_id), or None."""
    with Session(engine) as session:
        return session.exec(
            select(AgentDefinitionRecord)
            .where(AgentDefinitionRecord.tenant_id == tenant_id)
            .where(AgentDefinitionRecord.agent_id == agent_id)
            .where(AgentDefinitionRecord.is_active == True)  # noqa: E712
        ).first()


def list_definitions(
    tenant_id: str, *, active_only: bool = True
) -> Sequence[AgentDefinitionRecord]:
    """List all agent definitions for a tenant."""
    with Session(engine) as session:
        query = select(AgentDefinitionRecord).where(
            AgentDefinitionRecord.tenant_id == tenant_id
        )
        if active_only:
            query = query.where(AgentDefinitionRecord.is_active == True)  # noqa: E712
        return session.exec(query.order_by(AgentDefinitionRecord.date_created)).all()


def list_public_definitions() -> Sequence[AgentDefinitionRecord]:
    """Return all public definitions (marketplace catalog)."""
    with Session(engine) as session:
        return session.exec(
            select(AgentDefinitionRecord)
            .where(AgentDefinitionRecord.is_public == True)  # noqa: E712
            .where(AgentDefinitionRecord.is_active == True)  # noqa: E712
            .order_by(AgentDefinitionRecord.date_created)
        ).all()


# ── Write ─────────────────────────────────────────────────────────────────────


def create_definition(
    tenant_id: str,
    user_id: str,
    schema: AgentDefinitionSchema,
) -> AgentDefinitionRecord:
    """Validate and persist a new agent definition."""
    _ensure_tables()

    with Session(engine) as session:
        existing = session.exec(
            select(AgentDefinitionRecord)
            .where(AgentDefinitionRecord.tenant_id == tenant_id)
            .where(AgentDefinitionRecord.agent_id == schema.id)
            .where(AgentDefinitionRecord.is_active == True)  # noqa: E712
        ).first()
        if existing:
            raise ValueError(
                f"An active agent with id '{schema.id}' already exists in this tenant."
            )

        now = datetime.utcnow()
        record = AgentDefinitionRecord(
            tenant_id=tenant_id,
            created_by_user_id=user_id,
            agent_id=schema.id,
            name=schema.name,
            definition=schema.model_dump(mode="python"),
            version=schema.version,
            is_public=schema.is_public,
            date_created=now,
            date_updated=now,
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        return record


def update_definition(
    record_id: str,
    user_id: str,
    schema: AgentDefinitionSchema,
) -> AgentDefinitionRecord:
    """Replace the definition payload for an existing record."""
    with Session(engine) as session:
        record = session.get(AgentDefinitionRecord, record_id)
        if not record:
            raise ValueError(f"Agent definition record '{record_id}' not found.")

        record.name = schema.name
        record.definition = schema.model_dump(mode="python")
        record.version = schema.version
        record.is_public = schema.is_public
        record.date_updated = datetime.utcnow()

        session.add(record)
        session.commit()
        session.refresh(record)
        return record


def deactivate_definition(record_id: str) -> AgentDefinitionRecord:
    """Soft-delete a definition by setting is_active=False."""
    with Session(engine) as session:
        record = session.get(AgentDefinitionRecord, record_id)
        if not record:
            raise ValueError(f"Agent definition record '{record_id}' not found.")
        record.is_active = False
        record.date_updated = datetime.utcnow()
        session.add(record)
        session.commit()
        session.refresh(record)
        return record


def load_schema(record: AgentDefinitionRecord) -> AgentDefinitionSchema:
    """Deserialise the stored JSON blob back into a validated schema object."""
    return AgentDefinitionSchema.model_validate(record.definition)
