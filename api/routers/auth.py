"""Authentication router.

Routes
------
POST /api/auth/bootstrap  One-time super-admin setup (only works when no users exist)
POST /api/auth/register   Company sign-up → creates org + first org_admin user
POST /api/auth/login      Email + password → access_token + refresh_token
POST /api/auth/refresh    Exchange refresh_token → new access_token
POST /api/auth/logout     Client-side hint to discard tokens (stateless)
GET  /api/auth/me         Returns current user profile
PATCH /api/auth/me        Update own full_name or password
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field

from api.auth import get_current_user
from api.routers.auth_logout_patch import logout_with_revocation
from api.models.user import User
from api.services.auth.passwords import hash_password, verify_password
from api.services.auth.store import (
    count_users,
    create_user,
    create_user_with_id,
    get_user,
    get_user_by_email,
    update_user,
)
from api.services.auth.tokens import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from api.services.tenants.store import create_tenant

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Request / response models ─────────────────────────────────────────────────

class BootstrapRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class RegisterRequest(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=120)
    full_name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UpdateMeRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    current_password: str | None = None
    new_password: str | None = Field(default=None, min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _issue_tokens(user: User) -> TokenResponse:
    access = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        tenant_id=user.tenant_id,
    )
    refresh = create_refresh_token(user_id=user.id)
    return TokenResponse(access_token=access, refresh_token=refresh)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/bootstrap", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def bootstrap(body: BootstrapRequest) -> TokenResponse:
    """One-time platform setup — creates the first super_admin account.

    This endpoint is LOCKED once any user record exists in the database.
    It preserves all existing data by assigning the new account the legacy
    'default' user ID that all prior conversations, uploads, and settings
    are stored under.

    Call it exactly once, immediately after first deployment.
    """
    if count_users() > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bootstrap is locked — a super_admin account already exists. Use /login.",
        )
    if get_user_by_email(body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    # Create under the legacy "default" ID so all existing chats/uploads are
    # instantly accessible after first login.
    user = create_user_with_id(
        user_id="default",
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role="super_admin",
        tenant_id=None,
    )
    return _issue_tokens(user)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest) -> TokenResponse:
    """Create a new company account.

    Creates the tenant (organisation) and the first user with the
    ``org_admin`` role in a single transaction.
    """
    if get_user_by_email(body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    # Create the tenant first so we have a tenant_id for the user
    try:
        tenant = create_tenant(
            name=body.company_name,
            owner_user_id="__pending__",  # updated below once user id is known
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    user = create_user(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role="org_admin",
        tenant_id=tenant.id,
    )

    # Back-fill the real owner_user_id and add the user to member list
    from api.services.tenants.store import update_tenant, add_member
    from sqlmodel import Session
    from ktem.db.engine import engine
    from api.models.tenant import Tenant
    with Session(engine) as session:
        t = session.get(Tenant, tenant.id)
        if t:
            t.owner_user_id = user.id
            t.member_user_ids = [user.id]
            session.add(t)
            session.commit()

    return _issue_tokens(user)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request) -> TokenResponse:
    """Authenticate with email and password, return JWT tokens."""
    user = get_user_by_email(body.email)
    if not user or not verify_password(body.password, user.hashed_password):
        try:
            from api.services.audit.trail import record_event
            record_event(
                tenant_id="",
                user_id="",
                action="user.login_failed",
                resource_type="auth",
                resource_id=body.email,
                detail=f"Failed login attempt for {body.email}",
                ip_address=request.client.host if request.client else "",
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact your administrator.",
        )
    tokens = _issue_tokens(user)
    try:
        from api.services.audit.trail import record_event
        record_event(
            tenant_id=user.tenant_id or "",
            user_id=user.id,
            action="user.login",
            resource_type="auth",
            resource_id=user.id,
            detail=f"User {user.email} logged in successfully",
            ip_address=request.client.host if request.client else "",
        )
    except Exception:
        pass
    return tokens


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(body: RefreshRequest) -> TokenResponse:
    """Exchange a valid refresh token for a new access token."""
    try:
        user_id = decode_refresh_token(body.refresh_token)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = get_user(user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _issue_tokens(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def logout(
    _current_user: Annotated[User, Depends(get_current_user)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(HTTPBearer())],
    request: Request,
) -> None:
    """Revoke the caller's access token so it cannot be reused."""
    result = logout_with_revocation(_current_user, credentials)
    try:
        from api.services.audit.trail import record_event
        record_event(
            tenant_id=_current_user.tenant_id or "",
            user_id=_current_user.id,
            action="user.logout",
            resource_type="auth",
            resource_id=_current_user.id,
            detail=f"User {_current_user.email} logged out",
            ip_address=request.client.host if request.client else "",
        )
    except Exception:
        pass
    return result


@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Return the profile of the currently authenticated user."""
    return UserResponse.from_user(current_user)


@router.patch("/me", response_model=UserResponse)
def update_me(
    body: UpdateMeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Update own display name or change password."""
    if body.new_password:
        if not body.current_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="current_password is required to set a new password.",
            )
        user_db = get_user(current_user.id)
        if not user_db or not verify_password(body.current_password, user_db.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect.",
            )
        from sqlmodel import Session
        from ktem.db.engine import engine
        from datetime import datetime
        with Session(engine) as session:
            u = session.get(type(user_db), current_user.id)
            if u:
                u.hashed_password = hash_password(body.new_password)
                u.date_updated = datetime.utcnow()
                session.add(u)
                session.commit()

    updated = update_user(
        current_user.id,
        full_name=body.full_name,
    )
    return UserResponse.from_user(updated)
