"""MFA enrollment model — stores per-user TOTP secrets and backup codes."""
from __future__ import annotations

import uuid

from sqlmodel import Field, SQLModel


class MfaEnrollment(SQLModel, table=True):
    """Tracks MFA (TOTP) enrolment for a single user."""

    __tablename__ = "maia_mfa_enrollment"
    __table_args__ = {"extend_existing": True}

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True,
    )
    user_id: str = Field(index=True, unique=True)
    totp_secret_encrypted: str  # Fernet-encrypted TOTP secret
    is_active: bool = Field(default=False)
    backup_codes_json: str = Field(default="[]")  # encrypted JSON list
    created_at: float
    last_used_at: float | None = Field(default=None)
