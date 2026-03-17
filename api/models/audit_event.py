"""AuditEvent -- immutable audit trail record for the Maia platform.

Every security-relevant action (login, agent run, admin role change, etc.)
is persisted here so that org admins can review activity and export logs
to external SIEM systems.
"""
from __future__ import annotations

import uuid
from typing import Literal

from sqlmodel import Field, SQLModel

ActorType = Literal["user", "agent", "system", "api_key"]


class AuditEvent(SQLModel, table=True):
    """Single audit trail entry."""

    __tablename__ = "maia_audit_event"
    __table_args__ = {"extend_existing": True}

    # ── Primary key ───────────────────────────────────────────────────────────

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True,
    )

    # ── Temporal ──────────────────────────────────────────────────────────────

    timestamp: float = Field(default=0.0, index=True)

    # ── Identity / tenancy ────────────────────────────────────────────────────

    tenant_id: str = Field(default="", index=True)
    user_id: str = Field(default="", index=True)
    actor_type: str = Field(default="user")  # ActorType

    # ── Action / resource ─────────────────────────────────────────────────────

    action: str = Field(default="", index=True)  # e.g. "auth.login"
    resource_type: str = Field(default="")       # e.g. "workflow"
    resource_id: str = Field(default="")

    # ── Context ───────────────────────────────────────────────────────────────

    detail: str = Field(default="", max_length=1000)
    ip_address: str = Field(default="")
    metadata_json: str = Field(default="{}")  # JSON string for extra data
