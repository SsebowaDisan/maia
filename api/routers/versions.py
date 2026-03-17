"""Version history REST router.

Routes:
    GET  /api/versions/{resource_type}/{resource_id}            — list versions
    GET  /api/versions/{resource_type}/{resource_id}/{version}  — get one version
    POST /api/versions/{resource_type}/{resource_id}/promote    — env promotion
    POST /api/versions/{resource_type}/{resource_id}/rollback   — rollback
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.auth import get_current_user_id, require_org_admin
from api.models.user import User
from api.models.version_history import VersionRecord
from api.services.versions import store

router = APIRouter(prefix="/api/versions", tags=["versions"])


# ── Request / response bodies ─────────────────────────────────────────────────


class PromoteRequest(BaseModel):
    from_env: str
    to_env: str


class RollbackRequest(BaseModel):
    version: str
    environment: str


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/{resource_type}/{resource_id}")
def list_versions(
    resource_type: str,
    resource_id: str,
    environment: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    _user_id: str = Depends(get_current_user_id),
) -> list[VersionRecord]:
    """List all versions for a resource, newest first."""
    return store.list_versions(
        resource_type,
        resource_id,
        environment=environment,
        limit=limit,
    )


@router.get("/{resource_type}/{resource_id}/{version}")
def get_version(
    resource_type: str,
    resource_id: str,
    version: str,
    environment: Annotated[str, Query()] = "dev",
    _user_id: str = Depends(get_current_user_id),
) -> VersionRecord | None:
    """Get a specific version of a resource."""
    return store.get_version(resource_type, resource_id, version, environment)


@router.post("/{resource_type}/{resource_id}/promote")
def promote(
    resource_type: str,
    resource_id: str,
    body: PromoteRequest,
    admin: User = Depends(require_org_admin),
) -> VersionRecord:
    """Promote the latest version from one environment to another."""
    return store.promote(
        resource_type,
        resource_id,
        from_env=body.from_env,
        to_env=body.to_env,
        promoted_by=admin.id,
    )


@router.post("/{resource_type}/{resource_id}/rollback")
def rollback(
    resource_type: str,
    resource_id: str,
    body: RollbackRequest,
    admin: User = Depends(require_org_admin),
) -> VersionRecord:
    """Rollback to a previous version, creating a new latest record."""
    return store.rollback(
        resource_type,
        resource_id,
        target_version=body.version,
        environment=body.environment,
        rolled_back_by=admin.id,
    )
