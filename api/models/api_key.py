"""B9 — Developer API key model.

Responsibility: SQLModel table for long-lived API keys that developers use to
authenticate against the Maia API programmatically (CI/CD, SDK, GitHub Actions).

Each key is scoped to one or more permission scopes (e.g. "marketplace:publish")
and can be revoked at any time.  The raw key is only ever shown once at creation
time — only the SHA-256 hash is stored.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlmodel import Field, SQLModel


class ApiKey(SQLModel, table=True):
    """Developer API key record."""

    __tablename__ = "maia_api_key"
    __table_args__ = {"extend_existing": True}

    # ── Primary key ───────────────────────────────────────────────────────────

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True,
        index=True,
    )

    # ── Ownership ─────────────────────────────────────────────────────────────

    user_id: str = Field(index=True)
    tenant_id: Optional[str] = Field(default=None, index=True)

    # ── Key material ──────────────────────────────────────────────────────────

    # Human-readable label (e.g. "GitHub Actions – prod release")
    label: str = Field(default="")

    # SHA-256 hex digest of the raw key — never store plain text
    key_hash: str = Field(unique=True, index=True)

    # Key prefix shown in the UI to help users identify which key is which
    # e.g. "mk_abc123" (first 12 chars of the raw key, safe to display)
    key_prefix: str = Field(default="")

    # ── Permissions ───────────────────────────────────────────────────────────

    # Space-separated scopes: "marketplace:publish", "marketplace:read"
    scopes: str = Field(default="marketplace:publish marketplace:read")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    is_active: bool = Field(default=True, index=True)

    # Unix timestamp — None means never expires
    expires_at: Optional[float] = Field(default=None)

    # Tracking
    created_at: float = Field(default_factory=lambda: __import__("time").time())
    last_used_at: Optional[float] = Field(default=None)
