"""B9 — Developer API key router.

Responsibility: CRUD endpoints for developer API keys that allow programmatic
access to the marketplace publishing pipeline.

Endpoints:
  POST   /api/auth/api-keys               — create a new key (returns raw key once)
  GET    /api/auth/api-keys               — list the user's active keys
  DELETE /api/auth/api-keys/{key_id}      — revoke a key
"""
from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.auth import get_current_user
from api.models.user import User
from api.services.auth import api_keys as key_service

router = APIRouter(prefix="/api/auth/api-keys", tags=["auth"])

_ALLOWED_SCOPES = {"marketplace:publish", "marketplace:read"}


# ── Request / response models ──────────────────────────────────────────────────

class CreateKeyRequest(BaseModel):
    label: str = Field(default="", max_length=120)
    scopes: list[str] = Field(
        default=["marketplace:publish", "marketplace:read"],
        description="Permission scopes to grant this key.",
    )
    expires_in_days: Optional[int] = Field(
        default=None,
        ge=1,
        le=365,
        description="Days until key expires. Omit for no expiry.",
    )


class KeyResponse(BaseModel):
    id: str
    label: str
    key_prefix: str
    scopes: list[str]
    is_active: bool
    expires_at: Optional[float]
    created_at: float
    last_used_at: Optional[float]
    # raw_key is only present immediately after creation
    raw_key: Optional[str] = None

    @classmethod
    def from_record(cls, record: Any, raw_key: str | None = None) -> "KeyResponse":
        return cls(
            id=record.id,
            label=record.label,
            key_prefix=record.key_prefix,
            scopes=record.scopes.split(),
            is_active=record.is_active,
            expires_at=record.expires_at,
            created_at=record.created_at,
            last_used_at=record.last_used_at,
            raw_key=raw_key,
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED, response_model=KeyResponse)
def create_key(
    body: CreateKeyRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> KeyResponse:
    """Create a developer API key.

    The raw key is returned **once** in the response. Store it securely —
    it cannot be retrieved again.
    """
    # Validate requested scopes
    invalid = set(body.scopes) - _ALLOWED_SCOPES
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown scopes: {sorted(invalid)}. Allowed: {sorted(_ALLOWED_SCOPES)}",
        )

    expires_at: float | None = None
    if body.expires_in_days:
        import time
        expires_at = time.time() + body.expires_in_days * 86_400

    record, raw_key = key_service.create_api_key(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        label=body.label,
        scopes=body.scopes,
        expires_at=expires_at,
    )
    return KeyResponse.from_record(record, raw_key=raw_key)


@router.get("", response_model=list[KeyResponse])
def list_keys(
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[KeyResponse]:
    """List all active API keys for the current user."""
    records = key_service.list_api_keys(current_user.id)
    return [KeyResponse.from_record(r) for r in records]


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def revoke_key(
    key_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Revoke an API key permanently."""
    if not key_service.revoke_api_key(key_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found.")
