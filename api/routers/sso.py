"""SSO router — OIDC login flow.

Routes
------
GET  /api/auth/sso/config          Public SSO configuration probe
GET  /api/auth/sso/oidc/start      Initiate OIDC authorization
GET  /api/auth/sso/oidc/callback   Handle OIDC provider callback
"""
from __future__ import annotations

import logging
import secrets
import time

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from api.services.auth.oidc import (
    OIDC_ISSUER_URL,
    exchange_code,
    get_authorization_url,
    is_oidc_configured,
)
from api.services.auth.passwords import hash_password
from api.services.auth.store import create_user, get_user_by_email
from api.services.auth.tokens import create_access_token, create_refresh_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth/sso", tags=["sso"])

# ── In-memory pending state store (state → {nonce, created_at}) ──────────────

_pending_states: dict[str, dict[str, float | str]] = {}
_STATE_TTL = 600  # 10 minutes


def _cleanup_expired_states() -> None:
    """Remove expired entries from the pending-state map."""
    now = time.monotonic()
    expired = [s for s, v in _pending_states.items() if now - float(v["created_at"]) > _STATE_TTL]
    for s in expired:
        _pending_states.pop(s, None)


# ── Response models ──────────────────────────────────────────────────────────

class SSOConfigResponse(BaseModel):
    oidc_enabled: bool
    issuer: str


class StartResponse(BaseModel):
    auth_url: str
    state: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/config", response_model=SSOConfigResponse)
def sso_config() -> SSOConfigResponse:
    """Public endpoint — tells the frontend whether OIDC is available."""
    return SSOConfigResponse(
        oidc_enabled=is_oidc_configured(),
        issuer=OIDC_ISSUER_URL if is_oidc_configured() else "",
    )


@router.get("/oidc/start", response_model=StartResponse)
def oidc_start() -> StartResponse:
    """Generate a state + nonce pair and return the IdP authorization URL."""
    if not is_oidc_configured():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OIDC is not configured on this instance.",
        )

    _cleanup_expired_states()

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    _pending_states[state] = {"nonce": nonce, "created_at": time.monotonic()}

    try:
        auth_url = get_authorization_url(state=state, nonce=nonce)
    except Exception as exc:
        logger.error("Failed to build OIDC authorize URL: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to contact the identity provider.",
        ) from exc

    return StartResponse(auth_url=auth_url, state=state)


@router.get("/oidc/callback", response_model=TokenResponse)
def oidc_callback(
    code: str = Query(..., description="Authorization code from the IdP"),
    state: str = Query(..., description="State parameter for CSRF protection"),
) -> TokenResponse:
    """Exchange the authorization code for Maia JWT tokens.

    If the user does not yet exist a new ``org_user`` account is created.
    """
    _cleanup_expired_states()

    pending = _pending_states.pop(state, None)
    if pending is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state parameter.",
        )

    nonce = str(pending["nonce"])

    try:
        claims = exchange_code(code=code, state=state, nonce=nonce)
    except ValueError as exc:
        logger.warning("OIDC token exchange failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("OIDC token exchange error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Identity provider communication error.",
        ) from exc

    email: str = claims["email"]
    name: str = claims.get("name", "")
    tenant_id: str | None = claims.get("tid")

    # Find or create user
    user = get_user_by_email(email)
    if user is None:
        logger.info("Creating new SSO user: %s", email)
        user = create_user(
            email=email,
            hashed_password=hash_password(secrets.token_urlsafe(48)),
            full_name=name,
            role="org_user",
            tenant_id=tenant_id,
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact your administrator.",
        )

    access = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        tenant_id=user.tenant_id,
    )
    refresh = create_refresh_token(user_id=user.id)
    return TokenResponse(access_token=access, refresh_token=refresh)
