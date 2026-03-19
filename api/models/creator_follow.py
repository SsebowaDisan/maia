"""CreatorFollow — tracks who follows which creator."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel


class CreatorFollow(SQLModel, table=True):
    """A follow relationship between a user and a creator."""

    __tablename__ = "maia_creator_follow"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    follower_user_id: str = Field(index=True)
    creator_user_id: str = Field(index=True)
    date_created: datetime = Field(default_factory=datetime.utcnow)
