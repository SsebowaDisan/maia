"""Developer access service — application, approval, and status management."""
from __future__ import annotations

import logging
from datetime import datetime

from sqlmodel import Session, select

from ktem.db.engine import engine
from api.models.developer import DeveloperProfile

logger = logging.getLogger(__name__)


def _ensure_table() -> None:
    DeveloperProfile.metadata.create_all(engine)


class DeveloperError(Exception):
    def __init__(self, message: str, code: str = "developer_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def get_developer_profile(user_id: str) -> DeveloperProfile | None:
    """Fetch a developer profile by user_id, or None if not applied."""
    _ensure_table()
    with Session(engine) as session:
        statement = select(DeveloperProfile).where(
            DeveloperProfile.user_id == user_id
        )
        return session.exec(statement).first()


def get_developer_status(user_id: str) -> str:
    """Return the developer status string for a user (defaults to 'none')."""
    profile = get_developer_profile(user_id)
    return profile.status if profile else "none"


def apply_for_developer(
    user_id: str,
    tenant_id: str | None,
    motivation: str,
    intended_agent_types: str,
    agreed_to_guidelines: bool,
) -> DeveloperProfile:
    """Submit a developer application. Idempotent — re-applies if rejected."""
    _ensure_table()
    if not motivation.strip():
        raise DeveloperError("Motivation is required.", code="missing_motivation")
    if not agreed_to_guidelines:
        raise DeveloperError(
            "You must agree to the developer guidelines.",
            code="guidelines_not_accepted",
        )

    with Session(engine) as session:
        existing = session.exec(
            select(DeveloperProfile).where(
                DeveloperProfile.user_id == user_id
            )
        ).first()

        if existing:
            if existing.status in ("verified", "trusted_publisher"):
                raise DeveloperError(
                    "You are already a verified developer.",
                    code="already_verified",
                )
            if existing.status == "pending":
                raise DeveloperError(
                    "Your application is already pending review.",
                    code="already_pending",
                )
            # Re-apply after rejection
            existing.motivation = motivation.strip()
            existing.intended_agent_types = intended_agent_types.strip()
            existing.agreed_to_guidelines = True
            existing.status = "pending"
            existing.rejection_reason = None
            existing.reviewed_by = None
            existing.date_updated = datetime.utcnow()
            session.add(existing)
            session.commit()
            session.refresh(existing)
            return existing

        profile = DeveloperProfile(
            user_id=user_id,
            tenant_id=tenant_id,
            status="pending",
            motivation=motivation.strip(),
            intended_agent_types=intended_agent_types.strip(),
            agreed_to_guidelines=True,
        )
        session.add(profile)
        session.commit()
        session.refresh(profile)
        return profile


def approve_developer(user_id: str, reviewed_by: str) -> DeveloperProfile:
    """Approve a pending developer application."""
    _ensure_table()
    with Session(engine) as session:
        profile = session.exec(
            select(DeveloperProfile).where(
                DeveloperProfile.user_id == user_id
            )
        ).first()
        if not profile:
            raise DeveloperError("Developer profile not found.", code="not_found")
        if profile.status not in ("pending",):
            raise DeveloperError(
                f"Cannot approve profile with status '{profile.status}'.",
                code="invalid_status",
            )
        profile.status = "verified"
        profile.reviewed_by = reviewed_by
        profile.rejection_reason = None
        profile.date_updated = datetime.utcnow()
        session.add(profile)
        session.commit()
        session.refresh(profile)
        return profile


def reject_developer(
    user_id: str, reviewed_by: str, reason: str
) -> DeveloperProfile:
    """Reject a pending developer application with a reason."""
    _ensure_table()
    if not reason.strip():
        raise DeveloperError("Rejection reason is required.", code="missing_reason")
    with Session(engine) as session:
        profile = session.exec(
            select(DeveloperProfile).where(
                DeveloperProfile.user_id == user_id
            )
        ).first()
        if not profile:
            raise DeveloperError("Developer profile not found.", code="not_found")
        if profile.status != "pending":
            raise DeveloperError(
                f"Cannot reject profile with status '{profile.status}'.",
                code="invalid_status",
            )
        profile.status = "rejected"
        profile.reviewed_by = reviewed_by
        profile.rejection_reason = reason.strip()
        profile.date_updated = datetime.utcnow()
        session.add(profile)
        session.commit()
        session.refresh(profile)
        return profile


def promote_to_trusted(user_id: str, promoted_by: str) -> DeveloperProfile:
    """Promote a verified developer to trusted_publisher."""
    _ensure_table()
    with Session(engine) as session:
        profile = session.exec(
            select(DeveloperProfile).where(
                DeveloperProfile.user_id == user_id
            )
        ).first()
        if not profile:
            raise DeveloperError("Developer profile not found.", code="not_found")
        if profile.status != "verified":
            raise DeveloperError(
                "Only verified developers can be promoted.",
                code="invalid_status",
            )
        profile.status = "trusted_publisher"
        profile.reviewed_by = promoted_by
        profile.date_updated = datetime.utcnow()
        session.add(profile)
        session.commit()
        session.refresh(profile)
        return profile


def list_pending_applications() -> list[DeveloperProfile]:
    """List all pending developer applications for admin review."""
    _ensure_table()
    with Session(engine) as session:
        statement = (
            select(DeveloperProfile)
            .where(DeveloperProfile.status == "pending")
            .order_by(DeveloperProfile.date_created)  # type: ignore[arg-type]
        )
        return list(session.exec(statement).all())


def list_all_developers(
    status_filter: str | None = None,
) -> list[DeveloperProfile]:
    """List developer profiles, optionally filtered by status."""
    _ensure_table()
    with Session(engine) as session:
        statement = select(DeveloperProfile)
        if status_filter:
            statement = statement.where(DeveloperProfile.status == status_filter)
        statement = statement.order_by(DeveloperProfile.date_updated.desc())  # type: ignore[union-attr]
        return list(session.exec(statement).all())
