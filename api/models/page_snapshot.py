"""PageSnapshotRecord — stores URL baseline snapshots for the Competitor Change Radar."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class PageSnapshotRecord(SQLModel, table=True):
    """Persisted page snapshot for change detection."""

    __tablename__ = "maia_page_snapshot"
    __table_args__ = {"extend_existing": True}

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True,
        index=True,
    )

    tenant_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    url: str = Field(index=True)

    # SHA-256 hex digest of the extracted text content
    content_hash: str = Field(default="")

    # Plain-text content of the page (truncated to ~64 KB)
    content_text: str = Field(default="")

    last_fetched_at: datetime = Field(default_factory=datetime.utcnow)

    # False once the user removes the URL from monitoring
    is_active: bool = Field(default=True, index=True)
