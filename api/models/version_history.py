"""VersionRecord -- immutable version history for workflows and agents.

Every time a workflow or agent definition is published, promoted, or
rolled back, a new VersionRecord is created.  Records are never mutated
after creation (except the ``is_latest`` flag which is toggled when a
newer version supersedes this one).
"""
from __future__ import annotations

import uuid

from sqlmodel import Field, SQLModel


class VersionRecord(SQLModel, table=True):
    """Single immutable version snapshot."""

    __tablename__ = "maia_version_history"
    __table_args__ = {"extend_existing": True}

    # ── Primary key ───────────────────────────────────────────────────────────

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True,
    )

    # ── Resource identification ───────────────────────────────────────────────

    resource_type: str = Field(default="", index=True)   # "workflow" | "agent"
    resource_id: str = Field(default="", index=True)     # workflow_id or agent_id
    tenant_id: str = Field(default="", index=True)

    # ── Version info ──────────────────────────────────────────────────────────

    version: str = Field(default="1.0.0")                # semver string
    environment: str = Field(default="dev", index=True)  # "dev" | "staging" | "prod"

    # ── Frozen definition snapshot ────────────────────────────────────────────

    definition_json: str = Field(default="{}")

    # ── Metadata ──────────────────────────────────────────────────────────────

    created_by: str = Field(default="")
    created_at: float = Field(default=0.0, index=True)
    changelog: str = Field(default="")
    is_latest: bool = Field(default=False, index=True)
