"""FeedEvent model for creator and marketplace activity streams."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column
from sqlalchemy.types import JSON as SAJSON
from sqlmodel import Field, SQLModel


class FeedEvent(SQLModel, table=True):
    """Immutable activity event used by /api/feed and creator activity pages."""

    __tablename__ = "maia_feed_event"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True, index=True)
    creator_user_id: str = Field(index=True)
    actor_user_id: str = Field(index=True)
    event_type: str = Field(max_length=64, index=True)
    entity_type: str = Field(max_length=32, index=True)
    entity_id: str = Field(max_length=128, index=True)
    slug: str = Field(default="", max_length=128, index=True)
    title: str = Field(default="", max_length=160)
    summary: str = Field(default="", max_length=500)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(SAJSON))
    date_created: datetime = Field(default_factory=datetime.utcnow, index=True)
