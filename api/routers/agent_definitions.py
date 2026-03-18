"""Agent Definitions router — CRUD endpoints for agent definitions.

Responsibility: HTTP layer for agent definition management.
All persistence delegated to services/agent_definitions/store.py.
Schema validation delegated to schemas/agent_definition/schema.py.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, ValidationError

from api.auth import get_current_user_id
from api.models.agent_definition import AgentDefinitionRecord
from api.schemas.agent_definition import AgentDefinitionSchema
from api.services.agent_definitions import store as definition_store

router = APIRouter(prefix="/api/agent-definitions", tags=["agent-definitions"])


# ── Request / Response bodies ─────────────────────────────────────────────────


class AgentDefinitionCreateRequest(BaseModel):
    """Wraps an AgentDefinitionSchema + tenant context."""

    tenant_id: str
    definition: dict[str, Any]


class AgentDefinitionUpdateRequest(BaseModel):
    definition: dict[str, Any]


class AgentDefinitionSummary(BaseModel):
    id: str
    tenant_id: str
    agent_id: str
    name: str
    version: str
    is_public: bool
    is_active: bool
    date_created: str
    date_updated: str

    @classmethod
    def from_record(cls, rec: AgentDefinitionRecord) -> "AgentDefinitionSummary":
        return cls(
            id=rec.id,
            tenant_id=rec.tenant_id,
            agent_id=rec.agent_id,
            name=rec.name,
            version=rec.version,
            is_public=rec.is_public,
            is_active=rec.is_active,
            date_created=rec.date_created.isoformat(),
            date_updated=rec.date_updated.isoformat(),
        )


class AgentDefinitionDetail(AgentDefinitionSummary):
    definition: dict[str, Any]

    @classmethod
    def from_record(cls, rec: AgentDefinitionRecord) -> "AgentDefinitionDetail":  # type: ignore[override]
        return cls(
            id=rec.id,
            tenant_id=rec.tenant_id,
            agent_id=rec.agent_id,
            name=rec.name,
            version=rec.version,
            is_public=rec.is_public,
            is_active=rec.is_active,
            date_created=rec.date_created.isoformat(),
            date_updated=rec.date_updated.isoformat(),
            definition=dict(rec.definition or {}),
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("", response_model=list[AgentDefinitionSummary])
def list_definitions(
    tenant_id: str = Query(..., description="Tenant whose definitions to list."),
    user_id: Annotated[str, Depends(get_current_user_id)] = "",
) -> list[AgentDefinitionSummary]:
    """List all active agent definitions for a tenant."""
    records = definition_store.list_definitions(tenant_id, active_only=True)
    return [AgentDefinitionSummary.from_record(r) for r in records]


@router.get("/marketplace", response_model=list[AgentDefinitionSummary])
def list_marketplace_definitions(
    user_id: Annotated[str, Depends(get_current_user_id)] = "",
) -> list[AgentDefinitionSummary]:
    """List all publicly listed agent definitions (marketplace catalog)."""
    records = definition_store.list_public_definitions()
    return [AgentDefinitionSummary.from_record(r) for r in records]


@router.post(
    "",
    response_model=AgentDefinitionDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_definition(
    body: AgentDefinitionCreateRequest,
    user_id: Annotated[str, Depends(get_current_user_id)] = "",
) -> AgentDefinitionDetail:
    """Create a new agent definition for a tenant.

    The `definition` field must conform to AgentDefinitionSchema.
    """
    try:
        schema = AgentDefinitionSchema.model_validate(body.definition)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc

    try:
        record = definition_store.create_definition(body.tenant_id, user_id, schema)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    # Record initial version for audit trail
    try:
        import json
        from api.services.versions.store import create_version
        create_version(
            resource_type="agent_definition",
            resource_id=record.agent_id,
            tenant_id=body.tenant_id,
            version=record.version or "1.0.0",
            definition=json.dumps(dict(record.definition or {}), default=str),
            created_by=user_id,
            changelog="Initial creation",
        )
    except Exception:
        pass

    return AgentDefinitionDetail.from_record(record)


@router.get("/{record_id}", response_model=AgentDefinitionDetail)
def get_definition(
    record_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)] = "",
) -> AgentDefinitionDetail:
    """Get a single agent definition by its record id."""
    record = definition_store.get_definition(record_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent definition not found.",
        )
    return AgentDefinitionDetail.from_record(record)


@router.put("/{record_id}", response_model=AgentDefinitionDetail)
def update_definition(
    record_id: str,
    body: AgentDefinitionUpdateRequest,
    user_id: Annotated[str, Depends(get_current_user_id)] = "",
) -> AgentDefinitionDetail:
    """Replace the definition payload for an existing record."""
    try:
        schema = AgentDefinitionSchema.model_validate(body.definition)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc

    try:
        record = definition_store.update_definition(record_id, user_id, schema)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    # Record new version for audit trail
    try:
        import json
        from api.services.versions.store import create_version, get_latest_version, next_version
        latest = get_latest_version("agent_definition", record.agent_id)
        ver = next_version(latest.version) if latest else (record.version or "1.0.0")
        create_version(
            resource_type="agent_definition",
            resource_id=record.agent_id,
            tenant_id=record.tenant_id,
            version=ver,
            definition=json.dumps(dict(record.definition or {}), default=str),
            created_by=user_id,
            changelog="Updated definition",
        )
    except Exception:
        pass

    return AgentDefinitionDetail.from_record(record)


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def deactivate_definition(
    record_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)] = "",
) -> None:
    """Soft-delete an agent definition."""
    try:
        definition_store.deactivate_definition(record_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.get("/{record_id}/schema", response_model=dict)
def get_validated_schema(
    record_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)] = "",
) -> dict:
    """Return the stored definition as a validated AgentDefinitionSchema dict."""
    record = definition_store.get_definition(record_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent definition not found.",
        )
    schema = definition_store.load_schema(record)
    return schema.model_dump(mode="python")
