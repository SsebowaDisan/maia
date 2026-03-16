"""User — authenticated platform user.

Roles
-----
super_admin  Maia platform staff.  Can approve/reject marketplace agents,
             manage any tenant, and access all platform operations.
org_admin    Company administrator. Can invite/remove users within their
             own tenant and change user roles up to org_admin.
org_user     Regular company user. No admin privileges.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from sqlmodel import Field, SQLModel

UserRole = Literal["super_admin", "org_admin", "org_user"]


class User(SQLModel, table=True):
    """Platform user record."""

    __tablename__ = "maia_user"
    __table_args__ = {"extend_existing": True}

    # ── Primary key ───────────────────────────────────────────────────────────

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True,
        index=True,
    )

    # ── Identity ──────────────────────────────────────────────────────────────

    email: str = Field(unique=True, index=True)
    full_name: str = Field(default="")

    # bcrypt hash — never store plain text
    hashed_password: str

    # ── Role & tenant ─────────────────────────────────────────────────────────

    # One of: "super_admin" | "org_admin" | "org_user"
    role: str = Field(default="org_user", index=True)

    # Foreign key to maia_tenant.id — null for super_admin (they span all tenants)
    tenant_id: str | None = Field(default=None, index=True)

    # ── Status ────────────────────────────────────────────────────────────────

    is_active: bool = Field(default=True, index=True)

    # ── Timestamps ────────────────────────────────────────────────────────────

    date_created: datetime = Field(default_factory=datetime.utcnow, index=True)
    date_updated: datetime = Field(default_factory=datetime.utcnow)
