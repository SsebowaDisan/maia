"""DeveloperProfile — tracks developer tier and application status.

Statuses
--------
none             User has not applied for developer access.
pending          Application submitted, awaiting admin review.
verified         Approved developer — can publish agents (enters review queue).
trusted_publisher  Trusted developer — agents auto-approved on submit.
rejected         Application was rejected (can re-apply with new motivation).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from sqlmodel import Field, SQLModel

DeveloperStatus = Literal[
    "none", "pending", "verified", "trusted_publisher", "rejected"
]


class DeveloperProfile(SQLModel, table=True):
    """Developer access profile linked to a user."""

    __tablename__ = "maia_developer_profile"
    __table_args__ = {"extend_existing": True}

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True,
    )
    user_id: str = Field(index=True, unique=True)
    tenant_id: str | None = Field(default=None, index=True)

    status: str = Field(default="none", index=True)

    # Application fields
    motivation: str = Field(default="")
    intended_agent_types: str = Field(default="")
    agreed_to_guidelines: bool = Field(default=False)

    # Admin review
    reviewed_by: str | None = Field(default=None)
    rejection_reason: str | None = Field(default=None)

    date_created: datetime = Field(default_factory=datetime.utcnow, index=True)
    date_updated: datetime = Field(default_factory=datetime.utcnow)
