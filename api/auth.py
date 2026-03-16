"""Authentication and authorisation dependencies.

Primary flow (production)
--------------------------
All requests must carry an ``Authorization: Bearer <access_token>`` header.
The access token is a signed JWT issued by POST /api/auth/login.

Dev / legacy fallback
---------------------
When the environment variable ``MAIA_AUTH_DISABLED=true`` (default in dev),
the old ``X-User-Id`` header / ``user_id`` query-param flow is still accepted
so that existing tooling and notebooks continue to work without changes.

Dependency hierarchy
--------------------
get_current_user_id   → returns str user_id (all authenticated users)
get_current_user      → returns User ORM object
require_org_admin     → raises 403 if role < org_admin
require_super_admin   → raises 403 if role != super_admin
"""
from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.models.user import User
from api.services.auth.store import get_user
from api.services.auth.tokens import TokenError, decode_access_token

# Optional — skip token auth for local dev / migration period
_AUTH_DISABLED = os.getenv("MAIA_AUTH_DISABLED", "true").strip().lower() in {"1", "true", "yes", "on"}

_bearer = HTTPBearer(auto_error=False)


def _truthy_env(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _normalize(value: str | None) -> str | None:
    return value.strip() or None if value else None


# ── Core identity resolution ───────────────────────────────────────────────────

def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    # Legacy fallback headers kept for SSE endpoints where Bearer is awkward
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    user_id_query: Annotated[str | None, Query(alias="user_id")] = None,
) -> User:
    """Return the authenticated User object.

    Tries Bearer JWT first; falls back to X-User-Id if auth is disabled.
    """
    # ── 1. JWT Bearer token ────────────────────────────────────────────────────
    if credentials and credentials.credentials:
        try:
            payload = decode_access_token(credentials.credentials)
        except TokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        uid = payload.get("sub")
        user = get_user(str(uid)) if uid else None
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or deactivated.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user

    # ── 2. Legacy header / query-param (dev / migration mode) ─────────────────
    if _AUTH_DISABLED:
        resolved = _normalize(x_user_id) or _normalize(user_id_query)
        if resolved:
            # Try to load real user; if missing, synthesise a super_admin shell
            # so existing dev data continues to work without a login step.
            user = get_user(resolved)
            if user:
                return user
            # Synthesise an in-memory user so callers don't need a DB record
            fallback = User(
                id=resolved,
                email=f"{resolved}@dev.local",
                hashed_password="",
                role="super_admin",
                tenant_id=None,
                is_active=True,
            )
            return fallback

        dev_default = _normalize(os.getenv("MAIA_DEV_DEFAULT_USER_ID", "default"))
        if dev_default:
            user = get_user(dev_default)
            if user:
                return user
            fallback = User(
                id=dev_default,
                email="dev@local",
                hashed_password="",
                role="super_admin",
                tenant_id=None,
                is_active=True,
            )
            return fallback

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Provide Authorization: Bearer <token>.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user_id(
    user: Annotated[User, Depends(get_current_user)],
) -> str:
    """Convenience dependency — returns only the user_id string.

    Drop-in replacement for the old header-only version so all existing
    routers continue to work without changes.
    """
    return user.id


# ── Role guards ────────────────────────────────────────────────────────────────

def require_org_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Require org_admin or super_admin role."""
    if user.role not in ("org_admin", "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organisation admin privileges required.",
        )
    return user


def require_super_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Require super_admin role (Maia platform staff only)."""
    if user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform super-admin privileges required.",
        )
    return user
