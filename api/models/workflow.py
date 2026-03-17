"""WorkflowRecord — DB-backed workflow definition storage.

Replaces the JSON-file store (.maia_agent/workflows.json) with a proper
SQLModel table so definitions survive restarts and support multi-tenancy.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Column
from sqlalchemy.types import JSON as SAJSON
from sqlmodel import Field, SQLModel


class WorkflowRecord(SQLModel, table=True):
    """Persisted workflow definition."""

    __tablename__ = "maia_workflow"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    tenant_id: str = Field(index=True)
    name: str = Field(default="Untitled workflow")
    description: str = Field(default="")
    definition: dict[str, Any] = Field(default_factory=dict, sa_column=Column(SAJSON))
    version: str = Field(default="1.0.0")
    is_active: bool = Field(default=True, index=True)
    created_by: Optional[str] = Field(default=None, index=True)
    date_created: datetime = Field(default_factory=datetime.utcnow, index=True)
    date_updated: datetime = Field(default_factory=datetime.utcnow)
