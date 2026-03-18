"""Custom roles HTTP endpoints.

Listing and reading roles requires authentication.
Creating, updating, and deleting roles requires org_admin privileges.
"""
from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.auth import get_current_user, require_org_admin
from api.models.user import User
from api.services.auth.dependencies import require_scope
from api.services.auth.roles import (
    ALL_SCOPES,
    create_role,
    delete_role,
    get_role,
    list_roles,
    update_role,
)

router = APIRouter(prefix="/api/roles", tags=["roles"])


# ---------------------------------------------------------------------------
# Request / response bodies
# ---------------------------------------------------------------------------

class CreateRoleBody(BaseModel):
    name: str
    scopes: list[str]
    description: str = ""


class UpdateRoleBody(BaseModel):
    name: str | None = None
    scopes: list[str] | None = None
    description: str | None = None


def _role_to_dict(role) -> dict:
    return {
        "id": role.id,
        "tenant_id": role.tenant_id,
        "name": role.name,
        "description": role.description,
        "scopes": json.loads(role.scopes_json),
        "created_by": role.created_by,
        "created_at": role.created_at,
        "updated_at": role.updated_at,
    }


# ---------------------------------------------------------------------------
# GET /api/roles/scopes — list all available scope strings
# ---------------------------------------------------------------------------

@router.get("/scopes")
def available_scopes(
    user: Annotated[User, Depends(get_current_user)],
) -> list[str]:
    """Return every valid scope string that can be assigned to a role."""
    return ALL_SCOPES


# ---------------------------------------------------------------------------
# GET /api/roles
# ---------------------------------------------------------------------------

@router.get("")
def list_tenant_roles(
    user: Annotated[User, Depends(get_current_user)],
) -> list[dict]:
    """List all custom roles for the caller's tenant."""
    tenant_id = user.tenant_id or ""
    return [_role_to_dict(r) for r in list_roles(tenant_id)]


# ---------------------------------------------------------------------------
# POST /api/roles
# ---------------------------------------------------------------------------

@router.post("", status_code=status.HTTP_201_CREATED)
def create(
    body: CreateRoleBody,
    admin: Annotated[User, Depends(require_org_admin)],
    _scope=require_scope("roles:manage"),
) -> dict:
    """Create a new custom role. Requires org_admin."""
    # Validate scopes
    invalid = [s for s in body.scopes if s not in ALL_SCOPES]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid scopes: {invalid}",
        )
    tenant_id = admin.tenant_id or ""
    role = create_role(
        tenant_id,
        body.name,
        body.scopes,
        created_by=admin.id,
        description=body.description,
    )
    try:
        from api.services.audit.trail import record_event
        record_event(
            tenant_id=tenant_id,
            user_id=admin.id,
            action="role.created",
            resource_type="role",
            resource_id=role.id,
            detail=f"Role '{body.name}' created",
        )
    except Exception:
        pass
    return _role_to_dict(role)


# ---------------------------------------------------------------------------
# GET /api/roles/{role_id}
# ---------------------------------------------------------------------------

@router.get("/{role_id}")
def get_role_detail(
    role_id: str,
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    role = get_role(role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found.",
        )
    return _role_to_dict(role)


# ---------------------------------------------------------------------------
# PATCH /api/roles/{role_id}
# ---------------------------------------------------------------------------

@router.patch("/{role_id}")
def update(
    role_id: str,
    body: UpdateRoleBody,
    admin: Annotated[User, Depends(require_org_admin)],
    _scope=require_scope("roles:manage"),
) -> dict:
    """Update a custom role. Requires org_admin."""
    if body.scopes is not None:
        invalid = [s for s in body.scopes if s not in ALL_SCOPES]
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid scopes: {invalid}",
            )
    try:
        role = update_role(
            role_id,
            name=body.name,
            scopes=body.scopes,
            description=body.description,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found.",
        )
    try:
        from api.services.audit.trail import record_event
        record_event(
            tenant_id=admin.tenant_id or "",
            user_id=admin.id,
            action="role.updated",
            resource_type="role",
            resource_id=role_id,
            detail=f"Role '{role_id}' updated",
        )
    except Exception:
        pass
    return _role_to_dict(role)


# ---------------------------------------------------------------------------
# DELETE /api/roles/{role_id}
# ---------------------------------------------------------------------------

@router.delete("/{role_id}")
def delete(
    role_id: str,
    admin: Annotated[User, Depends(require_org_admin)],
    _scope=require_scope("roles:manage"),
) -> dict:
    """Delete a custom role. Requires org_admin."""
    if not delete_role(role_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found.",
        )
    try:
        from api.services.audit.trail import record_event
        record_event(
            tenant_id=admin.tenant_id or "",
            user_id=admin.id,
            action="role.deleted",
            resource_type="role",
            resource_id=role_id,
            detail=f"Role '{role_id}' deleted",
        )
    except Exception:
        pass
    return {"deleted": True}
