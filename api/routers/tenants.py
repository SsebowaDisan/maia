"""Tenants router — admin CRUD endpoints for platform tenants.

Responsibility: HTTP layer only. All persistence delegated to services/tenants/store.py.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from api.auth import get_current_user_id
from api.models.tenant import Tenant
from api.services.tenants import store as tenant_store

router = APIRouter(prefix="/api/tenants", tags=["tenants"])


# ── Request / Response bodies ─────────────────────────────────────────────────


class TenantCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
    plan: str = "free"


class TenantUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    plan: str | None = None
    feature_flags: dict | None = None
    max_agents: int | None = Field(default=None, ge=1, le=1000)
    max_connectors: int | None = Field(default=None, ge=1, le=500)


class MemberAddRequest(BaseModel):
    user_id: str


class TenantResponse(BaseModel):
    id: str
    name: str
    slug: str
    owner_user_id: str
    member_user_ids: list[str]
    plan: str
    feature_flags: dict
    max_agents: int
    max_connectors: int
    is_active: bool
    date_created: str
    date_updated: str

    @classmethod
    def from_model(cls, tenant: Tenant) -> "TenantResponse":
        return cls(
            id=tenant.id,
            name=tenant.name,
            slug=tenant.slug,
            owner_user_id=tenant.owner_user_id,
            member_user_ids=list(tenant.member_user_ids or []),
            plan=tenant.plan,
            feature_flags=dict(tenant.feature_flags or {}),
            max_agents=tenant.max_agents,
            max_connectors=tenant.max_connectors,
            is_active=tenant.is_active,
            date_created=tenant.date_created.isoformat(),
            date_updated=tenant.date_updated.isoformat(),
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("", response_model=list[TenantResponse])
def list_tenants(
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> list[TenantResponse]:
    """List all active tenants. Admin-only in production."""
    tenants = tenant_store.list_tenants(active_only=True)
    return [TenantResponse.from_model(t) for t in tenants]


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
def create_tenant(
    body: TenantCreateRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> TenantResponse:
    """Create a new tenant. The calling user becomes the owner."""
    try:
        tenant = tenant_store.create_tenant(
            name=body.name,
            owner_user_id=user_id,
            slug=body.slug,
            plan=body.plan,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return TenantResponse.from_model(tenant)


@router.get("/{tenant_id}", response_model=TenantResponse)
def get_tenant(
    tenant_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> TenantResponse:
    """Get a single tenant by id."""
    tenant = tenant_store.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")
    return TenantResponse.from_model(tenant)


@router.patch("/{tenant_id}", response_model=TenantResponse)
def update_tenant(
    tenant_id: str,
    body: TenantUpdateRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> TenantResponse:
    """Update mutable tenant fields."""
    try:
        tenant = tenant_store.update_tenant(
            tenant_id,
            name=body.name,
            plan=body.plan,
            feature_flags=body.feature_flags,
            max_agents=body.max_agents,
            max_connectors=body.max_connectors,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return TenantResponse.from_model(tenant)


@router.delete(
    "/{tenant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def deactivate_tenant(
    tenant_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> None:
    """Soft-delete a tenant (sets is_active=False)."""
    try:
        tenant_store.deactivate_tenant(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{tenant_id}/members", response_model=TenantResponse)
def add_member(
    tenant_id: str,
    body: MemberAddRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> TenantResponse:
    """Add a user to a tenant's member list."""
    try:
        tenant = tenant_store.add_member(tenant_id, body.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return TenantResponse.from_model(tenant)


@router.delete("/{tenant_id}/members/{member_user_id}", response_model=TenantResponse)
def remove_member(
    tenant_id: str,
    member_user_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> TenantResponse:
    """Remove a user from a tenant's member list."""
    try:
        tenant = tenant_store.remove_member(tenant_id, member_user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return TenantResponse.from_model(tenant)
