"""ConnectorBinding — links a connector to a tenant with scoped credentials.

Responsibility: SQLModel table definition for the connector binding entity.
A binding is the runtime contract between a connector definition (the
blueprint) and a specific tenant (the tenant-specific configuration + creds).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column
from sqlalchemy.types import JSON as SAJSON
from sqlmodel import Field, SQLModel


class ConnectorBinding(SQLModel, table=True):
    """Tenant-specific binding of a connector definition.

    Credentials stored here are encrypted by the credential vault service;
    this table holds only ciphertext — never plaintext secrets.
    """

    __tablename__ = "maia_connector_binding"
    __table_args__ = {"extend_existing": True}

    # ── Primary key ───────────────────────────────────────────────────────────

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True,
        index=True,
    )

    # ── Ownership ─────────────────────────────────────────────────────────────

    tenant_id: str = Field(index=True)
    connector_id: str = Field(index=True)  # References ConnectorDefinitionSchema.id

    # ── Display ───────────────────────────────────────────────────────────────

    # Human-readable label set by the tenant admin, e.g. "Production Salesforce".
    label: str = Field(default="")

    # ── Credentials (ciphertext) ──────────────────────────────────────────────

    # Fernet-encrypted JSON blob keyed by credential field name.
    # Never logged, never returned in API responses.
    encrypted_credentials: str = Field(default="")

    # OAuth2 access token (encrypted).
    encrypted_access_token: str = Field(default="")

    # OAuth2 refresh token (encrypted).
    encrypted_refresh_token: str = Field(default="")

    # UTC expiry for the access token; None if not applicable.
    token_expires_at: datetime | None = Field(default=None)

    # Auth strategy in use: "api_key" | "oauth2" | "basic" | "none"
    auth_strategy: str = Field(default="none", index=True)

    # ── Permissions ───────────────────────────────────────────────────────────

    # Agent definition IDs that are allowed to use this binding.
    # Empty list = all agents in the tenant may use it.
    allowed_agent_ids: list[str] = Field(
        default_factory=list,
        sa_column=Column(SAJSON),
    )

    # Subset of tool IDs from the connector that this binding exposes.
    # Empty list = all tools in the connector definition are available.
    enabled_tool_ids: list[str] = Field(
        default_factory=list,
        sa_column=Column(SAJSON),
    )

    # ── Runtime metadata ──────────────────────────────────────────────────────

    # Arbitrary metadata stored by the connector (e.g. connected account info).
    extra_metadata: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(SAJSON),
    )

    # ── Status ────────────────────────────────────────────────────────────────

    is_active: bool = Field(default=True, index=True)

    # ── Timestamps ────────────────────────────────────────────────────────────

    date_created: datetime = Field(default_factory=datetime.utcnow, index=True)
    date_updated: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: datetime | None = Field(default=None)
