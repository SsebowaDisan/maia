"""PublishedWorkflow — a workflow/team published to the Agent Hub marketplace.

Responsibility: stores the public snapshot of a workflow that other users
can discover, preview, and install into their workspaces.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column
from sqlalchemy.types import JSON as SAJSON
from sqlmodel import Field, SQLModel

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,62}[a-z0-9]$")


def validate_slug(value: str) -> str:
    cleaned = str(value or "").strip().lower()
    if not _SLUG_RE.match(cleaned):
        raise ValueError("Slug must be 3-64 chars, lowercase alphanumeric with hyphens.")
    return cleaned


class PublishedWorkflow(SQLModel, table=True):
    """A workflow/team published to the marketplace."""

    __tablename__ = "maia_published_workflow"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True, index=True)
    slug: str = Field(index=True, unique=True, max_length=64)
    creator_id: str = Field(index=True)
    source_workflow_id: str = Field(default="", index=True)

    name: str = Field(max_length=120)
    description: str = Field(default="", max_length=500)
    readme_md: str = Field(default="")

    definition_snapshot: dict[str, Any] = Field(default_factory=dict, sa_column=Column(SAJSON))
    agent_lineup: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(SAJSON))
    required_connectors: list[str] = Field(default_factory=list, sa_column=Column(SAJSON))
    screenshots: list[str] = Field(default_factory=list, sa_column=Column(SAJSON))
    tags: list[str] = Field(default_factory=list, sa_column=Column(SAJSON))

    category: str = Field(default="other", max_length=40)
    version: str = Field(default="1.0.0", max_length=20)
    status: str = Field(default="published", max_length=20)

    install_count: int = Field(default=0)
    avg_rating: float = Field(default=0.0)
    review_count: int = Field(default=0)

    date_created: datetime = Field(default_factory=datetime.utcnow, index=True)
    date_updated: datetime = Field(default_factory=datetime.utcnow)
