"""Custom role model — tenant-scoped RBAC roles with fine-grained scopes."""
from __future__ import annotations

import uuid

from sqlmodel import Field, SQLModel


class CustomRole(SQLModel, table=True):
    """A tenant-scoped custom role with an explicit list of scope strings."""

    __tablename__ = "maia_custom_role"
    __table_args__ = {"extend_existing": True}

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True,
    )
    tenant_id: str = Field(index=True)
    name: str  # e.g. "workflow_developer", "credential_manager"
    description: str = Field(default="")
    scopes_json: str = Field(default="[]")  # JSON list of scope strings
    created_by: str
    created_at: float
    updated_at: float
