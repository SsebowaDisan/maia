"""JWT access and refresh token helpers.

Tokens are signed with HS256.  The secret is read from the
MAIA_JWT_SECRET environment variable (required in production).
A random 32-byte fallback is generated at import time so tests
and local dev work without any configuration.

Token payload fields
--------------------
sub      User ID (str)
email    User email
role     User role string
tid      Tenant ID (str or None)
type     "access" | "refresh"
exp      Expiry (standard JWT claim)
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

# ── Configuration ──────────────────────────────────────────────────────────────

_SECRET = os.getenv("MAIA_JWT_SECRET") or secrets.token_hex(32)
_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL_MINUTES = int(os.getenv("MAIA_ACCESS_TOKEN_TTL_MINUTES", "60"))
REFRESH_TOKEN_TTL_DAYS = int(os.getenv("MAIA_REFRESH_TOKEN_TTL_DAYS", "30"))


# ── Token creation ─────────────────────────────────────────────────────────────

def create_access_token(
    *,
    user_id: str,
    email: str,
    role: str,
    tenant_id: str | None,
) -> str:
    """Issue a short-lived access token."""
    expire = datetime.now(tz=timezone.utc) + timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "tid": tenant_id,
        "type": "access",
        "exp": expire,
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def create_refresh_token(*, user_id: str) -> str:
    """Issue a long-lived refresh token (contains only sub + type)."""
    expire = datetime.now(tz=timezone.utc) + timedelta(days=REFRESH_TOKEN_TTL_DAYS)
    payload = {"sub": user_id, "type": "refresh", "exp": expire}
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


# ── Token verification ─────────────────────────────────────────────────────────

class TokenError(Exception):
    pass


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate an access token.  Raises TokenError on failure."""
    try:
        payload = jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    except JWTError as exc:
        raise TokenError(f"Invalid token: {exc}") from exc
    if payload.get("type") != "access":
        raise TokenError("Not an access token.")
    return payload


def decode_refresh_token(token: str) -> str:
    """Decode a refresh token and return the user_id (sub).  Raises TokenError on failure."""
    try:
        payload = jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    except JWTError as exc:
        raise TokenError(f"Invalid refresh token: {exc}") from exc
    if payload.get("type") != "refresh":
        raise TokenError("Not a refresh token.")
    return str(payload["sub"])
