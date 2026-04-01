"""User management router — org admins manage their team.

Routes
------
GET    /api/users               List all users in my organisation
POST   /api/users/invite        Invite (create) a new user in my org
GET    /api/users/{user_id}     Get a user by id (own org only)
PATCH  /api/users/{user_id}     Update role or name (org_admin can set up to org_admin)
DELETE /api/users/{user_id}     Deactivate a user (cannot deactivate yourself)
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from api.auth import get_current_user, require_org_admin
from api.models.user import User
from api.services.auth.invite_delivery import send_invite_email
from api.services.auth.passwords import hash_password
from api.services.auth.store import (
    create_user,
    deactivate_user,
    get_user,
    list_all_active_users,
    list_users_for_tenant,
    update_user,
)
from api.services.auth.tokens import create_invite_token, decode_invite_token
from api.services.tenants.store import add_member

router = APIRouter(prefix="/api/users", tags=["users"])

_VALID_ROLES = {"org_admin", "org_user"}


# ── Request / response models ─────────────────────────────────────────────────

class InviteRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(default="", max_length=120)
    role: str = Field(default="org_user")
    temporary_password: str | None = Field(default=None, min_length=8, max_length=128)
    send_invite_email: bool = False


class UpdateUserRequest(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    role: str | None = None


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    tenant_id: str | None
    is_active: bool

    @classmethod
    def from_user(cls, user: User) -> "UserResponse":
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            tenant_id=user.tenant_id,
            is_active=user.is_active,
        )


class InviteResponse(BaseModel):
    user: UserResponse
    invite_link: str
    invite_expires_at: str
    email_sent: bool = False
    email_error: str | None = None


def _frontend_base_url() -> str:
    raw = str(
        os.getenv("MAIA_INVITE_LINK_BASE_URL")
        or os.getenv("MAIA_FRONTEND_BASE_URL")
        or "http://127.0.0.1:5173"
    ).strip()
    return raw.rstrip("/")


def _build_invite_link(token: str) -> str:
    base = _frontend_base_url()
    return f"{base}/accept-invite?token={quote(token, safe='')}"


# ── Guards ────────────────────────────────────────────────────────────────────

def _assert_same_tenant(actor: User, target_user: User) -> None:
    """Raise 403 if actor and target are in different tenants."""
    # super_admin can act across all tenants
    if actor.role == "super_admin":
        return
    if actor.tenant_id != target_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only manage users within your own organisation.",
        )


def _assert_role_assignable(actor: User, role: str) -> None:
    """Org admins cannot grant super_admin; only super_admin can promote to super_admin."""
    if role == "super_admin" and actor.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform super-admins can assign the super_admin role.",
        )
    if role not in _VALID_ROLES and actor.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role '{role}'. Must be one of: {sorted(_VALID_ROLES)}.",
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[UserResponse])
def list_users(
    actor: Annotated[User, Depends(require_org_admin)],
) -> list[UserResponse]:
    """List all active users in the calling admin's organisation."""
    if actor.role == "super_admin":
        # super_admin sees all — tenant_id filter skipped
        # For a cleaner UX, require a tenant_id query param in future
        users = list_all_active_users()
        return [UserResponse.from_user(u) for u in users]
    if not actor.tenant_id:
        return []
    users = list_users_for_tenant(actor.tenant_id)
    return [UserResponse.from_user(u) for u in users]


@router.post("/invite", response_model=InviteResponse, status_code=status.HTTP_201_CREATED)
def invite_user(
    body: InviteRequest,
    actor: Annotated[User, Depends(require_org_admin)],
) -> InviteResponse:
    """Invite a new user into the calling admin's organisation.

    Assigns a temporary password — the user should change it on first login.
    """
    from api.services.auth.store import get_user_by_email

    role = body.role.strip().lower()
    _assert_role_assignable(actor, role)

    if get_user_by_email(body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )

    tenant_id = actor.tenant_id  # new user joins the same org
    temporary_password = str(body.temporary_password or "").strip()
    if not temporary_password:
        temporary_password = secrets.token_urlsafe(24)

    user = create_user(
        email=body.email,
        hashed_password=hash_password(temporary_password),
        full_name=body.full_name,
        role=role,
        tenant_id=tenant_id,
    )

    # Add to tenant member list
    if tenant_id:
        try:
            add_member(tenant_id, user.id)
        except ValueError:
            pass  # tenant not found — tolerate silently

    invite_token = create_invite_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        tenant_id=user.tenant_id,
        invited_by=actor.id,
        full_name=user.full_name,
    )
    payload = decode_invite_token(invite_token)
    exp_raw = payload.get("exp")
    exp_ts = int(exp_raw) if isinstance(exp_raw, (int, float)) else int(datetime.now(tz=timezone.utc).timestamp())
    invite_expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc).isoformat()
    invite_link = _build_invite_link(invite_token)

    email_sent = False
    email_error: str | None = None
    if body.send_invite_email:
        email_sent, email_error = send_invite_email(
            recipient=user.email,
            invite_link=invite_link,
            inviter_email=actor.email,
            workspace_label="Maia",
        )

    return InviteResponse(
        user=UserResponse.from_user(user),
        invite_link=invite_link,
        invite_expires_at=invite_expires_at,
        email_sent=email_sent,
        email_error=email_error,
    )


@router.get("/{user_id}", response_model=UserResponse)
def get_user_detail(
    user_id: str,
    actor: Annotated[User, Depends(require_org_admin)],
) -> UserResponse:
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    _assert_same_tenant(actor, user)
    return UserResponse.from_user(user)


@router.patch("/{user_id}", response_model=UserResponse)
def update_user_detail(
    user_id: str,
    body: UpdateUserRequest,
    actor: Annotated[User, Depends(require_org_admin)],
) -> UserResponse:
    """Update a user's display name or role."""
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    _assert_same_tenant(actor, user)

    if body.role is not None:
        role = body.role.strip().lower()
        _assert_role_assignable(actor, role)
    else:
        role = None

    updated = update_user(user_id, full_name=body.full_name, role=role)
    return UserResponse.from_user(updated)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def deactivate_user_endpoint(
    user_id: str,
    actor: Annotated[User, Depends(require_org_admin)],
) -> None:
    """Deactivate a user account (soft delete). Cannot deactivate yourself."""
    if user_id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account.",
        )
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    _assert_same_tenant(actor, user)
    deactivate_user(user_id)

    # Remove from tenant member list
    if user.tenant_id:
        try:
            from api.services.tenants.store import remove_member
            remove_member(user.tenant_id, user_id)
        except ValueError:
            pass  # already removed or owner — tolerate
