"""Logout function body with token revocation.

Patch into the existing auth router's ``/logout`` endpoint.
Extracts the JTI from the caller's access token and adds it
to the blocklist so the token cannot be reused.

Usage — replace the existing ``logout`` function in auth.py with::

    from api.routers.auth_logout_patch import logout_with_revocation

    @router.post("/logout", status_code=204, response_model=None)
    def logout(
        current_user: Annotated[User, Depends(get_current_user)],
        credentials: Annotated[HTTPAuthorizationCredentials, Depends(HTTPBearer())],
    ) -> None:
        return logout_with_revocation(current_user, credentials)
"""
from __future__ import annotations

from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt

from api.models.user import User
from api.services.auth.token_blocklist import block_token
from api.services.auth.tokens import _SECRET, _ALGORITHM, TokenError


def logout_with_revocation(
    current_user: User,
    credentials: HTTPAuthorizationCredentials,
) -> None:
    """Revoke the caller's access token by adding its JTI to the blocklist."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        ) from exc

    jti = payload.get("jti")
    if not jti:
        # Legacy token without JTI — nothing to revoke
        return None

    exp = payload.get("exp", 0)
    block_token(
        jti=jti,
        user_id=current_user.id,
        expires_at=float(exp),
        reason="logout",
    )
    return None
