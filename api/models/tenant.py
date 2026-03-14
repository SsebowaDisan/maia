"""Tenant — one isolated workspace on the Maia platform.

Responsibility: SQLModel table definition for the tenant entity.
A tenant maps 1:1 to an organisation. Each user belongs to exactly one tenant.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column
from sqlalchemy.types import JSON as SAJSON
from sqlmodel import Field, SQLModel


class Tenant(SQLModel, table=True):
    """Platform tenant (organisation-level workspace)."""

    __tablename__ = "maia_tenant"
    __table_args__ = {"extend_existing": True}

    # ── Primary key ───────────────────────────────────────────────────────────

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True,
        index=True,
    )

    # ── Identity ──────────────────────────────────────────────────────────────

    name: str = Field(index=True)

    # Slug used in URLs, e.g. "acme-corp".
    slug: str = Field(unique=True, index=True)

    # ── Membership ────────────────────────────────────────────────────────────

    # User ID of the tenant owner — corresponds to the ktem user system.
    owner_user_id: str = Field(index=True)

    # Denormalised list of all member user IDs for fast access-control checks.
    member_user_ids: list[str] = Field(
        default_factory=list,
        sa_column=Column(SAJSON),
    )

    # ── Plan / billing ────────────────────────────────────────────────────────

    # "free" | "starter" | "pro" | "enterprise"
    plan: str = Field(default="free", index=True)

    # ISO 4217 currency code, e.g. "USD".
    billing_currency: str = Field(default="USD")

    # ── Feature flags ─────────────────────────────────────────────────────────

    # Arbitrary JSON key/value pairs for per-tenant feature flags.
    feature_flags: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(SAJSON),
    )

    # ── Limits ────────────────────────────────────────────────────────────────

    # Maximum number of active agent definitions for this tenant.
    max_agents: int = Field(default=10)

    # Maximum number of connector bindings.
    max_connectors: int = Field(default=5)

    # ── Status ────────────────────────────────────────────────────────────────

    is_active: bool = Field(default=True, index=True)

    # ── Timestamps ────────────────────────────────────────────────────────────

    date_created: datetime = Field(default_factory=datetime.utcnow, index=True)
    date_updated: datetime = Field(default_factory=datetime.utcnow)
