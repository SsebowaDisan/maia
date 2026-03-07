from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.auth import get_current_user_id
from api.services.agent.auth.credentials import get_credential_store
from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.tools.registry import get_tool_registry
from api.services.settings_service import load_user_settings

from api.context import get_context

from .common import masked_credential_payload
from .common import tenant_id_for_user
from .schemas import CredentialUpsertRequest

router = APIRouter(tags=["agent"])


@router.get("/tools")
def list_tools() -> list[dict[str, Any]]:
    return get_tool_registry().list_tools()


@router.get("/connectors/health")
def connector_health(
    user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    settings = load_user_settings(get_context(), user_id)
    return get_connector_registry().health_report(settings=settings)


@router.get("/connectors/plugins")
def connector_plugins(
    user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    settings = load_user_settings(get_context(), user_id)
    return get_connector_registry().plugin_manifests(settings=settings)


@router.get("/connectors/plugins/{connector_id}")
def connector_plugin(
    connector_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    registry = get_connector_registry()
    if connector_id not in registry.names():
        raise HTTPException(status_code=404, detail="Unknown connector.")
    settings = load_user_settings(get_context(), user_id)
    return registry.plugin_manifest(connector_id=connector_id, settings=settings)


@router.post("/connectors/credentials")
def upsert_connector_credentials(
    payload: CredentialUpsertRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    tenant_id = tenant_id_for_user(user_id)
    if payload.connector_id not in get_connector_registry().names():
        raise HTTPException(status_code=404, detail="Unknown connector.")
    record = get_credential_store().set(
        tenant_id=tenant_id,
        connector_id=payload.connector_id,
        values=payload.values,
    )
    return {
        "tenant_id": record.tenant_id,
        "connector_id": record.connector_id,
        "values": masked_credential_payload(record.values),
        "date_updated": record.date_updated,
    }


@router.get("/connectors/credentials")
def list_connector_credentials(
    user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    tenant_id = tenant_id_for_user(user_id)
    rows = get_credential_store().list_for_tenant(tenant_id=tenant_id)
    return [
        {
            "tenant_id": row.tenant_id,
            "connector_id": row.connector_id,
            "values": masked_credential_payload(row.values),
            "date_updated": row.date_updated,
        }
        for row in rows
    ]


@router.delete("/connectors/credentials/{connector_id}")
def delete_connector_credentials(
    connector_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    tenant_id = tenant_id_for_user(user_id)
    if connector_id not in get_connector_registry().names():
        raise HTTPException(status_code=404, detail="Unknown connector.")
    deleted = get_credential_store().delete(tenant_id=tenant_id, connector_id=connector_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Credentials not found.")
    return {"status": "deleted", "connector_id": connector_id}
