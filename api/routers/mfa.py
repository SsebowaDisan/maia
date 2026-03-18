"""MFA (Multi-Factor Authentication) HTTP endpoints.

All routes require an authenticated user via ``get_current_user``.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.auth import get_current_user
from api.models.user import User
from api.services.auth.mfa import (
    activate_mfa,
    disable_mfa,
    enroll_mfa,
    has_mfa,
    verify_mfa,
)

router = APIRouter(prefix="/api/auth/mfa", tags=["mfa"])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class CodeBody(BaseModel):
    code: str


# ---------------------------------------------------------------------------
# POST /api/auth/mfa/enroll
# ---------------------------------------------------------------------------

@router.post("/enroll")
def enroll(user: Annotated[User, Depends(get_current_user)]) -> dict:
    """Start MFA enrolment — returns secret, QR provisioning URI, and backup codes."""
    if has_mfa(user.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="MFA is already active. Disable it first to re-enrol.",
        )
    result = enroll_mfa(user.id)
    try:
        from api.services.audit.trail import record_event
        record_event(
            tenant_id=user.tenant_id or "",
            user_id=user.id,
            action="mfa.enrolled",
            resource_type="mfa",
            resource_id=user.id,
            detail=f"MFA enrollment initiated for {user.email}",
        )
    except Exception:
        pass
    return result


# ---------------------------------------------------------------------------
# POST /api/auth/mfa/activate
# ---------------------------------------------------------------------------

@router.post("/activate")
def activate(
    body: CodeBody,
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Activate MFA by verifying the first TOTP code from the authenticator app."""
    if not activate_mfa(user.id, body.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid code or no pending enrolment.",
        )
    try:
        from api.services.audit.trail import record_event
        record_event(
            tenant_id=user.tenant_id or "",
            user_id=user.id,
            action="mfa.activated",
            resource_type="mfa",
            resource_id=user.id,
            detail=f"MFA activated for {user.email}",
        )
    except Exception:
        pass
    return {"activated": True}


# ---------------------------------------------------------------------------
# POST /api/auth/mfa/verify
# ---------------------------------------------------------------------------

@router.post("/verify")
def verify(
    body: CodeBody,
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Verify a TOTP code or backup code (used during login flow)."""
    if not verify_mfa(user.id, body.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid MFA code.",
        )
    return {"verified": True}


# ---------------------------------------------------------------------------
# DELETE /api/auth/mfa
# ---------------------------------------------------------------------------

@router.delete("")
def disable(user: Annotated[User, Depends(get_current_user)]) -> dict:
    """Disable and remove MFA enrolment."""
    if not disable_mfa(user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No MFA enrolment found.",
        )
    try:
        from api.services.audit.trail import record_event
        record_event(
            tenant_id=user.tenant_id or "",
            user_id=user.id,
            action="mfa.disabled",
            resource_type="mfa",
            resource_id=user.id,
            detail=f"MFA disabled for {user.email}",
        )
    except Exception:
        pass
    return {"disabled": True}


# ---------------------------------------------------------------------------
# GET /api/auth/mfa/status
# ---------------------------------------------------------------------------

@router.get("/status")
def mfa_status(user: Annotated[User, Depends(get_current_user)]) -> dict:
    """Return current MFA enrolment status for the authenticated user."""
    from api.services.auth.mfa import has_mfa as _has_mfa
    from sqlmodel import Session, select
    from api.models.mfa import MfaEnrollment
    from ktem.db.engine import engine

    active = _has_mfa(user.id)
    enrolled = False
    with Session(engine) as session:
        enrollment = session.exec(
            select(MfaEnrollment).where(MfaEnrollment.user_id == user.id)
        ).first()
        enrolled = enrollment is not None

    return {"enrolled": enrolled, "active": active}
