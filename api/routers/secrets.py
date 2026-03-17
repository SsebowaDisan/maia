"""Secret management API — CRUD for tenant-scoped secrets.

All endpoints require org_admin (or super_admin) role.
Secret values are never returned in full; GET returns a masked version.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.auth import require_org_admin
from api.models.user import User
from api.services.secrets.provider import get_secret_provider

router = APIRouter(prefix="/api/secrets", tags=["secrets"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tenant_id(user: User) -> str:
    """Derive the tenant scope.  super_admin with no tenant uses their user id."""
    return user.tenant_id or user.id


def _mask(value: str) -> str:
    if len(value) <= 4:
        return "****"
    return f"****{value[-4:]}"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SecretBody(BaseModel):
    value: str


class SecretKeyList(BaseModel):
    keys: list[str]


class SecretMasked(BaseModel):
    key: str
    value: str  # masked


class HealthResponse(BaseModel):
    ok: bool
    provider: str
    detail: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/health", response_model=HealthResponse)
def secret_health(user: Annotated[User, Depends(require_org_admin)]):
    """Check the secret provider's connectivity."""
    provider = get_secret_provider()
    return provider.health_check()


@router.get("", response_model=SecretKeyList)
def list_secrets(
    user: Annotated[User, Depends(require_org_admin)],
    prefix: str = "",
):
    """List secret keys for the current tenant."""
    provider = get_secret_provider()
    keys = provider.list_keys(tenant_id=_tenant_id(user), prefix=prefix)
    return {"keys": keys}


@router.get("/{key:path}", response_model=SecretMasked)
def get_secret(
    key: str,
    user: Annotated[User, Depends(require_org_admin)],
):
    """Return a masked view of a secret value."""
    provider = get_secret_provider()
    value = provider.get(key, tenant_id=_tenant_id(user))
    if value is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret not found.")
    return {"key": key, "value": _mask(value)}


@router.put("/{key:path}", status_code=status.HTTP_204_NO_CONTENT)
def set_secret(
    key: str,
    body: SecretBody,
    user: Annotated[User, Depends(require_org_admin)],
):
    """Create or update a secret."""
    provider = get_secret_provider()
    provider.set(key, body.value, tenant_id=_tenant_id(user))


@router.delete("/{key:path}")
def delete_secret(
    key: str,
    user: Annotated[User, Depends(require_org_admin)],
):
    """Delete a secret. Returns 404 if not found."""
    provider = get_secret_provider()
    deleted = provider.delete(key, tenant_id=_tenant_id(user))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret not found.")
    return {"deleted": True}
