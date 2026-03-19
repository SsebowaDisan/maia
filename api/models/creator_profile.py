"""CreatorProfile — public profile for agent/team publishers.

Responsibility: stores the public-facing identity of a creator on
the Maia Agent Hub. Linked 1:1 to a User record via user_id.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel

_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,28}[a-z0-9]$")


def validate_username(value: str) -> str:
    cleaned = str(value or "").strip().lower()
    if not _USERNAME_RE.match(cleaned):
        raise ValueError(
            "Username must be 3-30 chars, lowercase alphanumeric with hyphens, "
            "start/end with alphanumeric."
        )
    return cleaned


class CreatorProfile(SQLModel, table=True):
    """Public creator profile for the Agent Hub."""

    __tablename__ = "maia_creator_profile"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True, index=True)
    user_id: str = Field(index=True, unique=True)
    username: str = Field(index=True, unique=True, max_length=30)

    display_name: str = Field(default="", max_length=80)
    bio: str = Field(default="", max_length=300)
    avatar_url: str = Field(default="", max_length=500)
    website_url: str = Field(default="", max_length=300)
    github_url: str = Field(default="", max_length=300)
    twitter_url: str = Field(default="", max_length=300)

    follower_count: int = Field(default=0)
    total_installs: int = Field(default=0)
    published_agent_count: int = Field(default=0)
    published_team_count: int = Field(default=0)

    date_created: datetime = Field(default_factory=datetime.utcnow, index=True)
    date_updated: datetime = Field(default_factory=datetime.utcnow)
