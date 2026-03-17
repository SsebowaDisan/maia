"""Developer access endpoints — application, status, and admin review."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.auth import get_current_user, require_super_admin
from api.models.user import User
from api.services.marketplace.developers import (
    DeveloperError,
    apply_for_developer,
    approve_developer,
    get_developer_status,
    list_all_developers,
    list_pending_applications,
    promote_to_trusted,
    reject_developer,
)

router = APIRouter(prefix="/api/developers", tags=["developers"])


# ── Request / Response schemas ────────────────────────────────────────────────


class DeveloperStatusResponse(BaseModel):
    status: str
    motivation: str | None = None
    rejection_reason: str | None = None


class ApplyRequest(BaseModel):
    motivation: str
    intended_agent_types: str = ""
    agreed_to_guidelines: bool = False


class ApplyResponse(BaseModel):
    status: str
    message: str


class AdminRejectRequest(BaseModel):
    reason: str


class DeveloperProfileResponse(BaseModel):
    user_id: str
    status: str
    motivation: str
    intended_agent_types: str
    rejection_reason: str | None = None
    reviewed_by: str | None = None
    date_created: str | None = None


class AdminActionResponse(BaseModel):
    status: str
    user_id: str


# ── User-facing endpoints ────────────────────────────────────────────────────


@router.get("/me", response_model=DeveloperStatusResponse)
def get_my_developer_status(
    user: Annotated[User, Depends(get_current_user)],
) -> DeveloperStatusResponse:
    """Return the current user's developer status."""
    from api.services.marketplace.developers import get_developer_profile

    profile = get_developer_profile(user.id)
    if not profile:
        return DeveloperStatusResponse(status="none")
    return DeveloperStatusResponse(
        status=profile.status,
        motivation=profile.motivation or None,
        rejection_reason=profile.rejection_reason,
    )


@router.post("/apply", response_model=ApplyResponse)
def apply(
    body: ApplyRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> ApplyResponse:
    """Submit a developer application."""
    try:
        profile = apply_for_developer(
            user_id=user.id,
            tenant_id=user.tenant_id,
            motivation=body.motivation,
            intended_agent_types=body.intended_agent_types,
            agreed_to_guidelines=body.agreed_to_guidelines,
        )
    except DeveloperError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return ApplyResponse(
        status=profile.status,
        message="Application submitted. You will be notified when reviewed.",
    )


# ── Admin endpoints ──────────────────────────────────────────────────────────


@router.get("/admin/applications", response_model=list[DeveloperProfileResponse])
def list_applications(
    admin: Annotated[User, Depends(require_super_admin)],
    status_filter: str | None = None,
) -> list[DeveloperProfileResponse]:
    """List developer applications (admin only)."""
    if status_filter == "pending":
        profiles = list_pending_applications()
    else:
        profiles = list_all_developers(status_filter=status_filter)
    return [
        DeveloperProfileResponse(
            user_id=p.user_id,
            status=p.status,
            motivation=p.motivation,
            intended_agent_types=p.intended_agent_types,
            rejection_reason=p.rejection_reason,
            reviewed_by=p.reviewed_by,
            date_created=p.date_created.isoformat() if p.date_created else None,
        )
        for p in profiles
    ]


@router.post("/admin/{user_id}/approve", response_model=AdminActionResponse)
def admin_approve(
    user_id: str,
    admin: Annotated[User, Depends(require_super_admin)],
) -> AdminActionResponse:
    """Approve a developer application (admin only)."""
    try:
        profile = approve_developer(user_id, reviewed_by=admin.id)
    except DeveloperError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return AdminActionResponse(status=profile.status, user_id=profile.user_id)


@router.post("/admin/{user_id}/reject", response_model=AdminActionResponse)
def admin_reject(
    user_id: str,
    body: AdminRejectRequest,
    admin: Annotated[User, Depends(require_super_admin)],
) -> AdminActionResponse:
    """Reject a developer application with a reason (admin only)."""
    try:
        profile = reject_developer(user_id, reviewed_by=admin.id, reason=body.reason)
    except DeveloperError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return AdminActionResponse(status=profile.status, user_id=profile.user_id)


@router.post("/admin/{user_id}/promote", response_model=AdminActionResponse)
def admin_promote(
    user_id: str,
    admin: Annotated[User, Depends(require_super_admin)],
) -> AdminActionResponse:
    """Promote a verified developer to trusted_publisher (admin only)."""
    try:
        profile = promote_to_trusted(user_id, promoted_by=admin.id)
    except DeveloperError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return AdminActionResponse(status=profile.status, user_id=profile.user_id)
