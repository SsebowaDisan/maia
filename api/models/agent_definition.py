"""AgentDefinitionRecord — persisted agent definition for a tenant.

Responsibility: SQLModel table definition for stored agent definitions.
The full schema (gates, memory, triggers, etc.) is stored as a JSON blob.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column
from sqlalchemy.types import JSON as SAJSON
from sqlmodel import Field, SQLModel


class AgentDefinitionRecord(SQLModel, table=True):
    """Persisted agent definition belonging to a tenant."""

    __tablename__ = "maia_agent_definition"
    __table_args__ = {"extend_existing": True}

    # ── Primary key ───────────────────────────────────────────────────────────

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True,
        index=True,
    )

    # ── Ownership ─────────────────────────────────────────────────────────────

    tenant_id: str = Field(index=True)

    # User who created or last edited this definition.
    created_by_user_id: str = Field(index=True)

    # ── Definition snapshot ───────────────────────────────────────────────────

    # Slug from AgentDefinitionSchema.id (unique within the tenant).
    agent_id: str = Field(index=True)

    # Human-readable name (denormalised from the schema for fast list queries).
    name: str = Field(index=True)

    # Full AgentDefinitionSchema serialised to JSON.
    definition: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(SAJSON),
    )

    # Semantic version string.
    version: str = Field(default="1.0.0")

    # ── Marketplace ───────────────────────────────────────────────────────────

    # True when this definition is listed in the public marketplace.
    is_public: bool = Field(default=False, index=True)

    # ── Status ────────────────────────────────────────────────────────────────

    is_active: bool = Field(default=True, index=True)

    # ── Timestamps ────────────────────────────────────────────────────────────

    date_created: datetime = Field(default_factory=datetime.utcnow, index=True)
    date_updated: datetime = Field(default_factory=datetime.utcnow)
