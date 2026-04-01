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
iat      Issued-at timestamp (epoch float)
jti      Unique token identifier (UUID4)
"""
from __future__ import annotations

import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

# ── Configuration ──────────────────────────────────────────────────────────────

def _load_dev_secret() -> str:
    """Persist a stable dev secret across restarts when MAIA_JWT_SECRET is unset.

    Writes the generated secret to .maia_dev_jwt_secret on first run and
    reuses it on subsequent starts so tokens survive server restarts in dev.
    Never used when MAIA_JWT_SECRET is set via environment.
    """
    import pathlib
    secret_file = pathlib.Path(".maia_dev_jwt_secret")
    try:
        if secret_file.exists():
            stored = secret_file.read_text().strip()
            if stored:
                return stored
        new_secret = secrets.token_hex(32)
        secret_file.write_text(new_secret)
        return new_secret
    except OSError:
        return secrets.token_hex(32)


_SECRET = os.getenv("MAIA_JWT_SECRET") or _load_dev_secret()
_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL_MINUTES = int(os.getenv("MAIA_ACCESS_TOKEN_TTL_MINUTES", "60"))
REFRESH_TOKEN_TTL_DAYS = int(os.getenv("MAIA_REFRESH_TOKEN_TTL_DAYS", "30"))
INVITE_TOKEN_TTL_HOURS = int(os.getenv("MAIA_INVITE_TOKEN_TTL_HOURS", "72"))


# ── Token creation ─────────────────────────────────────────────────────────────

def create_access_token(
    *,
    user_id: str,
    email: str,
    role: str,
    tenant_id: str | None,
) -> str:
    """Issue a short-lived access token."""
    now = datetime.now(tz=timezone.utc)
    expire = now + timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "tid": tenant_id,
        "type": "access",
        "exp": expire,
        "iat": int(now.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def create_refresh_token(*, user_id: str) -> str:
    """Issue a long-lived refresh token (contains only sub + type)."""
    now = datetime.now(tz=timezone.utc)
    expire = now + timedelta(days=REFRESH_TOKEN_TTL_DAYS)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": expire,
        "iat": int(now.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def create_invite_token(
    *,
    user_id: str,
    email: str,
    role: str,
    tenant_id: str | None,
    invited_by: str | None,
    full_name: str | None = None,
) -> str:
    """Issue a short-lived onboarding token for invite acceptance."""
    now = datetime.now(tz=timezone.utc)
    expire = now + timedelta(hours=INVITE_TOKEN_TTL_HOURS)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "tid": tenant_id,
        "invited_by": invited_by,
        "full_name": full_name or "",
        "type": "invite",
        "exp": expire,
        "iat": int(now.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


# ── Token verification ─────────────────────────────────────────────────────────

class TokenError(Exception):
    pass


def _check_revoked(payload: dict[str, Any]) -> None:
    """Raise TokenError if the token's JTI is on the blocklist."""
    jti = payload.get("jti")
    sub = payload.get("sub")
    iat = payload.get("iat", 0)
    if jti and sub:
        from api.services.auth.token_blocklist import is_blocked
        if is_blocked(jti, str(sub), float(iat)):
            raise TokenError("Token has been revoked.")


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate an access token.  Raises TokenError on failure."""
    try:
        payload = jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    except JWTError as exc:
        raise TokenError(f"Invalid token: {exc}") from exc
    if payload.get("type") != "access":
        raise TokenError("Not an access token.")
    _check_revoked(payload)
    return payload


def decode_refresh_token(token: str) -> str:
    """Decode a refresh token and return the user_id (sub).  Raises TokenError on failure."""
    try:
        payload = jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    except JWTError as exc:
        raise TokenError(f"Invalid refresh token: {exc}") from exc
    if payload.get("type") != "refresh":
        raise TokenError("Not a refresh token.")
    _check_revoked(payload)
    return str(payload["sub"])


def decode_invite_token(token: str) -> dict[str, Any]:
    """Decode and validate an invite token. Raises TokenError on failure."""
    try:
        payload = jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    except JWTError as exc:
        raise TokenError(f"Invalid invite token: {exc}") from exc
    if payload.get("type") != "invite":
        raise TokenError("Not an invite token.")
    _check_revoked(payload)
    return payload
