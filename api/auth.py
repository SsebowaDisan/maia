from __future__ import annotations

import os
from typing import Annotated

from fastapi import Header, HTTPException, Query, status


def _truthy_env(name: str, *, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_user_id(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def get_current_user_id(
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    user_id: Annotated[str | None, Query(alias="user_id")] = None,
) -> str:
    # Query fallback keeps SSE/EventSource endpoints usable where custom headers
    # are difficult to set from browsers.
    resolved = _normalize_user_id(x_user_id) or _normalize_user_id(user_id)
    if resolved:
        return resolved

    require_explicit_user = _truthy_env("MAIA_REQUIRE_EXPLICIT_USER_ID", default=False)
    if require_explicit_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Missing user identity. Send X-User-Id header "
                "(or user_id query param for SSE endpoints)."
            ),
        )

    fallback_user = _normalize_user_id(os.getenv("MAIA_DEV_DEFAULT_USER_ID", "default"))
    if fallback_user:
        return fallback_user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing user identity and MAIA_DEV_DEFAULT_USER_ID is empty.",
    )
